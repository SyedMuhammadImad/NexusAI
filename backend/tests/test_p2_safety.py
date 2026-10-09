from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import sqlite3

import pytest

from core.rebuild.ledger import DemoAccount, Ledger
from core.rebuild.lifecycle_contracts import SourceEvent, CanonicalSignal, TradeIntent
from core.rebuild.lifecycle_service import LifecycleService
from core.rebuild.safety import SafetyEngine
from core.rebuild.safety_contracts import SafetyConfiguration

ACCOUNT = DemoAccount(account_id="p2-fixture", server="fixture", currency="USD", evidence_source="FIXTURE")
TIME = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)


def setup(tmp_path):
    ledger = Ledger(tmp_path / "p2.sqlite", account=ACCOUNT)
    config = SafetyConfiguration(approved_account_key=ACCOUNT.key, authorized_sources={"operator"})
    engine = SafetyEngine(ledger, config)
    with ledger.transaction() as conn:
        conn.execute("UPDATE halt_state SET state='ACTIVE' WHERE singleton=1")
    return ledger, engine


def intent(ledger, key="one", symbol="XAUUSDm", direction="BUY", entry=None, entry_type="MARKET", risk=None, tp=130., sl=90., source="MANUAL"):
    svc = LifecycleService(ledger)
    event = SourceEvent(source_event_id="source-" + key, source_type=source, source_id="operator",
                        source_message_id=key, raw_text="fixture only", original_timestamp=TIME.isoformat(),
                        timezone_evidence="UTC", source_time_utc=TIME, received_at=TIME)
    svc.save_source(event)
    signal = CanonicalSignal(signal_id="signal-" + key, source_type=source, source_id="operator", source_message_id=key,
                             source_event_id=event.source_event_id, source_timestamp=TIME.timestamp(),
                             received_timestamp=TIME.timestamp(), parsed_timestamp=TIME.timestamp(),
                             symbol=symbol, direction=direction, entry=entry, entry_type=entry_type,
                             stop_loss=sl, take_profit=(tp,), requested_risk_pct=risk,
                             raw_source_hash=hashlib.sha256(b"fixture only").hexdigest())
    ledger.save_signal(signal)
    request = TradeIntent(client_order_id="client-" + key, signal_id=signal.signal_id, symbol=symbol,
                          direction=direction, volume=.01, entry=entry, entry_type=entry_type,
                          stop_loss=sl, take_profit=tp, take_profit_targets=(tp,), requested_risk_pct=risk)
    return svc.create_intent(request)["intent_id"]


def inputs():
    day = TIME.replace(hour=0)
    metadata = dict(evidence_id="instrument", observed_at=TIME, account_currency="USD", calculation="LINEAR_ACCOUNT_CURRENCY",
                    tick_size="0.01", value_per_price_unit_per_lot="1", notional_per_price_unit_per_lot="1",
                    margin_per_lot="1", commission_per_lot="0", conversion_at=TIME,
                    volume_min="0.01", volume_max="1000", volume_step="0.01", tradable=True, market_available=True)
    return dict(account=dict(evidence_id="account", observed_at=TIME, account_key=ACCOUNT.key, currency="USD", mode="DEMO",
                             equity="100000", balance="100000", used_margin="0", positions_at=TIME, orders_at=TIME,
                             complete=True, reconciled=True, cash_flow_evidence_id="verified-no-flow", cash_flow_total="0",
                             day_start=day, week_start=day-timedelta(days=day.weekday()), day_equity="100000",
                             week_equity="100000", high_water_equity="100000", exposures=[]),
                quotes={s: dict(evidence_id="quote-"+s, observed_at=TIME, bid="99.9", ask="100") for s in ("XAUUSDm", "XAGUSDm", "USOILm")},
                instruments={s: dict(metadata, symbol=s) for s in ("XAUUSDm", "XAGUSDm", "USOILm")})


def evaluate(engine, identity, data=None, key="decision-one", current=TIME):
    return engine.evaluate(identity, key, data or inputs(), current=current)


def test_approval_lineage_restart_idempotency(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    result = evaluate(engine, identity)
    assert result["decision"] == "APPROVED", result
    assert Decimal(result["allocation"]["risk"]) <= 250
    assert evaluate(engine, identity) == result
    request = engine.eligible_request(identity, "decision-one", current=TIME)
    reopened = SafetyEngine(Ledger(ledger.path, account=ACCOUNT), engine.config)
    assert reopened.eligible_request(identity, "decision-one", current=TIME) == request
    trace = LifecycleService(ledger).trace("source-one")["lifecycles"][0]
    assert trace["p2_execution_requests"][0]["intent_id"] == identity
    assert not trace["broker_orders"]
    assert trace["p2_reservations"][0]["state"] == "RESERVED"


@pytest.mark.parametrize("field,value", [("equity", "NaN"), ("balance", "Infinity"), ("equity", "0"), ("mode", "LIVE"), ("complete", False), ("reconciled", False), ("account_key", "other")])
def test_invalid_account(tmp_path, field, value):
    ledger, engine = setup(tmp_path)
    data = inputs()
    data["account"][field] = value
    result = evaluate(engine, intent(ledger), data)
    assert result["decision"] == "REJECTED"
    with pytest.raises(ValueError):
        engine.eligible_request(result["intent_id"], "decision-one", current=TIME)


@pytest.mark.parametrize("risk", [.501, 1., 100.])
def test_risk_cap(tmp_path, risk):
    ledger, engine = setup(tmp_path)
    assert evaluate(engine, intent(ledger, risk=risk))["reason"] == "PER_TRADE_RISK"


def test_halt_replay_is_not_eligibility(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    evaluate(engine, identity)
    ledger.halt("operator")
    with pytest.raises(ValueError):
        engine.eligible_request(identity, "decision-one", current=TIME)
    assert evaluate(engine, intent(ledger, "two"), key="decision-two")["reason"] == "HALTED"


@pytest.mark.parametrize("source", ["HISTORICAL_WHATSAPP", "SCREENSHOT"])
def test_historical_firewall(tmp_path, source):
    ledger, engine = setup(tmp_path)
    with pytest.raises(ValueError, match="Historical"):
        intent(ledger, source=source)


@pytest.mark.parametrize("age,field", [(4, "quote"), (6, "account"), (6, "positions"), (6, "orders"), (11, "conversion"), (3601, "metadata")])
def test_stale(tmp_path, age, field):
    ledger, engine = setup(tmp_path)
    data = inputs()
    stamp = TIME-timedelta(seconds=age)
    if field == "quote": data["quotes"]["XAUUSDm"]["observed_at"] = stamp
    elif field in {"conversion", "metadata"}: data["instruments"]["XAUUSDm"]["conversion_at" if field == "conversion" else "observed_at"] = stamp
    else: data["account"][dict(account="observed_at", positions="positions_at", orders="orders_at")[field]] = stamp
    assert evaluate(engine, intent(ledger), data)["reason"] == "STALE_OR_FUTURE_EVIDENCE"


@pytest.mark.parametrize("equity,day,week,high,reason", [(98000,100000,98000,98000,"DAILY_LOSS"), (96000,96000,100000,96000,"WEEKLY_LOSS"), (92000,92000,92000,100000,"MAX_DRAWDOWN_HALT")])
def test_loss_equality(tmp_path, equity, day, week, high, reason):
    ledger, engine = setup(tmp_path)
    data = inputs()
    data["account"].update(equity=str(equity), day_equity=str(day), week_equity=str(week), high_water_equity=str(high))
    assert evaluate(engine, intent(ledger), data)["reason"] == reason
    if reason == "MAX_DRAWDOWN_HALT": assert ledger.status()["halt"]["state"] == "HALTED"


@pytest.mark.parametrize("direction", ["BUY", "SELL"])
def test_no_stacking_or_hedging(tmp_path, direction):
    ledger, engine = setup(tmp_path)
    data = inputs()
    data["account"]["exposures"] = [dict(exposure_id="position", symbol="XAUUSDm", direction=direction, volume="1", stop_loss="90" if direction=="BUY" else "110", kind="POSITION")]
    assert evaluate(engine, intent(ledger), data)["reason"] == "SAME_INSTRUMENT_EXPOSURE"


def test_concurrent_same_instrument(tmp_path):
    ledger, engine = setup(tmp_path)
    identities = [intent(ledger, str(i)) for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda pair: evaluate(engine, pair[1], key="decision-"+str(pair[0])), enumerate(identities)))
    assert sum(r["decision"] == "APPROVED" for r in results) == 1


def test_ttl_and_ambiguous_retention(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    evaluate(engine, identity)
    assert engine.expire(current=TIME+timedelta(seconds=59)) == []
    engine.observe_reservation(identity, state="AMBIGUOUS", filled_volume="0", evidence_id="fixture-ambiguous")
    assert engine.expire(current=TIME+timedelta(days=1)) == []
    other = intent(ledger, "two", symbol="USOILm")
    evaluate(engine, other, key="decision-two")
    assert engine.expire(current=TIME+timedelta(seconds=60)) == [other]


def test_policy_mismatch_invalidates_request(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    evaluate(engine, identity)
    with ledger.transaction() as conn:
        conn.execute("UPDATE p2_policy SET policy_hash='superseded'")
    with pytest.raises(ValueError, match="policy"):
        engine.eligible_request(identity, "decision-one", current=TIME)


@pytest.mark.parametrize("tp,expected", [(116.25,"APPROVED"), (116.24,"MINIMUM_R")])
def test_exact_rr(tmp_path, tp, expected):
    ledger, engine = setup(tmp_path)
    # Entry 100 + .5 allowance; loss 10.5; nearest reward 15.75.
    assert evaluate(engine, intent(ledger, tp=tp))["reason"] == expected


def test_margin_equity_not_lower_balance(tmp_path):
    ledger, engine = setup(tmp_path)
    data = inputs()
    data["account"].update(balance="50000", used_margin="24000")
    assert evaluate(engine, intent(ledger), data)["decision"] == "APPROVED"


@pytest.mark.parametrize("field,value,reason", [("used_margin","25000","MARGIN_LIMIT")])
def test_margin_limit(tmp_path, field, value, reason):
    ledger, engine = setup(tmp_path)
    data = inputs()
    data["account"][field] = value
    assert evaluate(engine, intent(ledger), data)["reason"] == reason


@pytest.mark.parametrize("symbol", ["XAGUSDm", "USOILm"])
def test_all_permitted_instruments(tmp_path, symbol):
    ledger, engine = setup(tmp_path)
    assert evaluate(engine, intent(ledger, symbol=symbol))["decision"] == "APPROVED"


@pytest.mark.parametrize("direction,entry,stop,target", [("BUY",100.,110.,120.), ("SELL",100.,90.,80.), ("HOLD",100.,90.,120.), ("BUY",float('nan'),90.,120.), ("BUY",100.,90.,float('inf'))])
def test_contract_rejects_bad_actions_numbers_geometry(tmp_path, direction, entry, stop, target):
    ledger, engine = setup(tmp_path)
    with pytest.raises(ValueError):
        intent(ledger, direction=direction, entry=entry, sl=stop, tp=target)


def test_sell_and_limit(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger, direction="SELL", sl=110., tp=75.)
    result = evaluate(engine, identity)
    assert result["decision"] == "APPROVED"
    assert Decimal(result["allocation"]["modeled_entry"]) < Decimal('99.9')
    identity = intent(ledger, "limit", symbol="USOILm", entry=100., entry_type="LIMIT")
    assert evaluate(engine, identity, key="limit-decision")["decision"] == "APPROVED"


def test_market_source_entry_only_provenance(tmp_path):
    ledger, engine = setup(tmp_path)
    result = evaluate(engine, intent(ledger, entry=91.))
    assert result["decision"] == "APPROVED"
    assert result["allocation"]["modeled_entry"] == "100.50"


@pytest.mark.parametrize("entry,reason", [(99.,"QUOTE_DEVIATION"), (101.,"CONTRADICTORY_LIMIT")])
def test_limit_rejects(tmp_path, entry, reason):
    ledger, engine = setup(tmp_path)
    assert evaluate(engine, intent(ledger, entry=entry, entry_type="LIMIT"))["reason"] == reason


@pytest.mark.parametrize("change,expected", [("spread","SPREAD_LIMIT"), ("commission","MINIMUM_R"), ("volume","BELOW_MINIMUM_VOLUME"), ("tradable","MARKET_UNAVAILABLE"), ("missing","MISSING_MARKET_EVIDENCE")])
def test_market_metadata_checks(tmp_path, change, expected):
    ledger, engine = setup(tmp_path)
    data = inputs()
    if change == "spread": data["quotes"]["XAUUSDm"]["bid"] = '98'
    elif change == "commission": data["instruments"]["XAUUSDm"]["commission_per_lot"] = '100'
    elif change == "volume": data["instruments"]["XAUUSDm"]["volume_min"] = '999'
    elif change == "tradable": data["instruments"]["XAUUSDm"]["tradable"] = False
    else: del data["quotes"]["XAUUSDm"]
    assert evaluate(engine, intent(ledger), data)["reason"] == expected


def position(symbol, key, volume='1', stop='90'):
    return dict(exposure_id=key, symbol=symbol, direction='BUY', volume=volume, stop_loss=stop, kind='POSITION')


@pytest.mark.parametrize("case,expected", [('count','POSITION_LIMIT'), ('instrument','INSTRUMENT_EXPOSURE'), ('correlation','CORRELATION_LIMIT'), ('notional','INSTRUMENT_EXPOSURE'), ('stop','STOP_RECONCILIATION_AMBIGUITY')])
def test_exposure_limits(tmp_path, case, expected):
    ledger, engine = setup(tmp_path)
    data = inputs()
    if case == 'count': data['account']['exposures'] = [position('USOILm', str(i)) for i in range(3)]
    elif case == 'instrument': data['account']['exposures'] = [position('USOILm','oil', '100')]
    elif case == 'correlation': data['account']['exposures'] = [position('XAGUSDm','silver','60')]
    elif case == 'notional':
        data['account']['exposures'] = [position('USOILm','oil')]
        data['instruments']['USOILm']['notional_per_price_unit_per_lot'] = '2000'
    else: data['account']['exposures'] = [position('USOILm','oil',stop='101')]
    assert evaluate(engine, intent(ledger, risk=.5 if case=='correlation' else None), data)['reason'] == expected


def test_partial_fill_conversion_and_retry(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    result = evaluate(engine, identity)
    volume = Decimal(result['allocation']['volume'])
    half = volume / 2
    args = dict(state='PARTIAL', filled_volume=half, evidence_id='fixture-partial')
    engine.observe_reservation(identity, **args)
    engine.observe_reservation(identity, **args)
    assert engine.expire(current=TIME+timedelta(hours=1)) == []
    data = inputs()
    data['account']['exposures'] = [dict(position('XAUUSDm','filled',str(half)), reservation_intent_id=identity)]
    assert evaluate(engine, intent(ledger, 'oil', symbol='USOILm'), data, key='oil-decision')['decision'] == 'APPROVED'
    with pytest.raises(ValueError, match='Terminal'):
        engine.observe_reservation(identity, state='CONVERTED', filled_volume=half, evidence_id='terminal')
    engine.observe_reservation(identity, state='CONVERTED', filled_volume=half, evidence_id='terminal', terminal=True)


def test_rejected_decision_cannot_bypass_sql(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger, risk=1.)
    evaluate(engine, identity)
    with ledger.transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO p2_execution_requests VALUES('request',?,?,?,?,'ELIGIBLE_NOT_SUBMITTED',?)", (identity,'decision-one',ACCOUNT.key,engine.policy_hash,TIME.isoformat()))


def test_atomic_rollback_on_reservation_failure(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    with ledger.transaction() as conn:
        conn.execute("CREATE TRIGGER fail_reservation BEFORE INSERT ON p2_reservations BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
    with pytest.raises(sqlite3.IntegrityError): evaluate(engine, identity)
    with ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM p2_evaluations').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM risk_decisions').fetchone()[0] == 0


def test_app_integration_stays_halted(tmp_path):
    from fastapi.testclient import TestClient
    from core.rebuild.application import create_app
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    def fresh_inputs(_=None):
        data=inputs()
        stamp=datetime.now(timezone.utc)
        day=stamp.replace(hour=0,minute=0,second=0,microsecond=0)
        data['account'].update(observed_at=stamp,positions_at=stamp,orders_at=stamp,
                               day_start=day,week_start=day-timedelta(days=day.weekday()))
        for q in data['quotes'].values(): q['observed_at']=stamp
        for m in data['instruments'].values(): m.update(observed_at=stamp,conversion_at=stamp)
        return data
    app = create_app(database_path=ledger.path, token='fixture', lifecycle_account=ACCOUNT,
                     safety_configuration=engine.config, safety_input_provider=fresh_inputs)
    with TestClient(app) as client:
        result = client.post('/api/core/lifecycle/intents/'+identity+'/evaluate', headers={'X-Control-Token':'fixture'},
                             json={'safety_decision_id':'app-decision'}).json()
        assert result['record']['reason'] == 'HALTED'
        assert result['execution_enabled'] is False
        app.state.safety.reset_halt(fresh_inputs(),operator_id='fixture-operator',reason='fixture reconciliation')
        active=intent(ledger,'active')
        headers={'X-Control-Token':'fixture'}
        decision=client.post('/api/core/lifecycle/intents/'+active+'/evaluate',headers=headers,
                             json={'safety_decision_id':'active-decision'}).json()
        assert decision['record']['decision']=='APPROVED', decision
        request=client.post('/api/core/lifecycle/requests',headers=headers,
                            json={'execution_request_id':'http-request-0001','intent_id':active,'safety_decision_id':'active-decision'}).json()
        assert request['record']['execution_request_id']=='http-request-0001', request
        assert request['record']['status']=='ELIGIBLE_NOT_SUBMITTED'
        assert request['execution_enabled'] is False


def test_p2_parser_market_absence_and_silver(tmp_path):
    from services.signal_parser import SignalParser
    kwargs = dict(text='XAGUSDm BUY NOW SL 90 TP 130', group_id='operator', sender_id='fixture',
                  message_id='silver', message_timestamp=TIME.timestamp(), received_timestamp=TIME.timestamp())
    parsed = SignalParser().parse(**kwargs, p2=True)
    assert parsed.rejection_reasons == []
    assert parsed.entry_price is None
    assert parsed.parser_version == 'deterministic_v3_p2'
    assert SignalParser().parse(**kwargs).rejection_reasons


def test_margin_race_across_instruments(tmp_path):
    ledger, engine = setup(tmp_path)
    identities = [intent(ledger, str(i), symbol=s) for i,s in enumerate(('XAUUSDm','XAGUSDm','USOILm'))]
    data = inputs()
    data['account']['used_margin'] = '24960'
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda pair: evaluate(engine,pair[1],data,key='decision-'+str(pair[0])),enumerate(identities)))
    assert sum(r['decision']=='APPROVED' for r in results) == 1


def test_expired_approval_revalidation(tmp_path):
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    evaluate(engine,identity)
    later = TIME + timedelta(seconds=60)
    assert engine.expire(current=later) == [identity]
    with pytest.raises(ValueError): engine.eligible_request(identity,'decision-one',current=later)
    data = inputs()
    for key in ('observed_at','positions_at','orders_at'): data['account'][key] = later
    for q in data['quotes'].values(): q['observed_at'] = later
    for m in data['instruments'].values(): m.update(observed_at=later,conversion_at=later)
    assert evaluate(engine,identity,data,key='decision-revalidated',current=later)['decision']=='APPROVED'


def test_persistent_halt_reset_requires_operator_evidence(tmp_path):
    ledger, engine = setup(tmp_path)
    ledger.halt('operator halt')
    with pytest.raises(ValueError): engine.reset_halt(inputs(),operator_id='',reason='reset',current=TIME)
    engine.reset_halt(inputs(),operator_id='fixture-operator',reason='reconciled and reviewed',current=TIME)
    assert ledger.status()['halt']['state']=='ACTIVE'


def test_drawdown_baseline_survives_restart(tmp_path):
    ledger, engine = setup(tmp_path)
    evaluate(engine,intent(ledger))
    reopened = SafetyEngine(Ledger(ledger.path,account=ACCOUNT),engine.config)
    data = inputs()
    data['account'].update(equity='92000',day_equity='100000',week_equity='100000',high_water_equity='92000')
    assert evaluate(reopened,intent(ledger,'oil',symbol='USOILm'),data,key='loss-decision')['reason']=='MAX_DRAWDOWN_HALT'


@pytest.mark.parametrize('after_commit', [False, True])
def test_process_crash_atomicity(tmp_path, after_commit):
    import subprocess
    import sys
    from pathlib import Path
    ledger, engine = setup(tmp_path)
    identity = intent(ledger)
    script = f'''
import os,sys
sys.path.insert(0,{str(Path(__file__).resolve().parents[1])!r})
sys.path.insert(0,{str(Path(__file__).resolve().parent)!r})
from test_p2_safety import ACCOUNT,TIME,inputs
from core.rebuild.ledger import Ledger
from core.rebuild.safety import SafetyEngine
from core.rebuild.safety_contracts import SafetyConfiguration
ledger=Ledger({str(ledger.path)!r},account=ACCOUNT)
engine=SafetyEngine(ledger,SafetyConfiguration(approved_account_key=ACCOUNT.key,authorized_sources={{'operator'}}))
original=ledger.audit
def crash(conn,event,intent,payload):
    if event=='P2_SAFETY_DECISION' and not {after_commit!r}: os._exit(7)
    return original(conn,event,intent,payload)
ledger.audit=crash
engine.evaluate({identity!r},'crash-decision',inputs(),current=TIME)
os._exit(7)
'''
    assert subprocess.run([sys.executable,'-B','-c',script],capture_output=True,timeout=30).returncode==7
    with ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM p2_evaluations').fetchone()[0]==int(after_commit)
        assert conn.execute('SELECT count(*) FROM p2_reservations').fetchone()[0]==int(after_commit)
    assert evaluate(engine,identity,key='crash-decision')['decision']=='APPROVED'


@pytest.mark.parametrize('extra', ['0', '0.0001'])
def test_projected_margin_equality(tmp_path, extra):
    ledger, engine = setup(tmp_path)
    data=inputs()
    data['instruments']['XAUUSDm']['commission_per_lot']='2'
    data['account']['used_margin']=str(Decimal('24960')+Decimal(extra))
    result=evaluate(engine,intent(ledger,risk=.5),data)
    assert result['reason']==('APPROVED' if extra=='0' else 'MARGIN_LIMIT')


@pytest.mark.parametrize('extra', ['0', '0.0001'])
def test_portfolio_risk_equality(tmp_path, extra):
    ledger, engine=setup(tmp_path)
    data=inputs()
    for q in data['quotes'].values(): q.update(bid='100',ask='100')
    data['account']['exposures']=[position('XAUUSDm','gold',str(Decimal('50')+Decimal(extra))),position('XAGUSDm','silver','50')]
    data['instruments']['USOILm']['commission_per_lot']='2'
    result=evaluate(engine,intent(ledger,symbol='USOILm',risk=.5),data)
    assert result['reason']==('APPROVED' if extra=='0' else 'PORTFOLIO_EXPOSURE')


@pytest.mark.parametrize('extra', ['0', '0.0001'])
def test_correlation_equality(tmp_path, extra):
    ledger,engine=setup(tmp_path)
    data=inputs()
    data['quotes']['XAGUSDm'].update(bid='100',ask='100')
    data['account']['exposures']=[position('XAGUSDm','silver',str(Decimal('50')+Decimal(extra)))]
    data['instruments']['XAUUSDm']['commission_per_lot']='2'
    assert evaluate(engine,intent(ledger,risk=.5),data)['reason']==('APPROVED' if extra=='0' else 'CORRELATION_LIMIT')


def test_portfolio_notional_limit(tmp_path):
    ledger,engine=setup(tmp_path)
    data=inputs()
    data['account']['exposures']=[position('XAGUSDm','silver'),position('USOILm','oil')]
    for symbol in ('XAGUSDm','USOILm'): data['instruments'][symbol]['notional_per_price_unit_per_lot']='1490'
    data['instruments']['XAUUSDm']['notional_per_price_unit_per_lot']='2'
    assert evaluate(engine,intent(ledger),data)['reason']=='PORTFOLIO_EXPOSURE'


def test_empty_allowlist_and_unauthorized_source(tmp_path):
    ledger, engine=setup(tmp_path)
    data=inputs()
    identity=intent(ledger,source='NEXUSAI_STRATEGY')
    assert evaluate(engine,identity,data)['reason']=='STRATEGY_NOT_QUALIFIED'
    # Configuration is immutable once installed; another config cannot silently replace it.
    with pytest.raises(ValueError,match='mismatch'):
        SafetyEngine(ledger,SafetyConfiguration(approved_account_key=ACCOUNT.key,authorized_sources=set(),instruments=set()))


def test_versioned_revalidation_and_ambiguous_retention(tmp_path):
    ledger,engine=setup(tmp_path)
    identity=intent(ledger)
    evaluate(engine,identity)
    old_request=engine.eligible_request(identity,'decision-one',current=TIME)
    oil=intent(ledger,'oil',symbol='USOILm')
    evaluate(engine,oil,key='oil-decision')
    engine.observe_reservation(oil,state='AMBIGUOUS',filled_volume='0',evidence_id='uncertain')
    updated=engine.activate_configuration(engine.config,revision='2',operator_id='fixture-operator',reason='reviewed configuration revision')
    with pytest.raises(ValueError): engine.eligible_request(identity,'decision-one',current=TIME)
    result=evaluate(updated,identity,key='new-decision')
    assert result['decision']=='APPROVED'
    assert result['policy_version'] != 'P2-DEMO-1.0/config-1'
    assert updated.eligible_request(identity,'new-decision',current=TIME)['execution_request_id'] != old_request['execution_request_id']
    assert updated.expire(current=TIME+timedelta(hours=1)) == [identity]
    with ledger.connect() as conn:
        assert conn.execute('SELECT state FROM p2_reservations WHERE intent_id=?',(oil,)).fetchone()[0]=='AMBIGUOUS'


def test_timezone_representation_cannot_reset_baseline(tmp_path):
    ledger,engine=setup(tmp_path)
    evaluate(engine,intent(ledger))
    data=inputs()
    offset=timezone(timedelta(hours=5))
    data['account']['day_start']=data['account']['day_start'].astimezone(offset)
    data['account']['week_start']=data['account']['week_start'].astimezone(offset)
    data['account']['day_equity']='50000'
    assert evaluate(engine,intent(ledger,'oil',symbol='USOILm'),data,key='tampered-baseline')['reason']=='CONTRADICTORY_CASH_FLOW_BASELINE'


@pytest.mark.parametrize('kind', ['sources','instruments'])
def test_empty_authorization_denies(tmp_path,kind):
    ledger=Ledger(tmp_path/'deny.sqlite',account=ACCOUNT)
    config=SafetyConfiguration(approved_account_key=ACCOUNT.key,authorized_sources=set() if kind=='sources' else {'operator'},
                               instruments=set() if kind=='instruments' else {'XAUUSDm','XAGUSDm','USOILm'})
    engine=SafetyEngine(ledger,config)
    with ledger.transaction() as conn: conn.execute("UPDATE halt_state SET state='ACTIVE' WHERE singleton=1")
    assert evaluate(engine,intent(ledger))['reason']==('SOURCE_UNAUTHORIZED' if kind=='sources' else 'INSTRUMENT_RESTRICTED')


@pytest.mark.parametrize('days', [1,3])
def test_utc_day_and_monday_rollover(tmp_path,days):
    ledger,engine=setup(tmp_path)
    evaluate(engine,intent(ledger))
    later=TIME+timedelta(days=days)
    engine.expire(current=later)
    data=inputs()
    day=later.replace(hour=0)
    for key in ('observed_at','positions_at','orders_at'): data['account'][key]=later
    data['account'].update(day_start=day,week_start=day-timedelta(days=day.weekday()))
    for q in data['quotes'].values(): q['observed_at']=later
    for m in data['instruments'].values(): m.update(observed_at=later,conversion_at=later)
    assert evaluate(engine,intent(ledger,'new-day'),data,key='rollover-decision',current=later)['decision']=='APPROVED'
    with ledger.connect() as conn:
        row=conn.execute('SELECT * FROM p2_baselines').fetchone()
        assert datetime.fromisoformat(row['day_start'])==day
        assert datetime.fromisoformat(row['week_start'])==day-timedelta(days=day.weekday())


def test_evidenced_cash_flow_adjusts_baselines(tmp_path):
    ledger,engine=setup(tmp_path)
    evaluate(engine,intent(ledger))
    data=inputs()
    data['account'].update(equity='110000',balance='110000',day_equity='110000',week_equity='110000',
                           high_water_equity='110000',cash_flow_total='10000',cash_flow_evidence_id='fixture-deposit')
    assert evaluate(engine,intent(ledger,'oil',symbol='USOILm'),data,key='deposit-decision')['decision']=='APPROVED'
