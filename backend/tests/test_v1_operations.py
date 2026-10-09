"""V1 non-operational integration. Synthetic account, temporary stores, no connector."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from core.rebuild.application import create_app
from core.rebuild.ledger import Ledger
from core.rebuild.operations import Operations, ControlCommand, DeploymentCommand, COMPONENTS
from core.rebuild.source_ingestion import SourceSubmission
from test_p4_sources import p4, body
from test_p2_safety import TIME, inputs


def service(p4):
    return Operations(p4.ledger,sources=p4.service,safety=p4.safety,provider=lambda _:inputs(),clock=lambda:p4.clock[0])


def test_manual_pipeline_exact_lineage_no_broker(p4):
    ops=service(p4)
    result=ops.ingest(SourceSubmission.model_validate(body()))
    assert result['status']=='P2_APPROVED_NOT_SUBMITTED',result
    with p4.ledger.connect() as c:
        request=c.execute('SELECT * FROM p2_execution_requests').fetchone()
        intent=c.execute('SELECT * FROM order_intents').fetchone()
        assert request['intent_id']==result['intent_id']==intent['intent_id']
        assert intent['signal_id']==result['signal_id']
        assert request['decision_id']==result['decision_id']
        assert c.execute('SELECT count(*) FROM p3_attempts').fetchone()[0]==0
    assert result['broker_execution']=='HARD_DISABLED'


@pytest.mark.parametrize('kind',['MANUAL','WHATSAPP_HUMAN'])
def test_replay_concurrency_restart(p4,kind):
    ops=service(p4); message=SourceSubmission.model_validate(body(kind))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:ops.ingest(message),range(8)))
    assert len({r['intent_id'] for r in results})==1
    again=service(p4).ingest(message)
    assert again['duplicate'] is True
    with p4.ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM p2_execution_requests').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM p3_attempts').fetchone()[0]==0


def test_changed_message_rejects(p4):
    ops=service(p4); data=body()
    ops.ingest(SourceSubmission.model_validate(data))
    data['signal']['stop_loss']=89.
    with pytest.raises(ValueError,match='REPLAY_CONFLICT'): ops.ingest(SourceSubmission.model_validate(data))


def test_p2_rejection_persists(p4):
    ops=service(p4); data=body(); data['signal']['requested_risk_pct']=.51
    r=ops.ingest(SourceSubmission.model_validate(data))
    assert r['status']=='P2_REJECTED'
    with p4.ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM p2_execution_requests').fetchone()[0]==0


def test_halt_blocks_proposals(p4):
    p4.ledger.halt('fixture stop')
    r=service(p4).ingest(SourceSubmission.model_validate(body()))
    assert r['status']=='P2_REJECTED' and r['reason']=='HALTED'


@pytest.mark.parametrize('patch,status',[
    ({'sender_id':'wrong'},'REJECTED_UNAUTHORIZED_SOURCE'),
    ({'group_id':'wrong'},'REJECTED_UNAUTHORIZED_SOURCE'),
    ({'raw_text':'GOLD BUY NOW SL below support TP soon'},'QUARANTINED_AMBIGUOUS'),
    ({'original_timestamp':(TIME-timedelta(seconds=601)).isoformat()},'REJECTED_EXPIRED'),
])
def test_whatsapp_quarantine(p4,patch,status):
    data=body('WHATSAPP_HUMAN'); data.update(patch)
    r=service(p4).ingest(SourceSubmission.model_validate(data))
    assert r['status']==status,r
    with p4.ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM order_intents').fetchone()[0]==0


@pytest.mark.parametrize('kind',['HISTORICAL_WHATSAPP','SCREENSHOT','NEXUSAI_STRATEGY'])
def test_research_firewall(p4,kind):
    with pytest.raises(ValueError): service(p4).ingest(SourceSubmission.model_validate(body(kind)))


@pytest.mark.parametrize('key',['manual','whatsapp','automated'])
def test_controls_cannot_enable_without_qualification(p4,key):
    data=dict(command_id='fixture-command',expected_revision=0,manual=False,whatsapp=False,automated=False)
    data[key]=True
    with pytest.raises(ValueError,match='QUALIFICATION_REQUIRED'): service(p4).set_controls(ControlCommand(**data))
    assert service(p4).controls()['revision']==0


def test_controls_audit_revision_retry(p4):
    ops=service(p4)
    command=ControlCommand(command_id='fixture-command',expected_revision=0,manual=False,whatsapp=False,automated=False)
    assert ops.set_controls(command)==ops.set_controls(command)
    assert service(p4).controls()['revision']==1
    with pytest.raises(ValueError,match='REVISION_CONFLICT'):
        ops.set_controls(command.model_copy(update={'command_id':'second-command'}))
    with p4.ledger.connect() as c:
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM v1_control_events')


@pytest.mark.parametrize('strategy',['p6-01','p6-02','p6-04','p6-05','p6-07'])
def test_disabled_deployments_are_distinct_and_replayable(p4,strategy):
    ops=service(p4)
    command=DeploymentCommand(strategy_id=strategy,instrument='XAUUSD',timeframe='1H')
    one=ops.deploy(command)
    assert ops.deploy(command)==one
    assert one['enabled']==0 and one['mode']=='DEMO_ONLY'
    with pytest.raises(ValueError): ops.deploy(command.model_copy(update={'enabled':True}))


def test_deployment_allowlist(p4):
    with pytest.raises(ValueError): service(p4).deploy(DeploymentCommand(strategy_id='p6-03',instrument='XAUUSD',timeframe='1H'))


def test_health_freshness_append_only_and_ack_does_not_unhalt(p4):
    ops=service(p4)
    kwargs=dict(component='mt5',state='DISCONNECTED',observed_at=TIME,valid_until=TIME+timedelta(seconds=5),evidence_id='synthetic-not-secret')
    identity=ops.record_health(**kwargs)
    assert ops.record_health(**kwargs)==identity
    ops.acknowledge(identity,'ack-fixture')
    assert ops.report()['alerts'][0]['acknowledged']==1
    p4.clock[0]+=timedelta(seconds=6)
    states={x['component']:x['state'] for x in ops.report()['health']}
    assert states['mt5']=='STALE'
    assert states['whatsapp']=='NOT_AVAILABLE'
    with p4.ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM v1_monitor_samples').fetchone()[0]==1
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM v1_monitor_samples')


def test_report_deterministic_read_only_unavailable_not_zero(p4):
    ops=service(p4)
    a=ops.report(); b=ops.report()
    assert a==b
    assert a['portfolio']['equity'] is None
    assert a['p8']['status']=='NOT_AVAILABLE'
    assert a['p8']['execution_eligible'] is False
    assert set(a['sources'])=={'MANUAL','WHATSAPP_HUMAN','NEXUSAI_STRATEGY','HISTORICAL_WHATSAPP','SCREENSHOT'}
    assert len(a['health'])==len(COMPONENTS)
    assert a['reconciliation']['status']=='NOT_ATTESTED'
    with p4.ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM v1_monitor_samples').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM v1_alerts').fetchone()[0]==0


def test_report_source_window_and_no_raw_text(p4):
    ops=service(p4)
    ops.ingest(SourceSubmission.model_validate(body('WHATSAPP_HUMAN')))
    report=ops.report()
    assert report['sources']['WHATSAPP_HUMAN']['received']==1
    assert report['sources']['MANUAL']['received']==0
    assert 'Current rate' not in json.dumps(report)
    assert ops.report(start=TIME+timedelta(seconds=0))['window']['start']==TIME.isoformat()
    with pytest.raises(ValueError): ops.report(start=TIME+timedelta(seconds=1))


def test_routes_auth_native_lock_and_input_redaction(tmp_path):
    app=create_app(database_path=tmp_path/'route.sqlite',token='fixture-access')
    with TestClient(app) as client:
        assert client.get('/api/core/operations/snapshot').status_code==403
        h={'X-Control-Token':'fixture-access'}
        r=client.get('/api/core/operations/snapshot',headers=h)
        assert r.status_code==200,r.text
        assert r.json()['live_locked'] is True
        assert client.post('/api/core/operations/submit',headers=h,json={}).status_code==423
        assert client.post('/api/core/operations/proposals',headers=h,json={'password':'never-echo-this'}).status_code==422
        assert 'never-echo-this' not in client.post('/api/core/operations/proposals',headers=h,json={'password':'never-echo-this'}).text
        data=body('WHATSAPP_HUMAN')
        assert client.post('/api/core/operations/proposals',headers=h,json=data).status_code==403


def test_connector_credential_cannot_read_or_control_workspace(tmp_path):
    app=create_app(database_path=tmp_path/'connector.sqlite',token='fixture-access',
                   whatsapp_connector_token='fixture-connector-only')
    with TestClient(app) as client:
        endpoint='/api/core/operations/whatsapp'
        assert client.post(endpoint,headers={'X-Control-Token':'fixture-access'},json=body('WHATSAPP_HUMAN')).status_code==403
        h={'X-Connector-Token':'fixture-connector-only'}
        result=client.post(endpoint,headers=h,json=body('WHATSAPP_HUMAN'))
        assert result.status_code==200,result.text
        assert result.json()['status']=='REJECTED_UNAUTHORIZED_SOURCE'
        assert client.get('/api/core/operations/snapshot',headers=h).status_code==403
        assert client.post('/api/controls/kill-switch',headers=h,json={}).status_code==403
        assert client.post(endpoint,headers=h,json=body()).status_code==403


def test_monitoring_uses_current_freshness_not_requested_activity_end(p4):
    ops=service(p4)
    ops.ingest(SourceSubmission.model_validate(body()))
    report=ops.report()
    assert report['portfolio']['status']=='OBSERVED_P2_INPUT'
    assert report['portfolio']['equity']=='100000'
    assert report['activity']['by_source']['MANUAL']['APPROVED']==1
    assert report['safety']['reserved_slots']==1
    p4.clock[0]+=timedelta(seconds=6)
    stale=ops.report(as_of=TIME)
    assert stale['portfolio']['status']=='STALE'
    assert stale['portfolio']['equity'] is None
    assert stale['safety']['reserved_slots']==1


def test_health_future_and_invalid_windows_rejected(p4):
    ops=service(p4)
    with pytest.raises(ValueError):
        ops.record_health(component='mt5',state='HEALTHY',observed_at=TIME+timedelta(seconds=1),
                          valid_until=TIME+timedelta(seconds=10),evidence_id='fixture')
    with pytest.raises(ValueError):
        ops.report(as_of=TIME+timedelta(seconds=1))
