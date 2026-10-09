import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from core.rebuild.ledger import BrokerDeal, BrokerOrder, BrokerPosition, DemoAccount, Ledger as CoreLedger
from ledger_crash_worker import ACCOUNT as CRASH_ACCOUNT, populate
from test_rebuild_core import ACCOUNT, Ledger, deal, order, request, source


def prepared(tmp_path):
    ledger=Ledger(tmp_path/'core.db')
    signal=source()
    ledger.save_signal(signal)
    intent=ledger.create_intent(request(signal))
    ledger.record_order(order('request-one','o1'))
    return ledger,signal,intent


def position(volume=.01,stamp=1005.,oid='snapshot-1'):
    return BrokerPosition(account_key=ACCOUNT.key,observation_id=oid,broker_position_id='p1',
        originating_client_order_id='request-one',symbol='EURUSD',direction='BUY',open_volume=volume,timestamp=stamp)


def test_account_isolation_and_no_unbound_economic_writes(tmp_path):
    ledger,signal,_=prepared(tmp_path)
    other=ACCOUNT.model_copy(update={'account_id':'other-account'})
    with pytest.raises(ValueError,match='different broker account'):
        CoreLedger(ledger.path,account=other)
    with pytest.raises(ValueError,match='binding required'):
        CoreLedger(ledger.path).create_intent(request(signal))
    for evidence,method in [(order('request-one','o1'),ledger.record_order),(deal('d1','o1','p1'),ledger.record_deal),(position(),ledger.record_position)]:
        with pytest.raises(ValueError,match='different account'):
            method(evidence.model_copy(update={'account_key':other.key}))
    with pytest.raises(ValueError):
        DemoAccount(account_id='live',server='s',currency='USD',mode='LIVE',evidence_source='MT5_DEMO')


def test_receipt_retry_preserves_first_signal_timestamps(tmp_path):
    ledger,signal,_=prepared(tmp_path)
    retry=signal.model_copy(update={'received_timestamp':1010.,'parsed_timestamp':1011.})
    assert ledger.save_signal(retry)==signal.signal_id
    with ledger.connect() as conn:
        stored=json.loads(conn.execute('SELECT payload FROM signals').fetchone()[0])
        assert stored['received_timestamp']==1001.
        assert stored['parsed_timestamp']==1002.


def test_multiple_partial_deals_and_explicit_position_snapshots(tmp_path):
    ledger,_,_=prepared(tmp_path)
    ledger.record_deal(deal('d1','o1','p1',volume=.004))
    ledger.record_deal(deal('d2','o1','p1',volume=.006))
    ledger.record_position(position())
    close_signal=source(source_message_id='close')
    ledger.save_signal(close_signal)
    ledger.create_intent(request(close_signal,'close-client').model_copy(update={'action':'PARTIAL_CLOSE','target_position_id':'p1','volume':.004}))
    ledger.record_order(order('close-client','o2',.004))
    ledger.record_deal(deal('d3','o2','p1','OUT',.004))
    ledger.record_position(position(.006,1006.,'snapshot-2'))
    ledger.record_position(position(.01,1004.,'stale-snapshot'))
    with ledger.connect() as conn:
        assert conn.execute('SELECT open_volume FROM positions').fetchone()[0]==.006
        assert conn.execute('SELECT count(*) FROM trade_outcomes').fetchone()[0]==0
    lines=ledger.deal_lineage()
    assert len(lines)==3
    assert len({r['position_originating_intent'] for r in lines})==1
    assert lines[-1]['intent_id']!=lines[-1]['position_originating_intent']
    assert ledger.record_position(position(.006,1006.,'snapshot-2'))=='DUPLICATE'


def test_close_deal_can_arrive_before_entry_deal_without_symbol_guessing(tmp_path):
    ledger,_,_=prepared(tmp_path)
    ledger.record_position(position())
    closing=source(source_message_id='closing')
    ledger.save_signal(closing)
    ledger.create_intent(request(closing,'close-client').model_copy(update={'action':'CLOSE','target_position_id':'p1'}))
    ledger.record_order(order('close-client','o2'))
    ledger.record_deal(deal('exit','o2','p1','OUT'))
    ledger.record_deal(deal('entry','o1','p1'))
    ledger.record_position(position(0.,1007.,'zero'))
    assert len(ledger.deal_lineage())==2
    with ledger.connect() as conn:
        assert conn.execute('SELECT lifecycle_state FROM positions').fetchone()[0]=='RECOVERY_REQUIRED'
    assert ledger.status()['counts']['trade_outcomes']==0


def test_unknown_target_and_duplicate_position_claims_fail(tmp_path):
    ledger,signal,_=prepared(tmp_path)
    with pytest.raises(ValueError,match='explicitly owned'):
        ledger.create_intent(request(signal,'close-client').model_copy(update={'action':'CLOSE','target_position_id':'unknown'}))
    ledger.record_deal(deal('d1','o1','p1',volume=.005))
    with pytest.raises(ValueError,match='second broker position'):
        ledger.record_deal(deal('d2','o1','p2',volume=.005))
    with pytest.raises(ValueError,match='second broker position'):
        ledger.record_position(position().model_copy(update={'broker_position_id':'p2'}))


def test_quarantine_payload_cannot_change_during_promotion(tmp_path):
    ledger=Ledger(tmp_path/'core.db')
    evidence=deal('d1','o1','p1')
    assert ledger.record_deal(evidence)=='QUARANTINED'
    signal=source(); ledger.save_signal(signal); ledger.create_intent(request(signal))
    ledger.record_order(order('request-one','o1'))
    with pytest.raises(ValueError,match='Quarantined deal conflict'):
        ledger.record_deal(evidence.model_copy(update={'price':101.}))
    assert ledger.replay_quarantine()==['RECORDED']
    assert ledger.replay_quarantine()==[]


def test_order_replay_is_audit_idempotent_and_volume_cannot_expand(tmp_path):
    ledger,_,_=prepared(tmp_path)
    with ledger.connect() as conn:
        before=conn.execute('SELECT count(*) FROM audit_events').fetchone()[0]
    for _ in range(10): ledger.record_order(order('request-one','o1'))
    with ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM audit_events').fetchone()[0]==before
        assert conn.execute('SELECT state FROM order_intents').fetchone()[0]=='FILLED'
    with pytest.raises(ValueError,match='volume differs'):
        ledger.record_order(order('request-one','o1',.02))
    ledger.record_deal(deal('d1','o1','p1'))
    with pytest.raises(ValueError,match='exceed requested'):
        ledger.record_deal(deal('d2','o1','p1',volume=.001))


def test_migration_preserves_version1_payload_and_halt(tmp_path):
    path=tmp_path/'old.db'
    sql=Path(__file__).parents[1]/'core/rebuild/migrations/001_lifecycle.sql'
    signal=source()
    payload=json.dumps(signal.model_dump(mode='json'))
    with sqlite3.connect(path) as conn:
        conn.executescript(sql.read_text())
        conn.execute('INSERT INTO signals VALUES(?,?,?,?,?,?)',(signal.signal_id,signal.source_type,signal.source_id,signal.source_message_id,'testhash',payload))
        conn.execute("UPDATE halt_state SET state='HALTED',reason='preserve me'")
    ledger=CoreLedger(path)
    with ledger.connect() as conn:
        row=conn.execute('SELECT * FROM signals').fetchone()
        assert row['payload']==payload
        assert row['source_timestamp']==1000.
        assert row['parser_version']==signal.parser_version
        assert conn.execute('SELECT count(*) FROM schema_migrations').fetchone()[0]==9
    assert ledger.status()['halt']['reason']=='preserve me'
    CoreLedger(path)
    with ledger.transaction() as conn:
        conn.execute("UPDATE migration_checksums SET sha256='tampered' WHERE version=2")
    with pytest.raises(ValueError,match='checksum mismatch'):
        CoreLedger(path)


@pytest.mark.parametrize('statement', ["UPDATE signals SET payload='{}'", "DELETE FROM signals",
    "UPDATE order_intents SET client_order_id='rewritten'", "DELETE FROM order_intents",
    "UPDATE account_binding SET account_key='changed'", "DELETE FROM account_binding",
    "UPDATE broker_orders SET intent_id='wrong'", "DELETE FROM broker_orders", "DELETE FROM audit_events"])
def test_database_identity_guards(tmp_path,statement):
    ledger,_,_=prepared(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        with ledger.transaction() as conn: conn.execute(statement)


@pytest.mark.parametrize('step',['signal','intent','order','deal','position','transaction'])
def test_actual_process_crash_then_replay(tmp_path,step):
    path=tmp_path/'crash.db'
    worker=Path(__file__).with_name('ledger_crash_worker.py')
    result=subprocess.run([sys.executable,str(worker),str(path),step],capture_output=True,timeout=30)
    assert result.returncode==71,result.stderr.decode()
    ledger=populate(path)
    counts=ledger.status()['counts']
    assert [counts[k] for k in ('signals','order_intents','broker_orders','broker_deals','positions')]==[1]*5
    with ledger.connect() as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('SELECT state FROM order_intents').fetchone()[0]=='FILLED'
    assert ledger.status()['execution_enabled'] is False


def test_competing_processes_keep_one_identity(tmp_path):
    path=tmp_path/'race.db'
    worker=Path(__file__).with_name('ledger_crash_worker.py')
    processes=[subprocess.Popen([sys.executable,str(worker),str(path),'none'],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(4)]
    for process in processes:
        _,err=process.communicate(timeout=40)
        assert process.returncode==0,err.decode()
    ledger=CoreLedger(path,account=CRASH_ACCOUNT)
    assert ledger.status()['counts']['order_intents']==1
    assert len(ledger.deal_lineage())==1


def test_two_same_direction_gold_positions_do_not_collide(tmp_path):
    ledger=Ledger(tmp_path/'same-symbol.db')
    for index in range(2):
        signal=source('GOLD BUY ENTRY 100 SL 90 TP 120',source_message_id=f'message-{index}')
        ledger.save_signal(signal)
        ledger.create_intent(request(signal,f'client-key-{index}'))
        ledger.record_order(order(f'client-key-{index}',f'o{index}'))
        ledger.record_deal(deal(f'd{index}',f'o{index}',f'p{index}'))
    assert len({row['position_originating_intent'] for row in ledger.deal_lineage()})==2


def test_placed_partial_filled_states_survive_reopening(tmp_path):
    path=tmp_path/'states.db'
    ledger=Ledger(path); signal=source(); ledger.save_signal(signal); ledger.create_intent(request(signal))
    for status,volume,stamp in [('PLACED',0.,1003.),('PARTIALLY_FILLED',.005,1004.),('FILLED',.01,1005.)]:
        ledger=Ledger(path)
        ledger.record_order(order('request-one','o1').model_copy(update={'status':status,'filled_volume':volume,'timestamp':stamp}))
        with Ledger(path).connect() as conn:
            assert conn.execute('SELECT state FROM order_intents').fetchone()[0]==status


def test_open_intent_cannot_silently_change_source_levels(tmp_path):
    ledger=Ledger(tmp_path/'levels.db'); signal=source(); ledger.save_signal(signal)
    with pytest.raises(ValueError,match='immutable source signal'):
        ledger.create_intent(request(signal).model_copy(update={'stop_loss':95.}))
