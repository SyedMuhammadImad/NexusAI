"""Native-shaped records from deterministic Python fixtures, not a terminal."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from core.rebuild.broker_observations import ObservationJournal
from core.rebuild.execution import ExecutionEngine
from core.rebuild.mt5_evidence import NativeNormalizer, NativeEvidenceReader, account, stamp, project_native
from core.rebuild.execution_contracts import BrokerSnapshot
from core.rebuild.ledger import DemoAccount
from test_p2_safety import TIME, ACCOUNT, inputs
from test_p3_execution import fixture, reservation

D=Decimal
MSC=int(TIME.timestamp())*1000


class Native:
    ACCOUNT_TRADE_MODE_DEMO=0
    ACCOUNT_TRADE_MODE_REAL=2
    ACCOUNT_TRADE_MODE_CONTEST=1
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=2
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING=0
    ACCOUNT_MARGIN_MODE_EXCHANGE=1
    ORDER_TYPE_BUY=0
    ORDER_TYPE_SELL=1
    ORDER_TYPE_BUY_LIMIT=2
    ORDER_TYPE_SELL_LIMIT=3
    ORDER_STATE_STARTED=0
    ORDER_STATE_PLACED=1
    ORDER_STATE_CANCELED=2
    ORDER_STATE_PARTIAL=3
    ORDER_STATE_FILLED=4
    ORDER_STATE_REJECTED=5
    ORDER_STATE_EXPIRED=6
    ORDER_STATE_REQUEST_ADD=7
    ORDER_STATE_REQUEST_MODIFY=8
    ORDER_STATE_REQUEST_CANCEL=9
    ORDER_REASON_SL=4
    ORDER_REASON_TP=5
    DEAL_TYPE_BUY=0
    DEAL_TYPE_SELL=1
    DEAL_TYPE_BALANCE=2
    DEAL_TYPE_CREDIT=3
    DEAL_TYPE_CHARGE=4
    DEAL_TYPE_CORRECTION=5
    DEAL_TYPE_BUY_CANCELED=13
    DEAL_TYPE_SELL_CANCELED=14
    DEAL_ENTRY_IN=0
    DEAL_ENTRY_OUT=1
    DEAL_ENTRY_INOUT=2
    DEAL_ENTRY_OUT_BY=3
    POSITION_TYPE_BUY=0
    POSITION_TYPE_SELL=1
    SYMBOL_TRADE_MODE_FULL=4
    SYMBOL_CALC_MODE_FOREX=0

    def __init__(self):
        self.a=dict(login=123,server='fixture-server',currency='USD',trade_mode=0,margin_mode=2,
                    trade_allowed=True,trade_expert=True,equity=100000,balance=100000,margin=0)
        self.t=dict(connected=True,trade_allowed=True,tradeapi_disabled=False)
        self.os=[]; self.ds=[]; self.ps=[]; self.pending=[]
    def account_info(self): return SimpleNamespace(**self.a)
    def terminal_info(self): return SimpleNamespace(**self.t)
    def history_orders_get(self,*args): return self.os
    def history_deals_get(self,*args): return self.ds
    def orders_get(self): return self.pending
    def positions_get(self): return self.ps
    def symbol_info(self,symbol): return SimpleNamespace(**symbol_record(symbol))
    def symbol_info_tick(self,symbol): return SimpleNamespace(time_msc=MSC,bid=99.99,ask=100)


def binding():
    return DemoAccount(account_id='123',server='fixture-server',currency='USD',evidence_source='MT5_DEMO')


def symbol_record(symbol='XAUUSDm'):
    return dict(name=symbol,trade_mode=4,trade_calc_mode=0,trade_tick_size=.01,trade_tick_value_profit=.01,
        trade_tick_value_loss=.01,trade_contract_size=1,volume_min=.01,volume_max=1000,volume_step=.01,
        currency_profit='USD',currency_margin='USD',point=.01,digits=2,trade_stops_level=0,filling_mode=1,trade_exemode=2)


def order_record(**kw):
    return dict(dict(ticket=11,time_setup_msc=MSC-1000,time_done_msc=MSC,type=0,state=4,magic=7,
        position_id=31,reason=3,volume_initial=1.,volume_current=0.,price_open=100.,sl=90.,tp=130.,symbol='XAUUSDm',comment='nx3-fixture'),**kw)


def deal_record(**kw):
    return dict(dict(ticket=21,order=11,time_msc=MSC,type=0,entry=0,position_id=31,volume=1.,price=100.,
        profit=0.,commission=0.,swap=0.,fee=0.,symbol='XAUUSDm',magic=7,reason=3),**kw)


def position_record(**kw):
    return dict(dict(ticket=99,identifier=31,time_msc=MSC-1000,time_update_msc=MSC,type=0,magic=7,
        volume=1.,price_open=100.,price_current=100.,sl=90.,tp=130.,symbol='XAUUSDm'),**kw)


def normalizer(): return NativeNormalizer(Native(),ACCOUNT.key,TIME)


@pytest.mark.parametrize('kind,make',[('order',order_record),('deal',deal_record),('position',position_record),('symbol',symbol_record)])
def test_native_normalizes_dict_and_named_fields(kind,make):
    n=normalizer()
    a=getattr(n,kind)(make())
    b=getattr(n,kind)(SimpleNamespace(**make()))
    assert a==b
    assert a.raw_reference and a.normalizer_version=='mt5-native-v1'


@pytest.mark.parametrize('kind,make,field,value',[
    ('order',order_record,'ticket',11.0),('order',order_record,'ticket',True),
    ('order',order_record,'type',999),('order',order_record,'state',999),
    ('order',order_record,'volume_current',2),('order',order_record,'time_done_msc',-1),
    ('deal',deal_record,'volume',float('nan')),('deal',deal_record,'price',float('inf')),
    ('deal',deal_record,'entry',999),('deal',deal_record,'position_id',0),
    ('position',position_record,'identifier',0),('position',position_record,'sl',0),
    ('position',position_record,'time_update_msc',MSC-2000),('symbol',symbol_record,'volume_step',0)])
def test_malformed_native_fields_fail_closed(kind,make,field,value):
    r=make(); r[field]=value
    with pytest.raises((ValueError,TypeError,OverflowError)):
        getattr(normalizer(),kind)(r)


@pytest.mark.parametrize('kind,make,field',[('order',order_record,'magic'),('deal',deal_record,'fee'),
    ('position',position_record,'identifier'),('symbol',symbol_record,'trade_calc_mode')])
def test_missing_native_fields_no_default(kind,make,field):
    r=make(); del r[field]
    with pytest.raises(KeyError): getattr(normalizer(),kind)(r)


def test_ids_and_timestamps_preserve_integer_precision():
    o=normalizer().deal(deal_record(ticket=2**60+1,time_msc=MSC+123))
    assert o.broker_entity_id==str(2**60+1)
    assert o.broker_reported_at.microsecond==123000
    assert o.ordering=='UNORDERED'


@pytest.mark.parametrize('type_', [2,5,13,14])
def test_balance_and_cancel_are_not_fake_fills(type_):
    o=normalizer().deal(deal_record(type=type_,volume=0,price=0,profit=-12))
    assert o.normalized_payload['direction'] is None
    assert o.normalized_payload['native_type'] not in {'DEAL_TYPE_BUY','DEAL_TYPE_SELL'}


@pytest.mark.parametrize('field,value',[('login',999),('trade_mode',2),('margin_mode',0),('trade_allowed',1),
    ('trade_expert',False),('equity',0),('balance',float('nan')),('margin',-1)])
def test_account_fail_closed(field,value):
    c=Native(); c.a[field]=value
    with pytest.raises(ValueError): account(c,c.account_info(),c.terminal_info(),binding(),'session',TIME)


def test_reader_collects_attested_records_without_send(tmp_path):
    ledger,*_=fixture(tmp_path)
    c=Native()
    b=binding()
    a,_=account(c,c.account_info(),c.terminal_info(),b,'session',TIME)
    def context(batch,orders,deals,positions):
        data=inputs()
        data['account']['account_key']=b.key
        data['account']['equity']=data['account']['balance']='100000'
        data['account']['used_margin']='0'
        data['quotes']['XAUUSDm']['bid']='99.99'
        data['quotes']['XAUUSDm']['ask']='100'
        return data
    reader=NativeEvidenceReader(b,symbols=['XAUUSDm'],context_provider=context,clock=lambda:TIME)
    from core.rebuild.mt5_demo import MT5DemoAdapter
    adapter=MT5DemoAdapter(c,b,session_id='session',snapshot_reader=reader,clock=lambda:TIME)
    batch=adapter.snapshot(TIME)
    assert adapter.observations==batch['native_observations']
    j=ObservationJournal(b.key)
    with ledger.transaction() as conn:
        j.append(conn,batch['native_observations'])
        snapshot=BrokerSnapshot.model_validate(project_native(conn,j,batch))
        assert snapshot.attestation.account_key==b.key
        assert snapshot.orders==snapshot.deals==snapshot.positions==()
    assert not hasattr(c,'order_send')


def test_reader_retains_malformed_deal(tmp_path):
    c=Native(); c.ds=[deal_record(price=float('nan'))]
    b=binding(); a,_=account(c,c.account_info(),c.terminal_info(),b,'session',TIME)
    reader=NativeEvidenceReader(b,symbols=[],context_provider=lambda *args:None,clock=lambda:TIME)
    batch=reader(c,TIME,a)
    bad=next(o for o in batch['native_observations'] if o.broker_entity_type=='DEAL')
    assert bad.error=='INVALID_NATIVE_RECORD'
    assert bad.raw_native['price']=='nan'


def install_native_batch(broker):
    original=broker.snapshot
    def snapshot(since):
        s=original(since)
        n=normalizer()
        observations=[]
        for o in s.orders:
            observations.append(n.order(order_record(ticket=int(o.broker_order_id),magic=o.magic,comment=o.correlation,
                type=0 if o.direction=='BUY' else 1,state={'FILLED':4,'PARTIALLY_FILLED':3,'PLACED':1}[o.status],
                volume_initial=float(o.requested_volume),volume_current=float(o.requested_volume-o.filled_volume))))
        for d in s.deals:
            observations.append(n.deal(deal_record(ticket=int(d.broker_deal_id),order=int(d.broker_order_id),position_id=int(d.broker_position_id),
                volume=float(d.volume),price=float(d.price),profit=float(d.profit),type=0 if d.direction=='BUY' else 1)))
        for p in s.positions:
            observations.append(n.position(position_record(identifier=int(p.broker_position_id),volume=float(p.open_volume))))
        a=dict(equity=str(s.safety.account.equity),balance=str(s.safety.account.balance),margin=str(s.safety.account.used_margin),currency='USD')
        observations.append(n.emit('ACCOUNT',ACCOUNT.key,a,a))
        meta=s.safety.instruments['XAUUSDm']
        r=symbol_record(); r.update(trade_tick_size=float(meta.tick_size),volume_min=float(meta.volume_min),volume_max=float(meta.volume_max),volume_step=float(meta.volume_step))
        observations.append(n.symbol(r))
        q=s.safety.quotes['XAUUSDm']
        observations.append(n.quote('XAUUSDm',dict(time_msc=MSC,bid=float(q.bid),ask=float(q.ask))))
        inv=dict(positions=[p.broker_position_id for p in s.positions],orders=[],complete=True,history_since=since.isoformat())
        observations.append(n.emit('INVENTORY','current',inv,inv,TIME,'BROKER_UPDATE'))
        broker.observations=observations
        return dict(native_observations=observations,attestation=s.attestation,history_since=since,observed_at=TIME,
                    safety_provider=lambda *args:s.safety,exit_reasons={4:'SL',5:'TP'},full_trade_mode=4)
    broker.snapshot=snapshot
    fill=broker.fill
    def numeric_fill(command,*args,**kw):
        result=fill(command,*args,**kw)
        for o in broker.orders: o['broker_order_id']='11'
        for index,d in enumerate(broker.deals): d.update(broker_deal_id=str(21+index),broker_order_id='11',broker_position_id='31')
        for p in broker.positions: p.update(broker_position_id='31',opening_order_id='11')
        # FakeBroker context lookup expects its own correlation-based opening ID;
        # build exact exposures here instead of weakening production attribution.
        broker.native_command=command
        return '11'
    broker.fill=numeric_fill
    # Replace FakeBroker's synthetic exposure lookup while retaining its snapshot shape.
    def canonical_snapshot(since):
        data=deepcopy(broker.data)
        for p in broker.positions:
            data['account']['exposures'].append(dict(exposure_id=p['broker_position_id'],symbol=p['symbol'],direction=p['direction'],
                volume=p['open_volume'],stop_loss=p['stop_loss'],kind='POSITION',reservation_intent_id=broker.native_command['intent_id']))
        return BrokerSnapshot(evidence_id='fixture-native',observed_at=TIME,attestation=broker.attest(),history_since=since,
            complete=True,orders=broker.orders,deals=broker.deals,positions=broker.positions,safety=data)
    original=canonical_snapshot


@pytest.mark.parametrize('count',[1,2])
def test_native_batch_execution_lineage_and_replay(tmp_path,count):
    ledger,_,engine,broker,request=fixture(tmp_path)
    broker.deal_count=count
    install_native_batch(broker)
    assert engine.submit(request)['state']=='FILLED'
    assert engine.submit(request)['state']=='FILLED'
    assert len(broker.calls)==1
    assert reservation(ledger)['state']=='CONVERTED'
    with ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM p3_deals').fetchone()[0]==count
        assert c.execute("SELECT count(*) FROM p3_observations WHERE broker_entity_type='DEAL'").fetchone()[0]==count


def test_unordered_native_deal_correction_halts_without_resubmit(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    install_native_batch(broker)
    assert engine.submit(request)['state']=='FILLED'
    broker.deals[0]['profit']='10'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert reservation(ledger)['state']=='AMBIGUOUS'
    engine.submit(request)
    assert len(broker.calls)==1
    with ledger.connect() as c:
        assert c.execute("SELECT count(*) FROM p3_observations WHERE broker_entity_type='DEAL'").fetchone()[0]==2


def native_batch(orders, deals, positions, *, time=TIME, provider_change=None):
    n=NativeNormalizer(Native(),ACCOUNT.key,time)
    observations=[n.order(o) for o in orders]+[n.deal(d) for d in deals]+[n.position(p) for p in positions]
    data=inputs()
    a=dict(equity=data['account']['equity'],balance=data['account']['balance'],margin=data['account']['used_margin'],currency='USD')
    observations.append(n.emit('ACCOUNT',ACCOUNT.key,a,a))
    observations.append(n.symbol(symbol_record()))
    q=data['quotes']['XAUUSDm']
    observations.append(n.quote('XAUUSDm',dict(time_msc=MSC,bid=float(q['bid']),ask=float(q['ask']))))
    inv=dict(positions=[str(p['identifier']) for p in positions],orders=[],complete=True,history_since=TIME.isoformat())
    observations.append(n.emit('INVENTORY','current',inv,inv,time,'BROKER_UPDATE'))
    def context(batch,os,ds,ps):
        result=deepcopy(data)
        for p in ps:
            if D(p['open_volume']):
                result['account']['exposures'].append(dict(exposure_id=p['broker_position_id'],symbol=p['symbol'],direction=p['direction'],
                    volume=p['open_volume'],stop_loss=p['stop_loss'],kind='POSITION',reservation_intent_id='intent-one'))
        if provider_change: provider_change(result)
        return result
    from test_p3_execution import FakeBroker
    return dict(native_observations=observations,attestation=FakeBroker().attest(),history_since=TIME,observed_at=time,
                safety_provider=context,exit_reasons={4:'SL',5:'TP'},full_trade_mode=4)


def test_native_same_symbol_independent_positions(tmp_path):
    ledger,*_=fixture(tmp_path)
    j=ObservationJournal(ACCOUNT.key)
    batch=native_batch([order_record(),order_record(ticket=12,position_id=32)],
        [deal_record(),deal_record(ticket=22,order=12,position_id=32)],
        [position_record(),position_record(identifier=32,ticket=100)])
    with ledger.transaction() as c:
        j.append(c,batch['native_observations'])
        snap=BrokerSnapshot.model_validate(project_native(c,j,batch))
        assert {(p.broker_position_id,p.opening_order_id) for p in snap.positions}=={('31','11'),('32','12')}


def test_native_protective_close_requires_exact_deals_and_absence(tmp_path):
    ledger,_,engine,broker,request=fixture(tmp_path)
    install_native_batch(broker)
    assert engine.submit(request)['state']=='FILLED'
    command=broker.calls[0]; v=float(command['volume'])
    orders=[order_record(magic=command['magic'],comment=command['correlation'],volume_initial=v),
        order_record(ticket=12,type=1,reason=5,volume_initial=v,sl=0,tp=0,time_done_msc=MSC+1000)]
    deals=[deal_record(volume=v),deal_record(ticket=22,order=12,type=1,entry=1,volume=v,price=130,time_msc=MSC+1000)]
    batch=native_batch(orders,deals,[],time=TIME+timedelta(seconds=1))
    broker.time=TIME+timedelta(seconds=1)
    broker.observations=batch['native_observations']
    broker.snapshot=lambda since:batch
    assert engine.reconcile()['status']=='RECONCILED'
    assert reservation(ledger)['state']=='RELEASED'
    with ledger.connect() as c:
        assert c.execute('SELECT lifecycle_state FROM p3_positions').fetchone()[0]=='CLOSED'
    assert engine.reconcile()['status']=='RECONCILED'
    assert len(broker.calls)==1


@pytest.mark.parametrize('case',['no_close','external_position','bad_quantity','unsupported_correction'])
def test_native_impossible_or_external_evidence_is_retained(tmp_path,case):
    ledger,*_=fixture(tmp_path)
    os=[order_record()]; ds=[deal_record()]; ps=[]
    if case=='external_position': ps=[position_record(identifier=99)]
    if case=='bad_quantity': ds=[deal_record(volume=.5)]; ps=[position_record()]
    if case=='unsupported_correction': ds=[deal_record(type=13,profit=0)]
    batch=native_batch(os,ds,ps)
    j=ObservationJournal(ACCOUNT.key)
    with ledger.transaction() as c:
        j.append(c,batch['native_observations'])
        with pytest.raises((ValueError,KeyError)): project_native(c,j,batch)
        assert c.execute('SELECT count(*) FROM p3_observations').fetchone()[0]>=3


@pytest.mark.parametrize('case',['balance','margin','quote','lot','understated_value','notional','inventory'])
def test_context_cannot_override_native_facts(tmp_path,case):
    def change(data):
        if case in {'balance','margin'}: data['account']['balance' if case=='balance' else 'used_margin']='1'
        elif case=='quote': data['quotes']['XAUUSDm']['bid']='98'
        elif case=='lot': data['instruments']['XAUUSDm']['volume_step']='0.1'
        elif case=='understated_value': data['instruments']['XAUUSDm']['value_per_price_unit_per_lot']='0.1'
        elif case=='notional': data['instruments']['XAUUSDm']['notional_per_price_unit_per_lot']='0.1'
        else: data['account']['exposures']=[]
    ledger,*_=fixture(tmp_path)
    batch=native_batch([order_record()],[deal_record()],[position_record()],provider_change=change)
    with ledger.transaction() as c:
        j=ObservationJournal(ACCOUNT.key); j.append(c,batch['native_observations'])
        with pytest.raises(ValueError): project_native(c,j,batch)


def test_broker_update_out_of_order_projection(tmp_path):
    ledger,*_=fixture(tmp_path)
    n=normalizer(); j=ObservationJournal(ACCOUNT.key)
    old=n.order(order_record(state=3,volume_current=.5,time_done_msc=0))
    new=n.order(order_record())
    with ledger.transaction() as c:
        j.append(c,[new])
        j.append(c,[old])
        assert j.current(c,'ORDER','11').normalized_payload['native_status']=='ORDER_STATE_FILLED'
        assert c.execute('SELECT count(*) FROM p3_observations').fetchone()[0]==2


@pytest.mark.parametrize('method',['os','ds','ps','pending'])
def test_none_native_inventory_is_not_empty(method):
    c=Native(); setattr(c,method,None)
    b=binding(); a,_=account(c,c.account_info(),c.terminal_info(),b,'session',TIME)
    reader=NativeEvidenceReader(b,symbols=[],context_provider=lambda *args:None,clock=lambda:TIME)
    with pytest.raises(ValueError): reader(c,TIME,a)
