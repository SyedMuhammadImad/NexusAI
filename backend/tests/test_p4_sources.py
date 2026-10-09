"""P4 fixtures: no network, credentials, operator stores or native broker."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.rebuild.ledger import Ledger
from core.rebuild.lifecycle_contracts import TradeIntent, SourceEvent, CanonicalSignal
from core.rebuild.lifecycle_service import LifecycleService
from core.rebuild.source_registry import SourceRule, SourceConfiguration, install, check_signal
from core.rebuild.source_ingestion import SourceSubmission, SourceIngestion
from core.rebuild.safety import SafetyEngine
from core.rebuild.safety_contracts import SafetyConfiguration
from core.rebuild.execution import ExecutionEngine
from core.rebuild.application import create_app
from test_p2_safety import ACCOUNT, TIME, inputs
from test_p3_execution import FakeBroker


@pytest.fixture
def p4(tmp_path,monkeypatch):
    clock=[TIME]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return clock[0]
    monkeypatch.setattr('core.rebuild.source_registry.datetime',Clock)
    rules=[SourceRule(source_type=t,source_id=t,execution_eligibility='P2_ONLY' if t in {'MANUAL','WHATSAPP_HUMAN'} else 'NONE',
                     **(dict(sender_ids={'teacher'},group_id='group') if t=='WHATSAPP_HUMAN' else {}))
           for t in ('MANUAL','WHATSAPP_HUMAN','NEXUSAI_STRATEGY','HISTORICAL_WHATSAPP','SCREENSHOT')]
    config=SourceConfiguration(sources=rules)
    ledger=Ledger(tmp_path/'p4.sqlite',account=ACCOUNT)
    service=SourceIngestion(ledger,config,clock=lambda:clock[0])
    safety=SafetyEngine(ledger,SafetyConfiguration(approved_account_key=ACCOUNT.key,authorized_sources={'MANUAL','WHATSAPP_HUMAN'}))
    safety.reset_halt(inputs(),operator_id='fixture',reason='fixture-only',current=TIME)
    return SimpleNamespace(**locals())


def body(kind='MANUAL',key='one',age=0):
    data=dict(source_type=kind,source_id=kind,message_id=key,original_timestamp=(TIME-timedelta(seconds=age)).isoformat(),
              timezone_evidence='UTC',provenance={'origin':'fixture'})
    if kind in {'WHATSAPP_HUMAN','HISTORICAL_WHATSAPP'}:
        data.update(raw_text='XAUUSDm\nBUY\nCurrent rate: 100\nStoploss: 90\nTP: 130')
    else:
        data['signal']=dict(instrument='XAUUSDm',direction='BUY',entry_type='MARKET',entry=100.,stop_loss=90.,take_profit=[130.])
    if kind=='WHATSAPP_HUMAN': data.update(sender_id='teacher',group_id='group')
    if kind=='NEXUSAI_STRATEGY': data.update(strategy_id='research-only',strategy_version='v1')
    if kind=='SCREENSHOT': data.update(evidence_ref='sha256:fixture-image-not-loaded')
    return data


def ingest(s,data=None): return s.service.ingest(SourceSubmission.model_validate(data or body()))


def intent(s,record,key='client-one'):
    with s.ledger.connect() as conn:
        signal=json.loads(conn.execute('SELECT payload FROM signals WHERE signal_id=?',(record['signal_id'],)).fetchone()[0])
    return s.ledger.create_intent(TradeIntent(client_order_id=key,signal_id=signal['signal_id'],symbol=signal['symbol'],
        direction=signal['direction'],entry=signal['entry'],entry_type=signal['entry_type'],volume=.01,
        stop_loss=signal['stop_loss'],take_profit=signal['take_profit'][0],take_profit_targets=signal['take_profit'],
        requested_risk_pct=signal.get('requested_risk_pct')))


@pytest.mark.parametrize('entry_type,entry',[('MARKET',None),('MARKET',100.),('LIMIT',100.)])
def test_manual_valid_semantics_and_p2(p4,entry_type,entry):
    data=body(); data['signal'].update(entry_type=entry_type,entry=entry)
    r=ingest(p4,data)
    assert r['status']=='VALIDATED',r
    assert r['execution_eligibility']=='P2_ONLY'
    i=intent(p4,r)
    decision=p4.safety.evaluate(i['intent_id'],'decision-one',inputs(),current=TIME)
    assert decision['decision']=='APPROVED',decision
    req=p4.safety.eligible_request(i['intent_id'],'decision-one',current=TIME)
    assert req['status']=='ELIGIBLE_NOT_SUBMITTED' if 'status' in req else req['state']=='ELIGIBLE_NOT_SUBMITTED'


@pytest.mark.parametrize('field,value',[('direction','HOLD'),('stop_loss',None),('take_profit',[]),('stop_loss',140),
    ('entry',float('nan')),('stop_loss',float('inf')),('entry_type','STOP'),('take_profit',[80.])])
def test_manual_malformed_explicit_rejection(p4,field,value):
    d=body(); d['signal'][field]=value
    with pytest.raises(ValueError): ingest(p4,d)


def test_limit_requires_entry(p4):
    d=body(); d['signal'].update(entry_type='LIMIT',entry=None)
    with pytest.raises(ValueError): ingest(p4,d)


@pytest.mark.parametrize('age,eligible',[(0,True),(600,True),(600.001,False),(601,False)])
def test_whatsapp_freshness_boundary(p4,age,eligible):
    r=ingest(p4,body('WHATSAPP_HUMAN',age=age))
    assert r['signal_id']
    assert (r['execution_eligibility']=='P2_ONLY')==eligible
    if eligible: assert intent(p4,r)
    else:
        with pytest.raises(ValueError): intent(p4,r)


@pytest.mark.parametrize('timestamp,evidence',[("10/09/26 10:00",'UTC'),(TIME.replace(tzinfo=None).isoformat(),'UTC'),
    (TIME.isoformat(),'+05:00')])
def test_ambiguous_time_preserved_without_signal(p4,timestamp,evidence):
    d=body('WHATSAPP_HUMAN'); d.update(original_timestamp=timestamp,timezone_evidence=evidence)
    r=ingest(p4,d)
    assert r['reason']=='TIME_UNRESOLVED' and r['signal_id'] is None
    with p4.ledger.connect() as c:
        event=json.loads(c.execute('SELECT payload FROM source_events').fetchone()[0])
    assert event['original_timestamp']==timestamp and event['timezone_evidence']==evidence


def test_future_timestamp_rejects(p4):
    with pytest.raises(ValueError): ingest(p4,body('WHATSAPP_HUMAN',age=-1))


@pytest.mark.parametrize('change',[{'source_id':'unknown'},{'sender_id':'intruder'},{'group_id':'other'}])
def test_whatsapp_unauthorized(p4,change):
    d=body('WHATSAPP_HUMAN'); d.update(change)
    with pytest.raises(ValueError): ingest(p4,d)


def test_raw_and_parser_failure_preserved(p4):
    d=body('WHATSAPP_HUMAN'); d['raw_text']='Not a trading instruction'
    r=ingest(p4,d)
    assert r['reason']=='PARSER_REJECTED'
    with p4.ledger.connect() as c:
        event=json.loads(c.execute('SELECT payload FROM source_events').fetchone()[0])
    assert event['raw_text']==d['raw_text'] and event['sender_id']=='teacher'
    assert event['metadata']['group_id']=='group'


@pytest.mark.parametrize('kind',['MANUAL','WHATSAPP_HUMAN','NEXUSAI_STRATEGY','HISTORICAL_WHATSAPP','SCREENSHOT'])
def test_all_sources_canonical_replay(p4,kind):
    d=body(kind)
    first=ingest(p4,d); second=ingest(p4,d)
    assert first==second and first['signal_id'],first
    with p4.ledger.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM source_events').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM signals').fetchone()[0]==1


@pytest.mark.parametrize('kind',['NEXUSAI_STRATEGY','HISTORICAL_WHATSAPP','SCREENSHOT'])
def test_research_firewall_domain_and_registry(p4,kind):
    r=ingest(p4,body(kind))
    assert r['execution_eligibility']=='NONE'
    with pytest.raises(ValueError): intent(p4,r)
    with pytest.raises(ValueError): SourceRule(source_type=kind,source_id=kind,execution_eligibility='P2_ONLY')
    trace=LifecycleService(p4.ledger).trace(r['source_event_id'])
    assert trace['lifecycles']==[]
    if kind=='NEXUSAI_STRATEGY':
        metadata=json.loads(trace['source_event']['payload'])['metadata']
        assert (metadata['strategy_id'],metadata['strategy_version'])==('research-only','v1')


def test_conflict_and_distinct_signals(p4):
    first=ingest(p4)
    d=body(); d['signal']['take_profit']=[140.]
    with pytest.raises(ValueError): ingest(p4,d)
    second=ingest(p4,body(key='two',age=1))
    assert first['signal_id']!=second['signal_id']
    assert intent(p4,first)['intent_id']!=intent(p4,second,'client-two')['intent_id']


def test_concurrent_replay(p4):
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(lambda _:ingest(p4),range(8)))
    assert len({r['signal_id'] for r in records})==1


def test_crash_after_source_commit_restart(p4,monkeypatch):
    def crash(*args): raise RuntimeError('fixture crash')
    monkeypatch.setattr(p4.service.lifecycle,'validate_source',crash)
    with pytest.raises(RuntimeError): ingest(p4)
    reopened=SourceIngestion(Ledger(p4.ledger.path,account=ACCOUNT),p4.config,clock=lambda:TIME)
    r=reopened.ingest(SourceSubmission.model_validate(body()))
    assert r['signal_id']
    with p4.ledger.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM source_events').fetchone()[0]==1


def test_freshness_rechecked_at_request_not_just_ingest(p4):
    r=ingest(p4,body('WHATSAPP_HUMAN',age=599))
    i=intent(p4,r)
    assert p4.safety.evaluate(i['intent_id'],'decision-one',inputs(),current=TIME)['decision']=='APPROVED'
    with pytest.raises(ValueError): p4.safety.eligible_request(i['intent_id'],'decision-one',current=TIME+timedelta(seconds=2))


def test_registry_revision_changes_window_without_rewriting_event(p4):
    r=ingest(p4,body('WHATSAPP_HUMAN',age=650))
    assert r['execution_eligibility']=='NONE'
    rules=[x.model_copy(update={'freshness_seconds':700}) if x.source_type=='WHATSAPP_HUMAN' else x for x in p4.config.sources]
    install(p4.ledger,SourceConfiguration(revision=2,sources=rules))
    i=intent(p4,r)
    assert p4.safety.evaluate(i['intent_id'],'decision-two',inputs(),current=TIME)['decision']=='APPROVED'
    assert ingest(p4,body('WHATSAPP_HUMAN',age=650))['source_event_id']==r['source_event_id']
    with pytest.raises(ValueError): install(p4.ledger,p4.config)


def test_halt_and_p2_risk_no_source_bypass(p4):
    d=body(); d['signal']['requested_risk_pct']=1
    i=intent(p4,ingest(p4,d))
    assert p4.safety.evaluate(i['intent_id'],'risk-reject',inputs(),current=TIME)['decision']=='REJECTED'
    p4.ledger.halt('fixture stop')
    i2=intent(p4,ingest(p4,body(key='two')),'client-two')
    assert p4.safety.evaluate(i2['intent_id'],'halt-reject',inputs(),current=TIME)['reason']=='HALTED'


def test_direct_source_and_forged_signal_rejected(p4):
    r=ingest(p4)
    with p4.ledger.connect() as c:
        event=SourceEvent.model_validate_json(c.execute('SELECT payload FROM source_events').fetchone()[0])
        signal=CanonicalSignal.model_validate_json(c.execute('SELECT payload FROM signals').fetchone()[0])
    with pytest.raises(ValueError): LifecycleService(p4.ledger).save_source(event.model_copy(update={'source_id':'unregistered'}))
    with pytest.raises(ValueError): p4.ledger.save_signal(signal.model_copy(update={'take_profit':(150.,)}))


def test_broker_hard_block_survives_approval_reset_and_restart(p4):
    i=intent(p4,ingest(p4))
    assert p4.safety.evaluate(i['intent_id'],'decision-one',inputs(),current=TIME)['decision']=='APPROVED'
    p4.safety.eligible_request(i['intent_id'],'decision-one',current=TIME)
    broker=FakeBroker()
    with pytest.raises(ValueError,match='HARD_DISABLED'): ExecutionEngine(p4.safety,broker)
    assert not broker.calls
    reopened=Ledger(p4.ledger.path,account=ACCOUNT)
    with pytest.raises(ValueError): ExecutionEngine(SafetyEngine(reopened,p4.safety.config),broker)
    with pytest.raises(ValueError): create_app(token='fixture',source_configuration=p4.config,execution_adapter=broker)


def test_authenticated_ingestion_and_redacted_validation(p4,tmp_path):
    app=create_app(database_path=tmp_path/'api.sqlite',token='synthetic-token',lifecycle_account=ACCOUNT,
                   source_configuration=p4.config,source_clock=lambda:TIME)
    with TestClient(app) as client:
        assert client.post('/api/core/sources/ingest',json=body()).status_code==403
        headers={'x-control-token':'synthetic-token'}
        response=client.post('/api/core/sources/ingest',json=body(),headers=headers)
        assert response.status_code==200,response.text
        bad=body(); bad['signal']['direction']='private-input-not-for-response'
        response=client.post('/api/core/sources/ingest',json=bad,headers=headers)
        assert response.status_code==422 and 'private-input' not in response.text
        assert client.post('/api/core/lifecycle/requests/fixture-request/submit',headers=headers).status_code==423


def test_disabled_and_unknown_manual_sources(p4):
    d=body(); d['source_id']='unknown'
    with pytest.raises(ValueError): ingest(p4,d)
    rules=[x.model_copy(update={'enabled':False}) if x.source_type=='MANUAL' else x for x in p4.config.sources]
    install(p4.ledger,SourceConfiguration(revision=2,sources=rules))
    with pytest.raises(ValueError): ingest(p4)


def test_source_revision_invalidates_unused_approval(p4):
    i=intent(p4,ingest(p4))
    assert p4.safety.evaluate(i['intent_id'],'decision-one',inputs(),current=TIME)['decision']=='APPROVED'
    install(p4.ledger,SourceConfiguration(revision=2,sources=p4.config.sources))
    with pytest.raises(ValueError):
        p4.safety.eligible_request(i['intent_id'],'decision-one',current=TIME)


def test_screenshot_reference_without_extraction(p4):
    d=body('SCREENSHOT'); del d['signal']
    r=ingest(p4,d)
    assert r['signal_id'] is None and r['execution_eligibility']=='NONE'
    with p4.ledger.connect() as c:
        event=json.loads(c.execute('SELECT payload FROM source_events').fetchone()[0])
    assert event['metadata']['evidence_ref']==d['evidence_ref']
    assert event['metadata']['parser_version']=='deterministic_v3_p2'


@pytest.mark.parametrize('provenance',[{'origin':''},{'':'fixture'},{'parser_version':'fake'}])
def test_invalid_provenance_rejected(p4,provenance):
    d=body(); d['provenance']=provenance
    with pytest.raises(ValueError): ingest(p4,d)


def test_strategy_cannot_claim_qualification():
    with pytest.raises(ValueError):
        SourceRule(source_type='NEXUSAI_STRATEGY',source_id='strategy',qualification='QUALIFIED')


def test_preexisting_engine_cannot_bypass_persistent_block(tmp_path):
    from test_p3_execution import fixture
    ledger,safety,engine,broker,request=fixture(tmp_path)
    install(ledger,SourceConfiguration())
    with pytest.raises(sqlite3.IntegrityError,match='P4_BROKER_HARD_DISABLED'):
        engine.submit(request)
    with ledger.connect() as c:
        with pytest.raises(ValueError,match='P4_BROKER_HARD_DISABLED'):
            engine._snapshot(c)
        with pytest.raises(sqlite3.IntegrityError):
            c.execute('DELETE FROM p4_source_configuration')
        assert c.execute('SELECT COUNT(*) FROM p3_attempts').fetchone()[0]==0
    assert broker.calls==[] and broker.snapshot_calls==0
