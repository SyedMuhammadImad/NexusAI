"""Credential-free completion tests. Never import a native session or broker."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal as D
import json
from pathlib import Path
import subprocess

import pytest

from core.rebuild.ledger import Ledger
from core.rebuild.monitoring import health_coverage, execution_lineage, source_counters
from core.rebuild.operations import Operations, SOURCE_TYPES
from core.rebuild.operator_verification import VerificationLedger
from core.rebuild.qualification_basis import QualificationEvidence, qualification_basis, EPOCH
from core.rebuild.strategy_observer import BrokerCandle, StrategyObserver, normalize_closed_rates
from core.rebuild.operations import DeploymentCommand
from test_p4_sources import p4
from core.rebuild.host_attestation import validate_receipt, VERSION as HOST_VERSION
from test_p2_safety import TIME, ACCOUNT, inputs
from test_p3_execution import FakeBroker, fixture


def evidence(**changes):
    body = dict(attestation=FakeBroker().attest(), observed_at=TIME, equity=100000,
        history_from=EPOCH, history_complete=True, history_evidence_id='fixture-complete-history',
        ever_traded=False, inventory_complete=True, inventory_evidence_id='fixture-inventory',
        cash_flow_total=100000, cash_flow_evidence_id='fixture-opening-deposit')
    body.update(changes)
    return QualificationEvidence(**body)


def test_new_qualification_basis_has_actual_start_not_midnight(tmp_path):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    basis = qualification_basis(ledger, evidence(), current=TIME)
    assert basis.day_start.hour == 0 and basis.observed_at == TIME
    assert basis.day_equity == basis.week_equity == basis.high_water_equity == 100000
    with ledger.connect() as conn:
        payload = json.loads(conn.execute("SELECT payload FROM audit_events WHERE event_type='P3_QUALIFICATION_BASELINE'").fetchone()[0])
        assert payload['qualification_started_at'] == TIME.isoformat()
        assert payload['period_basis'] == 'QUALIFICATION_START_THEN_EVIDENCED_UTC_ROLLOVERS'
    assert ledger.status()['halt']['state'] == 'HALTED'


@pytest.mark.parametrize('change', [dict(history_complete=False), dict(history_from=TIME),
    dict(inventory_complete=False), dict(ever_traded=True),dict(open_position_ids=['external']),
    dict(pending_order_ids=['external']),dict(observed_at=TIME-timedelta(seconds=6))])
def test_new_account_initialization_is_not_an_escape_from_missing_evidence(tmp_path, change):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    with pytest.raises(ValueError): qualification_basis(ledger, evidence(**change), current=TIME)
    with ledger.connect() as conn:
        assert conn.execute("SELECT count(*) FROM audit_events WHERE event_type='P3_QUALIFICATION_BASELINE'").fetchone()[0] == 0


def test_initialization_rejects_ordinary_ledger_and_account_mismatch(tmp_path):
    with pytest.raises(ValueError):
        qualification_basis(Ledger(tmp_path/'ordinary.sqlite', account=ACCOUNT), evidence(), current=TIME)
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    bad = FakeBroker().attest().model_copy(update={'account_id':'different'})
    with pytest.raises(ValueError): qualification_basis(ledger, evidence(attestation=bad), current=TIME)


def test_basis_atomic_retry_restart_and_no_loss_reset(tmp_path):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    with ThreadPoolExecutor(4) as pool:
        values = list(pool.map(lambda _:qualification_basis(ledger,evidence(),current=TIME),range(8)))
    assert len({v.evidence_id for v in values}) == 1
    with ledger.connect() as conn:
        assert conn.execute("SELECT count(*) FROM audit_events WHERE event_type='P3_QUALIFICATION_BASELINE'").fetchone()[0] == 1
    reopened = VerificationLedger.resume(ledger.path.parent.name, ACCOUNT, workspace=tmp_path)
    later = TIME+timedelta(seconds=1)
    attestation = FakeBroker().attest().model_copy(update={'observed_at':later})
    basis = qualification_basis(reopened,evidence(observed_at=later,attestation=attestation,
        equity=98000,ever_traded=True),current=later)
    assert basis.day_equity == basis.week_equity == basis.high_water_equity == 100000
    with pytest.raises(ValueError): qualification_basis(reopened,evidence(),current=TIME)


def test_cash_flow_adjustment_and_exact_evidenced_rollover(tmp_path):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    qualification_basis(ledger,evidence(),current=TIME)
    tomorrow = (TIME+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    later = tomorrow+timedelta(seconds=1)
    attestation = FakeBroker().attest().model_copy(update={'observed_at':later})
    sample = evidence(observed_at=later,attestation=attestation,equity=100900,cash_flow_total=101000)
    with pytest.raises(ValueError,match='ROLLOVER_EVIDENCE_MISSING'):
        qualification_basis(ledger,sample,current=later)
    sample = evidence(observed_at=later,attestation=attestation,equity=100900,cash_flow_total=101000,
        rollovers=[dict(observed_at=tomorrow,equity=99900,cash_flow_total=100000,evidence_id='fixture-midnight')])
    basis = qualification_basis(ledger,sample,current=later)
    assert basis.day_equity == 100900
    assert basis.high_water_equity == 101000
    assert basis.week_equity == 101000


def test_missing_health_is_unknown_and_overlap_never_double_counts(tmp_path):
    ledger = Ledger(tmp_path/'monitor.sqlite',account=ACCOUNT)
    operations = Operations(ledger,clock=lambda:TIME)
    start=TIME-timedelta(seconds=100)
    for offset,state in [(0,'HEALTHY'),(10,'DISCONNECTED'),(50,'HEALTHY')]:
        when=start+timedelta(seconds=offset)
        operations.record_health(component='mt5',state=state,observed_at=when,
            valid_until=when+timedelta(seconds=20),evidence_id='fixture-'+str(offset))
    with ledger.connect() as conn:
        report=health_coverage(conn,start,TIME,['mt5','whatsapp'])
    assert report['mt5']['seconds']['HEALTHY']==30
    assert report['mt5']['seconds']['DISCONNECTED']==20
    assert report['mt5']['seconds']['UNKNOWN']==50
    assert report['mt5']['healthy_fraction']==.3
    assert report['whatsapp']['coverage_fraction']==0


def test_simultaneous_conflicting_health_is_ambiguous(tmp_path):
    ledger=Ledger(tmp_path/'health.sqlite',account=ACCOUNT)
    operations=Operations(ledger,clock=lambda:TIME)
    for state in ['HEALTHY','ERROR']:
        operations.record_health(component='mt5',state=state,observed_at=TIME-timedelta(seconds=10),
            valid_until=TIME+timedelta(seconds=10),evidence_id=state)
    with ledger.connect() as conn:
        report=health_coverage(conn,TIME-timedelta(seconds=10),TIME,['mt5'])['mt5']
    assert report['seconds']['AMBIGUOUS']==10 and report['healthy_fraction']==0


def test_exact_lineage_and_executed_counts_require_deals(tmp_path):
    ledger,safety,engine,broker,request=fixture(tmp_path)
    with ledger.connect() as conn:
        counts=source_counters(conn,TIME-timedelta(seconds=1),TIME,SOURCE_TYPES)
        assert counts['counts']['MANUAL']['executed']==0
    engine.submit(request)
    with ledger.connect() as conn:
        lineage=execution_lineage(conn)
        counts=source_counters(conn,TIME-timedelta(seconds=1),TIME,SOURCE_TYPES)
    assert len(lineage)==1 and lineage[0]['execution_request_id']==request
    assert lineage[0]['source_event_id'] and lineage[0]['signal_id'] and lineage[0]['risk_decision_id']
    assert len(lineage[0]['broker_deal_ids'])==len(lineage[0]['broker_position_ids'])==1
    assert counts['counts']['MANUAL']['executed']==1
    report=Operations(ledger,clock=lambda:TIME).report()
    assert report['scope']=='FIXTURE' and report['execution']['lineage']==lineage
    assert report['broker_execution']=='HARD_DISABLED'


def bars(account=ACCOUNT, count=22):
    boundary=TIME.replace(minute=0,second=0,microsecond=0)
    result=[]
    for n in range(count):
        opened=boundary-timedelta(hours=count-n)
        close=103 if n==count-1 else 100
        result.append(BrokerCandle(provider=account.evidence_source,account_key=account.key,
            broker_symbol='XAUUSDm',instrument='XAUUSD',timeframe='1H',opened=opened,
            closed=opened+timedelta(hours=1),open=close,high=close+1,low=close-1,
            close=close,volume=20,source_ref='fixture-bar-'+str(n)))
    return result


def deployment(ledger,strategy='p6-07'):
    return Operations(ledger,clock=lambda:TIME).deploy(DeploymentCommand(strategy_id=strategy,
        instrument='XAUUSD',timeframe='1H'))['deployment_id']


def test_closed_strategy_checkpoint_and_canonical_firewall(p4):
    identity=deployment(p4.ledger)
    worker=StrategyObserver(p4.ledger,clock=lambda:TIME,sources=p4.service,source_id='NEXUSAI_STRATEGY')
    result=worker.evaluate(identity,bars())
    assert len(result['evaluations'])==22
    assert result['evaluations'][-1]['candidate']['direction']=='BUY'
    assert result['canonical_candidates'][0]['status']=='VALIDATED'
    assert result['canonical_candidates'][0]['execution_eligibility']=='NONE'
    assert result['p2_routing']=='BLOCKED_BY_EXISTING_RESEARCH_SOURCE_POLICY'
    again=StrategyObserver(p4.ledger,clock=lambda:TIME,sources=p4.service,
        source_id='NEXUSAI_STRATEGY').evaluate(identity,bars())
    assert result['canonical_candidates']==again['canonical_candidates']
    with p4.ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM signals').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM p3_attempts').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM v1_deployment_events').fetchone()[0]==23
    report=Operations(p4.ledger,clock=lambda:TIME).report()
    assert report['deployments'][0]['evaluation_count']==22
    assert report['deployments'][0]['candle_provider']=='FIXTURE'


@pytest.mark.parametrize('strategy',['p6-01','p6-02','p6-04','p6-05','p6-07'])
def test_five_frozen_rules_restart_replay_and_concurrent_evaluation(tmp_path,strategy):
    ledger=Ledger(tmp_path/'strategy.sqlite',account=ACCOUNT)
    identity=deployment(ledger,strategy)
    def run(_): return StrategyObserver(ledger,clock=lambda:TIME).evaluate(identity,bars())
    with ThreadPoolExecutor(3) as pool: list(pool.map(run,range(3)))
    with ledger.connect() as conn:
        events=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM v1_deployment_events')]
        assert sum(p.get('kind')=='CLOSED_BAR_EVALUATED' for p in events)==22
    changed=bars();changed[-1]=changed[-1].model_copy(update={'source_ref':'revised-native-evidence'})
    with pytest.raises(ValueError,match='REVISED_BROKER_BAR'):
        StrategyObserver(ledger,clock=lambda:TIME).evaluate(identity,changed)


def test_gap_reset_no_synthetic_repair_and_no_forming_bar(tmp_path):
    ledger=Ledger(tmp_path/'gap.sqlite',account=ACCOUNT)
    identity=deployment(ledger)
    worker=StrategyObserver(ledger,clock=lambda:TIME)
    data=bars(); result=worker.evaluate(identity,data[:20]+data[21:])
    assert result['evaluations'][-1]['gap_reset']
    assert result['evaluations'][-1]['warmup_count']==1
    assert result['evaluations'][-1]['candidate'] is None
    future=bars()[-1].model_copy(update={'opened':TIME.replace(minute=0,second=0,microsecond=0),
        'closed':TIME.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)})
    with pytest.raises(ValueError,match='FORMING_BAR'):
        worker.evaluate(identity,[future])


def test_rate_normalizer_keeps_bid_tick_semantics_and_drops_forming_bar():
    boundary=TIME.replace(minute=0,second=0,microsecond=0)
    rows=[dict(time=int((boundary-timedelta(hours=1-n)).timestamp()),open=100,high=101,low=99,
        close=100,tick_volume=4,spread=1,real_volume=0) for n in range(2)]
    result=normalize_closed_rates(rows,account=ACCOUNT,symbol='XAUUSDm',timeframe='1H',
        current=TIME,chart_basis='BID',evidence_ref='fixture-native-rates')
    assert len(result)==1 and result[0].price_basis=='BID' and result[0].volume_unit=='TICK_COUNT'
    for bad in [rows+rows, list(reversed(rows))]:
        with pytest.raises(ValueError): normalize_closed_rates(bad,account=ACCOUNT,symbol='XAUUSDm',
            timeframe='1H',current=TIME,chart_basis='BID',evidence_ref='fixture')
    with pytest.raises(ValueError,match='SEMANTICS_UNPROVEN'):
        normalize_closed_rates(rows,account=ACCOUNT,symbol='XAUUSDm',timeframe='1H',
            current=TIME,chart_basis='LAST',evidence_ref='fixture')


def receipt(**changes):
    value=dict(version=HOST_VERSION,nonce='a'*32,account_key=ACCOUNT.key,run_id='fixture-run',
        python_pid=123,started_at=TIME.isoformat(),completed_at=TIME.isoformat(),
        host=dict(dedicated_identity=True,session_zero=True,non_admin=True,
            exclusive_processes=True,protected_acl=True,terminal_pid=456))
    value.update(changes)
    return value


def check_receipt(value,current=TIME):
    return validate_receipt(value,nonce='a'*32,account_key=ACCOUNT.key,run_id='fixture-run',
        python_pid=123,current=current)


@pytest.mark.parametrize('change',[dict(nonce='b'*32),dict(account_key='other'),
    dict(run_id='other'),dict(python_pid=124),dict(python_pid=True),dict(version='unknown'),
    dict(password='fixture-must-reject-extra'),dict(started_at=(TIME-timedelta(seconds=6)).isoformat()),
    dict(completed_at=(TIME+timedelta(seconds=1)).isoformat()),dict(started_at=TIME.replace(tzinfo=None).isoformat()),
    dict(host=dict(receipt()['host'],non_admin=1))])
def test_privileged_receipt_cannot_rebind_replay_or_weaken_schema(change):
    with pytest.raises(ValueError): check_receipt(receipt(**change))


def test_negative_privileged_receipt_remains_a_negative_host_gate():
    result=check_receipt(receipt(host=dict(receipt()['host'],protected_acl=False)))
    assert result['protected_acl'] is False
    assert check_receipt(receipt())['non_admin'] is True


def test_windows_scripts_parse_and_default_provision_never_mutates():
    root=Path(__file__).resolve().parents[2]
    scripts=['p3_system_attestor.ps1','p3_attestor_client.ps1','p3_operator_host_probe.ps1','provision_p3_operator.ps1']
    for name in scripts:
        path=root/'scripts'/name
        command=f"$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$t,[ref]$e);if($e.Count){{exit 2}}"
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,timeout=15)
        assert result.returncode==0, name
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',
        str(root/'scripts/provision_p3_operator.ps1')],capture_output=True,text=True,timeout=15)
    assert result.returncode==0 and json.loads(result.stdout)['mode']=='PLAN_ONLY'
    assert json.loads(result.stdout)['broker_actions']==0
