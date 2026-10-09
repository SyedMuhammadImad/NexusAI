"""ADR-011 journal/projection fixtures; no credentials or native runtime."""
from copy import deepcopy
from datetime import timedelta
import json
import sqlite3

import pytest

from core.rebuild.broker_observations import ObservationJournal, observation
from core.rebuild.execution import ExecutionEngine
from core.rebuild.ledger import Ledger
from core.rebuild.lifecycle_service import LifecycleService
from test_p3_execution import fixture, reservation
from test_p2_safety import TIME, ACCOUNT


def obs(kind='DEAL', identity='1', version=1, payload=None, **kw):
    p = payload or {'volume':'1'}
    return observation(ACCOUNT.key,kind,identity,p,p,TIME,version=version,
                       ordering='SEQUENCE' if version is not None else 'UNORDERED',**kw)


@pytest.mark.parametrize('kind',['DEAL','ORDER','POSITION'])
@pytest.mark.parametrize('reverse',[False,True])
def test_versions_duplicates_out_of_order_restart(tmp_path,kind,reverse):
    ledger,*_=fixture(tmp_path)
    journal=ObservationJournal(ACCOUNT.key)
    first=obs(kind,version=1)
    second=obs(kind,version=2,payload={'volume':'2'},supersedes=first.observation_id)
    sequence=[second,first] if reverse else [first,second]
    for o in sequence:
        with ledger.transaction() as conn:
            journal.append(conn,[o,o])
    reopened=Ledger(ledger.path,account=ACCOUNT)
    with reopened.transaction() as conn:
        journal.append(conn,[first])
        assert journal.current(conn,kind,'1').observation_id==second.observation_id
        assert conn.execute('SELECT count(*) FROM p3_observations').fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM p3_native_evidence').fetchone()[0]==2
    for sql in ('UPDATE p3_observations SET normalizer_version="bad"','DELETE FROM p3_observations',
                'UPDATE p3_native_evidence SET payload="{}"','DELETE FROM p3_native_evidence'):
        with pytest.raises(sqlite3.IntegrityError),ledger.transaction() as conn:
            conn.execute(sql)


@pytest.mark.parametrize('mode',['equal_version','no_version','missing_parent','wrong_entity_parent','backwards_parent'])
def test_conflicting_revisions_preserved(tmp_path,mode):
    ledger,*_=fixture(tmp_path)
    journal=ObservationJournal(ACCOUNT.key)
    first=obs(version=None if mode=='no_version' else 2)
    kwargs={}
    version=None if mode=='no_version' else 2
    if mode=='missing_parent': kwargs['supersedes']='missing'
    if mode=='wrong_entity_parent':
        first=obs(identity='other')
        kwargs['supersedes']=first.observation_id
    if mode=='backwards_parent':
        version=1
        kwargs['supersedes']=first.observation_id
    second=obs(version=version,payload={'volume':'2'},**kwargs)
    with ledger.transaction() as conn:
        journal.append(conn,[first,second])
        with pytest.raises(ValueError): journal.current(conn,'DEAL','1')
        assert conn.execute('SELECT count(*) FROM p3_observations').fetchone()[0]==2


def test_explicit_supersession_without_sequence(tmp_path):
    ledger,*_=fixture(tmp_path)
    j=ObservationJournal(ACCOUNT.key)
    a=obs(version=None)
    b=obs(version=None,payload={'volume':'2'},supersedes=a.observation_id)
    with ledger.transaction() as c:
        j.append(c,[b,a])
        assert j.current(c,'DEAL','1').observation_id==b.observation_id


def test_different_receipt_time_is_not_new_fill(tmp_path):
    ledger,*_=fixture(tmp_path)
    first=obs()
    duplicate=first.model_copy(update={'observed_at':TIME+timedelta(seconds=1)})
    with ledger.transaction() as c:
        ObservationJournal(ACCOUNT.key).append(c,[first,duplicate])
        assert c.execute('SELECT count(*) FROM p3_observations').fetchone()[0]==1


def test_account_or_content_tamper_rejected(tmp_path):
    ledger,*_=fixture(tmp_path)
    for changes in ({'account_key':'other'},{'raw_reference':'bad'},{'normalized_payload':{'volume':'9'}}):
        with pytest.raises(ValueError),ledger.transaction() as c:
            ObservationJournal(ACCOUNT.key).append(c,[obs().model_copy(update=changes)])


def install_journal_broker(broker):
    """Explicit sequenced fixture feed, distinct from unsequenced MT5 deal history."""
    original=broker.snapshot
    broker.version=1
    def snapshot(since):
        s=original(since)
        groups={}
        broker.observations=[]
        for kind,field,key in (('ORDER','orders','broker_order_id'),('DEAL','deals','broker_deal_id'),('POSITION','positions','broker_position_id')):
            items=[]
            for item in getattr(s,field):
                payload=item.model_dump(mode='json',exclude={'evidence_id','observed_at'})
                o=observation(ACCOUNT.key,kind,getattr(item,key),payload,payload,TIME,
                    version=broker.version,ordering='SEQUENCE',normalizer='fixture-sequenced-v1')
                broker.observations.append(o)
                items.append(item.model_copy(update={'evidence_id':o.observation_id}))
            groups[field]=tuple(items)
        return s.model_copy(update=groups)
    broker.snapshot=snapshot


def test_revised_deal_preserves_one_economic_entity_and_trace(tmp_path):
    ledger,safety,engine,broker,request=fixture(tmp_path)
    install_journal_broker(broker)
    assert engine.submit(request)['state']=='FILLED'
    with ledger.connect() as c:
        original=c.execute('SELECT payload FROM p3_deals').fetchone()[0]
    broker.version=2
    broker.deals[0]['profit']='2'
    assert engine.reconcile()['status']=='RECONCILED'
    assert ExecutionEngine(safety,broker,clock=lambda:TIME).submit(request)['state']=='FILLED'
    with ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM p3_deals').fetchone()[0]==1
        assert c.execute('SELECT payload FROM p3_deals').fetchone()[0]==original
        head=engine.journal.current(c,'DEAL',broker.deals[0]['broker_deal_id'])
        assert head.normalized_payload['profit']=='2'
    trace=LifecycleService(ledger).trace('source-one')['lifecycles'][0]
    assert len(trace['p3_observations'])==6
    assert all(o['attempt_id']==engine.get(request)['attempt_id'] for o in trace['p3_observations'])
    assert len(broker.calls)==1


def test_conflicting_deal_keeps_history_capacity_halt_no_resend(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    install_journal_broker(broker)
    engine.submit(request)
    broker.deals[0]['profit']='99'  # Same authoritative sequence, contradictory payload.
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'
    assert ledger.status()['halt']['state']=='HALTED'
    engine.submit(request)
    assert len(broker.calls)==1
    with ledger.connect() as c:
        assert c.execute("SELECT count(*) FROM p3_observations WHERE broker_entity_type='DEAL'").fetchone()[0]==2


def test_revision_cannot_change_economic_identity(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    install_journal_broker(broker)
    engine.submit(request)
    broker.version=2
    broker.deals[0]['broker_position_id']='external'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'


def test_partial_fill_correction_must_agree_with_position_and_order(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    from decimal import Decimal
    broker.fraction=Decimal('0.5')
    install_journal_broker(broker)
    assert engine.submit(request)['state']=='PARTIALLY_FILLED'
    broker.version=2
    broker.deals[0]['volume']=str(Decimal(broker.deals[0]['volume'])/2)
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'


def test_unknown_order_evidence_survives_projection_rollback(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    install_journal_broker(broker)
    engine.submit(request)
    broker.version=2
    external=deepcopy(broker.orders[0]); external.update(broker_order_id='external',correlation='not-ours')
    broker.orders.append(external)
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    with ledger.connect() as c:
        assert c.execute("SELECT count(*) FROM p3_observations WHERE broker_entity_id='external'").fetchone()[0]==1
        assert c.execute("SELECT count(*) FROM p3_orders WHERE broker_order_id='external'").fetchone()[0]==0


def test_consistent_partial_correction_preserves_history(tmp_path):
    from decimal import Decimal
    ledger,_,engine,broker,request=fixture(tmp_path)
    broker.fraction=Decimal('0.5')
    install_journal_broker(broker)
    assert engine.submit(request)['state']=='PARTIALLY_FILLED'
    prior=broker.deals[0]['volume']
    corrected=str(Decimal(prior)/2)
    broker.version=2
    broker.deals[0]['volume']=corrected
    broker.orders[0]['filled_volume']=corrected
    broker.positions[0]['open_volume']=corrected
    assert engine.reconcile()['status']=='RECONCILED'
    assert reservation(ledger)['state']=='PARTIAL'
    assert Decimal(reservation(ledger)['filled_volume'])==Decimal(corrected)
    with ledger.connect() as c:
        assert json.loads(c.execute('SELECT payload FROM p3_deals').fetchone()[0])['volume']==prior
        assert engine.journal.current(c,'DEAL',broker.deals[0]['broker_deal_id']).normalized_payload['volume']==corrected
    assert len(broker.calls)==1


def test_equal_content_uses_numeric_version_order(tmp_path):
    ledger,*_=fixture(tmp_path)
    j=ObservationJournal(ACCOUNT.key)
    with ledger.transaction() as c:
        j.append(c,[obs(version=9),obs(version=10)])
        assert j.current(c,'DEAL','1').observed_version==10


def test_transaction_crash_rolls_back_whole_evidence_batch(tmp_path):
    ledger,*_=fixture(tmp_path)
    with pytest.raises(RuntimeError),ledger.transaction() as c:
        ObservationJournal(ACCOUNT.key).append(c,[obs()])
        raise RuntimeError('fixture crash')
    with ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM p3_observations').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM p3_observation_heads').fetchone()[0]==0


def test_concurrent_duplicate_read_is_one_observation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    ledger,*_=fixture(tmp_path)
    j=ObservationJournal(ACCOUNT.key)
    def append(_):
        with ledger.transaction() as c: j.append(c,[obs()])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(append,range(8)))
    with ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM p3_observations').fetchone()[0]==1


def test_conflict_lineage_remains_visible_after_halt(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    install_journal_broker(broker)
    engine.submit(request)
    broker.deals[0]['profit']='2'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    trace=LifecycleService(ledger).trace('source-one')['lifecycles'][0]
    deals=[o for o in trace['p3_observations'] if o['broker_entity_type']=='DEAL']
    assert len(deals)==2
    assert all(o['attempt_id']==engine.get(request)['attempt_id'] for o in deals)


def test_identical_content_does_not_excuse_backward_lineage(tmp_path):
    ledger,*_=fixture(tmp_path)
    j=ObservationJournal(ACCOUNT.key)
    parent=obs(version=2)
    child=obs(version=1,supersedes=parent.observation_id)
    with ledger.transaction() as c:
        j.append(c,[parent,child])
        with pytest.raises(ValueError): j.current(c,'DEAL','1')


def test_replayed_original_payload_cannot_clear_unresolved_conflict(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    install_journal_broker(broker)
    engine.submit(request)
    broker.deals[0]['profit']='9'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    broker.deals[0]['profit']='0'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'
    engine.submit(request)
    assert len(broker.calls)==1
