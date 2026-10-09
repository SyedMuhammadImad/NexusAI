"""No terminal, credentials, operator database or network. All economic calls fake."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from core.rebuild.execution import ExecutionEngine
from core.rebuild.execution_contracts import Attestation, BrokerSnapshot, SubmissionResult
from core.rebuild.ledger import Ledger
from core.rebuild.lifecycle_service import LifecycleService
from core.rebuild.safety import SafetyEngine
from test_p2_safety import ACCOUNT, TIME, setup, intent, inputs, evaluate

D = Decimal


class Crash(BaseException):
    pass


class FakeBroker:
    scope = 'FIXTURE'

    def __init__(self):
        self.time = TIME
        self.data = inputs()
        self.calls = []
        self.commands = []
        self.orders, self.deals, self.positions = [], [], []
        self.exits = []
        self.outcome = 'ACKNOWLEDGED'
        self.fraction = D(1)
        self.deal_count = 1
        self.crash = None
        self.attestation_changes = {}
        self.complete = True
        self.snapshot_calls = 0
        self.on_snapshot = None

    def attest(self):
        values = dict(evidence_id='fixture-session', observed_at=self.time, account_key=ACCOUNT.key,
                      account_id=ACCOUNT.account_id,server=ACCOUNT.server,currency=ACCOUNT.currency,
                      mode='DEMO',scope='FIXTURE',session_id='fixture-session',connected=True,
                      trade_allowed=True,expert_allowed=True,hedging=True)
        values.update(self.attestation_changes)
        return Attestation(**values)

    def snapshot(self, since):
        self.snapshot_calls += 1
        if self.on_snapshot:
            self.on_snapshot(self)
        data = deepcopy(self.data)
        for p in self.positions:
            if not D(p['open_volume']):
                continue
            command = next(c for c in self.commands if 'order-'+c['attempt_id'] == p['opening_order_id'])
            data['account']['exposures'].append(dict(exposure_id=p['broker_position_id'],symbol=p['symbol'],
                direction=p['direction'],volume=p['open_volume'],stop_loss=p['stop_loss'],kind='POSITION',
                reservation_intent_id=command['intent_id']))
        return BrokerSnapshot(evidence_id='snapshot-'+str(self.snapshot_calls),observed_at=self.time,
                              attestation=self.attest(),history_since=since,complete=self.complete,
                              orders=self.orders,deals=self.deals,positions=self.positions,safety=data,
                              protective_exit_orders=self.exits)

    def fill(self, command, fraction=None, status=None):
        fraction = self.fraction if fraction is None else fraction
        self.commands.append(command) if command not in self.commands else None
        order_id, position_id = 'order-'+command['attempt_id'], 'position-'+command['attempt_id']
        volume = D(command['volume']) * fraction
        state = status or ('FILLED' if fraction==1 else 'PARTIALLY_FILLED' if fraction else 'PLACED')
        order = dict(evidence_id=order_id,observed_at=self.time,broker_order_id=order_id,
                     correlation=command['correlation'],magic=command['magic'],symbol=command['symbol'],
                     direction=command['direction'],entry_type=command['entry_type'],requested_volume=command['volume'],
                     filled_volume=str(volume),stop_loss=command['stop'],take_profit=command['nearest_tp'],status=state)
        self.orders = [o for o in self.orders if o['broker_order_id'] != order_id] + [order]
        if volume:
            self.deals = [d for d in self.deals if d['broker_order_id'] != order_id]
            for n in range(self.deal_count):
                self.deals.append(dict(evidence_id=f'deal-{order_id}-{n}',observed_at=self.time,
                    broker_deal_id=f'deal-{order_id}-{n}',broker_order_id=order_id,broker_position_id=position_id,
                    symbol=command['symbol'],direction=command['direction'],entry='IN',volume=str(volume/self.deal_count),
                    price=command['base_entry'],profit='0',commission='0',swap='0',fee='0'))
            self.positions = [p for p in self.positions if p['broker_position_id'] != position_id] + [dict(
                evidence_id=position_id,observed_at=self.time,broker_position_id=position_id,opening_order_id=order_id,
                symbol=command['symbol'],direction=command['direction'],open_volume=str(volume),
                stop_loss=command['stop'],take_profit=command['nearest_tp'])]
        return order_id

    def submit(self, command):
        self.calls.append(command)
        if self.crash == 'before':
            raise Crash()
        if self.outcome == 'REJECTED':
            order_id = None
        else:
            order_id = self.fill(command)
        if self.crash == 'after':
            raise Crash()
        if self.crash == 'timeout':
            raise TimeoutError('transport exception deliberately not persisted')
        return SubmissionResult(evidence_id='response-'+command['attempt_id'],observed_at=self.time,
                                attestation=self.attest(),outcome=self.outcome,broker_order_id=order_id,retcode=1)


def fixture(tmp_path, **intent_args):
    ledger, safety = setup(tmp_path)
    identity = intent(ledger, **intent_args)
    result = evaluate(safety, identity)
    assert result['decision']=='APPROVED', result
    request = safety.eligible_request(identity,'decision-one',current=TIME)['execution_request_id']
    broker = FakeBroker()
    engine = ExecutionEngine(safety, broker, clock=lambda:broker.time)
    return ledger, safety, engine, broker, request


def reservation(ledger):
    with ledger.connect() as conn:
        return dict(conn.execute('SELECT * FROM p2_reservations').fetchone())


def test_success_exact_lineage_and_restart_replay(tmp_path):
    ledger, safety, engine, broker, request = fixture(tmp_path)
    assert engine.submit(request)['state']=='FILLED'
    assert reservation(ledger)['state']=='CONVERTED'
    reopened = ExecutionEngine(SafetyEngine(Ledger(ledger.path,account=ACCOUNT),safety.config),broker,clock=lambda:TIME)
    for _ in range(3):
        assert reopened.submit(request)['state']=='FILLED'
    assert len(broker.calls)==1
    path = LifecycleService(ledger).trace('source-one')['lifecycles'][0]
    attempt = path['p3_attempts'][0]
    assert attempt['execution_request_id']==request
    assert attempt['intent_id']==path['intent']['intent_id']
    assert path['p2_execution_requests'][0]['decision_id']==path['safety_decisions'][0]['risk_decision_id']
    assert path['p3_orders'][0]['attempt_id']==attempt['attempt_id']
    assert path['p3_deals'][0]['broker_order_id']==path['p3_orders'][0]['broker_order_id']
    assert path['p3_deals'][0]['broker_position_id']==path['p3_positions'][0]['broker_position_id']
    assert D(json.loads(path['p3_orders'][0]['payload'])['requested_volume']) != D(str(path['intent']['requested_volume']))
    assert path['outcomes']==[]


def test_broker_rejection_releases_only_attested_result(tmp_path):
    ledger, _, engine, broker, request = fixture(tmp_path)
    broker.outcome = 'REJECTED'
    assert engine.submit(request)['state']=='REJECTED_BY_BROKER'
    assert reservation(ledger)['state']=='RELEASED'
    engine.submit(request)
    assert len(broker.calls)==1


def test_crash_before_started_safe_resume(tmp_path):
    ledger, safety, engine, broker, request = fixture(tmp_path)
    prepared = engine.prepare(request)
    assert prepared['state']=='NOT_SUBMITTED'
    restarted = ExecutionEngine(SafetyEngine(Ledger(ledger.path,account=ACCOUNT),safety.config),broker,clock=lambda:TIME)
    assert restarted.submit(request)['state']=='FILLED'
    assert len(broker.calls)==1


@pytest.mark.parametrize('moment', ['before','after'])
def test_crash_after_durable_start_never_resubmits(tmp_path, moment):
    ledger, safety, engine, broker, request = fixture(tmp_path)
    broker.crash=moment
    with pytest.raises(Crash):
        engine.submit(request)
    assert engine.get(request)['state']=='SUBMISSION_STARTED'
    assert reservation(ledger)['state']=='SUBMISSION_BEGUN'
    restarted = ExecutionEngine(SafetyEngine(Ledger(ledger.path,account=ACCOUNT),safety.config),broker,clock=lambda:TIME)
    assert restarted.submit(request)['state']==('FILLED' if moment=='after' else 'SUBMISSION_AMBIGUOUS')
    assert len(broker.calls)==1
    if moment=='before':
        assert reservation(ledger)['state']=='AMBIGUOUS'
        assert safety.expire(current=TIME+timedelta(days=1))==[]


@pytest.mark.parametrize('outcome,crash', [('AMBIGUOUS',None),('ACKNOWLEDGED','timeout')])
def test_ambiguous_response_resolves_only_with_broker_evidence(tmp_path, outcome, crash):
    ledger, _, engine, broker, request = fixture(tmp_path)
    broker.outcome,broker.crash=outcome,crash
    assert engine.submit(request)['state']=='FILLED'
    assert ledger.status()['halt']['state']=='HALTED'
    assert len(broker.calls)==1
    with ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM quarantine').fetchone()[0]>=1
        assert 'transport exception deliberately' not in str(conn.execute('SELECT payload FROM p3_events').fetchall())


def test_partial_multi_deal_and_cancel_remainder(tmp_path):
    ledger, _, engine, broker, request = fixture(tmp_path)
    broker.fraction=D('.5')
    broker.deal_count=2
    assert engine.submit(request)['state']=='PARTIALLY_FILLED'
    row=reservation(ledger)
    assert row['state']=='PARTIAL'
    assert D(row['filled_volume'])==D(row['volume'])/2
    broker.orders[0]['status']='CANCELLED'
    broker.orders[0]['observed_at']=TIME+timedelta(seconds=1)
    assert engine.reconcile()['status']=='RECONCILED'
    assert engine.get(request)['state']=='CANCELLED'
    assert reservation(ledger)['state']=='CONVERTED'
    engine.submit(request)
    assert len(broker.calls)==1
    with ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM p3_deals').fetchone()[0]==2


def test_pending_cancellation_releases_capacity(tmp_path):
    ledger, _, engine, broker, request = fixture(tmp_path,entry=99.9,entry_type='LIMIT')
    broker.fraction=D(0)
    assert engine.submit(request)['state']=='SUBMISSION_CONFIRMED'
    assert reservation(ledger)['state']=='SUBMISSION_BEGUN'
    broker.orders[0].update(status='CANCELLED',observed_at=TIME+timedelta(seconds=1))
    engine.reconcile()
    assert reservation(ledger)['state']=='RELEASED'


@pytest.mark.parametrize('field,value', [('mode','LIVE'),('account_id','wrong'),('account_key','wrong'),
    ('server','wrong'),('currency','EUR'),('scope','MT5_DEMO'),('connected',False),('trade_allowed',False),
    ('expert_allowed',False),('hedging',False),('observed_at',TIME-timedelta(seconds=6))])
def test_account_attestation_fail_closed(tmp_path,field,value):
    ledger, _, engine, broker, request = fixture(tmp_path)
    broker.attestation_changes[field]=value
    assert engine.submit(request)['state']=='NOT_SUBMITTED'
    assert broker.calls==[]
    assert ledger.status()['halt']['state']=='HALTED'


@pytest.mark.parametrize('failure', ['halt','expired','superseded','stale','drawdown','missing','risk_changed'])
def test_submission_revalidates_p2(tmp_path,failure):
    ledger, safety, engine, broker, request = fixture(tmp_path)
    if failure=='halt': ledger.halt('fixture halt')
    if failure=='expired': broker.time=TIME+timedelta(seconds=61)
    if failure=='superseded': safety.activate_configuration(safety.config,revision='2',operator_id='fixture',reason='fixture')
    if failure=='stale': broker.data['quotes']['XAUUSDm']['observed_at']=TIME-timedelta(seconds=4)
    if failure=='drawdown': broker.data['account']['equity']='92000'
    if failure=='missing': broker.complete=False
    if failure=='risk_changed': broker.data['instruments']['XAUUSDm']['commission_per_lot']='1'
    assert engine.submit(request)['state']=='NOT_SUBMITTED'
    assert broker.calls==[]


def test_halt_between_start_and_final_gate(tmp_path):
    ledger, _, engine, broker, request = fixture(tmp_path)
    original=engine._gate
    def gate(conn,attempt,snapshot,**kwargs):
        if kwargs.get('begun'):
            conn.execute("UPDATE halt_state SET state='HALTED',version=version+1 WHERE singleton=1")
        return original(conn,attempt,snapshot,**kwargs)
    engine._gate=gate
    assert engine.submit(request)['state']=='SUBMISSION_AMBIGUOUS'
    assert broker.calls==[]
    assert reservation(ledger)['state']=='AMBIGUOUS'


def test_halt_recovery_observes_but_never_sends(tmp_path):
    ledger, _, engine, broker, request = fixture(tmp_path)
    broker.crash='after'
    with pytest.raises(Crash): engine.submit(request)
    ledger.halt('recovery halt')
    assert engine.submit(request)['state']=='FILLED'
    assert ledger.status()['halt']['state']=='HALTED'
    assert len(broker.calls)==1


@pytest.mark.parametrize('change', ['unknown_order','unknown_position','deal_conflict','position_zero',
    'missing_deal','missing_position','wrong_order_id','overfill','changed_stop','unknown_exit'])
def test_reconciliation_mismatch_quarantines_without_local_close(tmp_path,change):
    ledger, _, engine, broker, request = fixture(tmp_path)
    engine.submit(request)
    if change=='unknown_order': broker.orders[0]['correlation']='external'
    if change=='unknown_position': broker.positions[0]['opening_order_id']='external'
    if change=='deal_conflict': broker.deals[0]['price']='1'
    if change=='position_zero': broker.positions[0]['open_volume']='0'
    if change=='missing_deal': broker.deals=[]
    if change=='missing_position': broker.positions=[]
    if change=='wrong_order_id': broker.orders[0]['broker_order_id']='different'
    if change=='overfill': broker.orders[0]['filled_volume']='100000'
    if change=='changed_stop': broker.positions[0]['stop_loss']='80'
    if change=='unknown_exit': broker.deals[0]['entry']='OUT'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'
    assert ledger.status()['halt']['state']=='HALTED'
    with ledger.connect() as conn:
        assert conn.execute('SELECT lifecycle_state FROM p3_positions').fetchone()[0]=='RECOVERY_REQUIRED'
        assert conn.execute('SELECT count(*) FROM trade_outcomes').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM quarantine').fetchone()[0]>0
    engine.submit(request)
    assert len(broker.calls)==1


def test_concurrent_replay_no_double_send(tmp_path):
    _, _, engine, broker, request = fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _:engine.submit(request),range(6)))
    # Recovery may conservatively HALT a racing request before send; never two calls.
    assert len(broker.calls)<=1
    assert engine.get(request)['started_at'] is not None


def test_atomic_projection_rollback(tmp_path):
    ledger, _, engine, broker, request = fixture(tmp_path)
    broker.crash='after'
    with pytest.raises(Crash): engine.submit(request)
    broker.deals[0]['volume']='0.001'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    with ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM p3_orders').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM p3_deals').fetchone()[0]==0
    assert reservation(ledger)['state']=='AMBIGUOUS'


def test_direct_sql_p1_request_cannot_enter_p3(tmp_path):
    ledger, _, _, _, _ = fixture(tmp_path)
    with pytest.raises(sqlite3.IntegrityError),ledger.transaction() as conn:
        conn.execute("INSERT INTO p3_attempts VALUES('bad','p1-fixture-request','bad','bad',1,'NOT_SUBMITTED',?,NULL,?,NULL,NULL)",(TIME.isoformat(),TIME.isoformat()))


def test_no_default_app_dispatch_or_runtime_import():
    import sys
    assert 'MetaTrader5' not in sys.modules
    assert 'legacy_application' not in sys.modules


def test_partial_then_additional_deal_full_fill(tmp_path):
    ledger, _, engine, broker, request = fixture(tmp_path)
    broker.fraction=D('.5')
    engine.submit(request)
    additional=deepcopy(broker.deals[0])
    additional.update(evidence_id='second-fill',broker_deal_id='second-fill',observed_at=TIME+timedelta(seconds=1))
    broker.deals.append(additional)
    broker.orders[0].update(filled_volume=broker.orders[0]['requested_volume'],status='FILLED',observed_at=TIME+timedelta(seconds=1))
    broker.positions[0].update(open_volume=broker.orders[0]['requested_volume'],observed_at=TIME+timedelta(seconds=1))
    assert engine.reconcile()['status']=='RECONCILED'
    assert reservation(ledger)['state']=='CONVERTED'
    with ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM p3_deals').fetchone()[0]==2


def test_same_symbol_independent_broker_positions_without_admission_stacking(tmp_path):
    ledger, safety, engine, broker, request = fixture(tmp_path)
    engine.submit(request)
    second = intent(ledger,'second')
    data=broker.snapshot(TIME).safety
    assert evaluate(safety,second,data,key='decision-second')['reason']=='SAME_INSTRUMENT_EXPOSURE'
    # Reconciliation fixture: two previously authorized, separately identified
    # requests. This SQL setup is NOT a production admission/adoption API.
    third = intent(ledger,'third')
    with ledger.transaction() as conn:
        conn.execute("UPDATE p2_reservations SET state='RELEASED' WHERE intent_id=?",(broker.calls[0]['intent_id'],))
    assert evaluate(safety,third,key='decision-third')['decision']=='APPROVED'
    other=safety.eligible_request(third,'decision-third',current=TIME)['execution_request_id']
    attempt=engine.prepare(other)
    command=dict(broker.calls[0],attempt_id=attempt['attempt_id'],execution_request_id=other,intent_id=third,
                 safety_decision_id='decision-third',correlation=attempt['correlation'],magic=attempt['magic'])
    with ledger.transaction() as conn:
        conn.execute("UPDATE p3_attempts SET state='SUBMISSION_STARTED',started_at=?,command=? WHERE attempt_id=?",(TIME.isoformat(),json.dumps(command),attempt['attempt_id']))
        conn.execute("UPDATE p2_reservations SET state='SUBMISSION_BEGUN' WHERE intent_id=?",(third,))
    broker.fill(command)
    assert engine.reconcile()['status']=='RECONCILED'
    with ledger.connect() as conn:
        records=conn.execute('SELECT broker_position_id,attempt_id FROM p3_positions').fetchall()
        assert len(records)==2 and len({r['attempt_id'] for r in records})==2
    assert len(broker.calls)==1  # No second admission through the executor.


def test_final_snapshot_detects_external_order(tmp_path):
    _, _, engine, broker, request=fixture(tmp_path)
    def inject(b):
        if b.snapshot_calls==2:
            attempt=engine.get(request)
            command=json.loads(attempt['command'])
            command.update(correlation='external',attempt_id='external')
            b.fill(command,D(0))
    broker.on_snapshot=inject
    assert engine.submit(request)['state']=='SUBMISSION_AMBIGUOUS'
    assert broker.calls==[]


def test_submission_deadline_and_drawdown_are_durable(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    original=broker.attest
    calls=0
    def slow_attest():
        nonlocal calls
        calls+=1
        if calls==3: broker.time=TIME+timedelta(seconds=4)
        return original()
    broker.attest=slow_attest
    assert engine.submit(request)['state']=='SUBMISSION_AMBIGUOUS'
    assert broker.calls==[]
    assert Ledger(ledger.path,account=ACCOUNT).status()['halt']['state']=='HALTED'


@pytest.mark.parametrize('direction,sl,tp', [('BUY',90.,130.),('SELL',110.,70.)])
def test_both_directions_exact_sized_volume(tmp_path,direction,sl,tp):
    ledger,_,engine,broker,request=fixture(tmp_path,direction=direction,sl=sl,tp=tp)
    assert engine.submit(request)['state']=='FILLED'
    command=broker.calls[0]
    assert command['direction']==direction
    assert command['base_entry']==('100' if direction=='BUY' else '99.9')
    assert command['volume']==reservation(ledger)['volume']


def test_repeated_snapshot_is_idempotent(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    engine.submit(request)
    snapshot=broker.snapshot(TIME)
    broker.snapshot=lambda since:snapshot
    engine.reconcile()
    with ledger.connect() as conn:
        before={t:conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('p3_events','p3_orders','p3_deals','p3_positions')}
    for _ in range(4): engine.reconcile()
    with ledger.connect() as conn:
        assert before=={t:conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in before}


@pytest.mark.parametrize('moment',['before-start','after-start','after-fill'])
def test_process_death_recovery(tmp_path,moment):
    db=tmp_path/'process'
    db.mkdir()
    observed=db/'broker-fixture.json'
    code=r'''
import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
sys.path.insert(0,sys.argv[2])
from test_p3_execution import fixture
ledger,safety,engine,broker,request=fixture(Path(sys.argv[3]))
if sys.argv[5]=='before-start':
    engine.prepare(request)
    os._exit(74)
original=broker.submit
def interrupted(command):
    if sys.argv[5]=='after-start': os._exit(75)
    original(command)
    snapshot=broker.snapshot(engine._time())
    Path(sys.argv[4]).write_text(snapshot.model_dump_json(),encoding='utf-8')
    os._exit(76)
broker.submit=interrupted
engine.submit(request)
'''
    backend=Path(__file__).resolve().parents[1]
    completed=subprocess.run([sys.executable,'-B','-c',code,str(backend),str(backend/'tests'),str(db),str(observed),moment],
                             env=dict(os.environ),capture_output=True,text=True,timeout=30)
    assert completed.returncode=={'before-start':74,'after-start':75,'after-fill':76}[moment],completed.stderr
    ledger,safety=setup(db)
    broker=FakeBroker()
    with ledger.connect() as conn:
        request=conn.execute('SELECT execution_request_id FROM p3_attempts').fetchone()[0]
        command=conn.execute('SELECT command FROM p3_attempts').fetchone()[0]
    if moment=='after-fill':
        snapshot=BrokerSnapshot.model_validate_json(observed.read_text(encoding='utf-8'))
        broker.orders=[o.model_dump() for o in snapshot.orders]
        broker.deals=[d.model_dump() for d in snapshot.deals]
        broker.positions=[p.model_dump() for p in snapshot.positions]
        broker.commands=[json.loads(command)]
    engine=ExecutionEngine(safety,broker,clock=lambda:TIME)
    state=engine.submit(request)['state']
    assert state==('SUBMISSION_AMBIGUOUS' if moment=='after-start' else 'FILLED')
    assert len(broker.calls)==(1 if moment=='before-start' else 0)


@pytest.mark.parametrize('field,value', [('price','101'),('volume','NaN'),('price','Infinity')])
def test_invalid_or_adverse_broker_fill_fail_safe(tmp_path,field,value):
    ledger,_,engine,broker,request=fixture(tmp_path)
    broker.crash='after'
    with pytest.raises(Crash):engine.submit(request)
    broker.deals[0][field]=value
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'


def test_explicit_app_fixture_composition_and_auth(tmp_path):
    from fastapi.testclient import TestClient
    from core.rebuild.application import create_app
    from core.rebuild.safety_contracts import SafetyConfiguration
    broker=FakeBroker()
    app=create_app(database_path=tmp_path/'app.sqlite',token='fixture-token',lifecycle_account=ACCOUNT,
                   fixture_mode=True,safety_configuration=SafetyConfiguration(approved_account_key=ACCOUNT.key,authorized_sources={'operator'}),
                   execution_adapter=broker,execution_clock=lambda:TIME)
    with TestClient(app) as client:
        ledger,safety=app.state.ledger,app.state.safety
        assert ledger.status()['halt']['state']=='HALTED'
        safety.reset_halt(inputs(),operator_id='fixture',reason='test only',current=TIME)
        identity=intent(ledger)
        assert evaluate(safety,identity)['decision']=='APPROVED'
        request=safety.eligible_request(identity,'decision-one',current=TIME)['execution_request_id']
        path=f'/api/core/lifecycle/requests/{request}/submit'
        assert client.post(path).status_code==403
        response=client.post(path,headers={'X-Control-Token':'fixture-token'})
        assert response.status_code==200,response.text
        assert response.json()['record']['state']=='FILLED'
        assert response.json()['scope']=='P3_FIXTURE_ONLY'
        assert response.json()['execution_enabled'] is False
        assert client.post('/api/core/lifecycle/reconcile',headers={'X-Control-Token':'fixture-token'}).status_code==200
        assert len(broker.calls)==1


def test_default_app_cannot_dispatch(tmp_path):
    from fastapi.testclient import TestClient
    from core.rebuild.application import create_app
    app=create_app(database_path=tmp_path/'disabled.sqlite',token='fixture-token')
    with TestClient(app) as client:
        for path in ('/api/core/lifecycle/requests/fixture-request/submit','/api/core/lifecycle/reconcile'):
            assert client.post(path,headers={'X-Control-Token':'fixture-token'}).status_code==423
        assert app.state.execution is None


def test_native_adapter_not_authorized_by_app_configuration(tmp_path):
    from core.rebuild.application import create_app
    broker=FakeBroker()
    broker.scope='MT5_DEMO'
    with pytest.raises(ValueError,match='fixture'):
        create_app(database_path=tmp_path/'disabled.sqlite',token='fixture-token',fixture_mode=True,execution_adapter=broker)


def test_rejection_contradicted_by_order_restores_full_ambiguous_capacity(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    broker.outcome='REJECTED'
    assert engine.submit(request)['state']=='REJECTED_BY_BROKER'
    assert reservation(ledger)['state']=='RELEASED'
    broker.fill(broker.calls[0])
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'
    assert engine.get(request)['state']=='SUBMISSION_AMBIGUOUS'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert len(broker.calls)==1


def protective_exit(broker, *, fraction=D(1), key='exit-1'):
    position=broker.positions[0]
    volume=D(position['open_volume'])*fraction
    broker.exits.append(dict(evidence_id=key,observed_at=TIME+timedelta(seconds=1),broker_order_id=key,
        broker_position_id=position['broker_position_id'],symbol=position['symbol'],
        direction='SELL' if position['direction']=='BUY' else 'BUY',reason='TP',
        requested_volume=str(volume),filled_volume=str(volume),status='FILLED'))
    broker.deals.append(dict(evidence_id='deal-'+key,observed_at=TIME+timedelta(seconds=1),
        broker_deal_id='deal-'+key,broker_order_id=key,broker_position_id=position['broker_position_id'],
        symbol=position['symbol'],direction=broker.exits[-1]['direction'],entry='OUT',volume=str(volume),
        price=position['take_profit'],profit='10',commission='-1',swap='0',fee='0'))
    remaining=D(position['open_volume'])-volume
    position.update(open_volume=str(remaining),observed_at=TIME+timedelta(seconds=1))
    if not remaining:
        position.update(confirmed_absent=True,absence_evidence_id='complete-broker-inventory')


@pytest.mark.parametrize('direction,sl,tp', [('BUY',90.,130.),('SELL',110.,70.)])
def test_protective_exit_requires_broker_deals_and_absence(tmp_path,direction,sl,tp):
    ledger,safety,engine,broker,request=fixture(tmp_path,direction=direction,sl=sl,tp=tp)
    engine.submit(request)
    protective_exit(broker)
    assert engine.reconcile()['status']=='RECONCILED'
    assert reservation(ledger)['state']=='RELEASED'
    path=LifecycleService(ledger).trace('source-one')['lifecycles'][0]
    assert path['p3_positions'][0]['lifecycle_state']=='CLOSED'
    assert path['p3_exit_deals'][0]['broker_position_id']==path['p3_positions'][0]['broker_position_id']
    assert path['p3_exit_orders'][0]['broker_order_id']==path['p3_exit_deals'][0]['broker_order_id']
    assert path['outcomes']==[]  # No P5 label/PnL computation.
    engine.submit(request)
    assert len(broker.calls)==1
    assert evaluate(safety,intent(ledger,'after-close'),key='after-close-decision')['decision']=='APPROVED'


def test_partial_protective_close_reduces_current_position_not_history(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    engine.submit(request)
    original=reservation(ledger)['volume']
    protective_exit(broker,fraction=D('.5'))
    assert engine.reconcile()['status']=='RECONCILED'
    assert reservation(ledger)['state']=='CONVERTED'
    assert D(reservation(ledger)['filled_volume'])==D(original)/2
    with ledger.connect() as conn:
        assert json.loads(conn.execute('SELECT payload FROM p3_orders').fetchone()[0])['filled_volume']==original


@pytest.mark.parametrize('missing',['absence','close_order','close_deal','excess','reason','wrong_position','wrong_direction'])
def test_unproven_close_never_releases(tmp_path,missing):
    ledger,_,engine,broker,request=fixture(tmp_path)
    engine.submit(request)
    protective_exit(broker)
    if missing=='absence':broker.positions[0].pop('absence_evidence_id')
    if missing=='close_order':broker.exits=[]
    if missing=='close_deal':broker.deals.pop()
    if missing=='excess':broker.deals[-1]['volume']='1000'
    if missing=='reason':broker.exits[0]['reason']='MANUAL'
    if missing=='wrong_position':broker.exits[0]['broker_position_id']='other'
    if missing=='wrong_direction':broker.exits[0]['direction']='BUY'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'
    with ledger.connect() as conn:
        assert conn.execute('SELECT lifecycle_state FROM p3_positions').fetchone()[0]!='CLOSED'
