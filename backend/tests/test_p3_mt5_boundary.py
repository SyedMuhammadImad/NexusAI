"""MT5 method shapes implemented by a fake Python object; no native import."""
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest

from core.rebuild.ledger import DemoAccount
from core.rebuild.mt5_demo import MT5DemoAdapter
from test_p3_execution import fixture, TIME


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO=0
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=2
    SYMBOL_TRADE_MODE_FULL=4
    SYMBOL_TRADE_EXECUTION_MARKET=2
    ORDER_FILLING_FOK=0
    ORDER_FILLING_IOC=1
    ORDER_FILLING_RETURN=2
    TRADE_ACTION_DEAL=1
    TRADE_ACTION_PENDING=5
    ORDER_TYPE_BUY=0
    ORDER_TYPE_SELL=1
    ORDER_TYPE_BUY_LIMIT=2
    ORDER_TYPE_SELL_LIMIT=3
    ORDER_TIME_GTC=0
    TRADE_RETCODE_DONE=10009
    TRADE_RETCODE_DONE_PARTIAL=10010
    TRADE_RETCODE_PLACED=10008
    TRADE_RETCODE_REJECT=10006

    def __init__(self):
        self.account=NS(login=123,server='fixture-demo',currency='USD',trade_mode=0,margin_mode=2,trade_allowed=True,trade_expert=True,
                        equity=100000,balance=100000,margin=0)
        self.terminal=NS(connected=True,trade_allowed=True,tradeapi_disabled=False)
        self.info=NS(point=.01,volume_min=.01,volume_max=1000,volume_step=.01,trade_tick_size=.01,
                     trade_mode=4,trade_stops_level=0,filling_mode=3,trade_exemode=2)
        self.tick=NS(time_msc=int(TIME.timestamp()*1000),bid=99.9,ask=100.)
        self.result=NS(retcode=10009,order=321,deal=654)
        self.sent=[]
        self.on_account=None
        self.account_calls=0

    def account_info(self):
        self.account_calls+=1
        if self.on_account:self.on_account(self)
        return self.account
    def terminal_info(self):return self.terminal
    def symbol_info(self,symbol):return self.info
    def symbol_info_tick(self,symbol):return self.tick
    def order_send(self,request):
        self.sent.append(request)
        return self.result


def adapter_fixture(tmp_path,**kwargs):
    _,_,engine,broker,request=fixture(tmp_path,**kwargs)
    engine.submit(request)
    command=dict(broker.calls[0])
    account=DemoAccount(account_id='123',server='fixture-demo',currency='USD',evidence_source='MT5_DEMO')
    native=FakeMT5()
    adapter=MT5DemoAdapter(native,account,session_id='fixture-only',snapshot_reader=lambda *_:None,clock=lambda:TIME)
    command.update(account_key=account.key,session_id='fixture-only')
    return native,adapter,command


@pytest.mark.parametrize('direction,sl,tp', [('BUY',90.,130.),('SELL',110.,70.)])
def test_market_mapping(tmp_path,direction,sl,tp):
    native,adapter,command=adapter_fixture(tmp_path,direction=direction,sl=sl,tp=tp)
    assert adapter.submit(command).outcome=='ACKNOWLEDGED'
    sent=native.sent[0]
    assert sent['volume']==float(command['volume'])
    assert sent['sl']==float(command['stop']) and sent['tp']==float(command['nearest_tp'])
    assert sent['magic']==command['magic'] and sent['comment']==command['correlation']
    assert sent['type']==(0 if direction=='BUY' else 1)
    assert 'price' not in sent
    assert sent['deviation']<=50


def test_limit_mapping(tmp_path):
    native,adapter,command=adapter_fixture(tmp_path,entry=99.9,entry_type='LIMIT')
    assert adapter.submit(command).outcome=='ACKNOWLEDGED'
    assert native.sent[0]['action']==native.TRADE_ACTION_PENDING
    assert native.sent[0]['type']==native.ORDER_TYPE_BUY_LIMIT
    assert native.sent[0]['type_filling']==native.ORDER_FILLING_RETURN
    assert native.sent[0]['price']==99.9


@pytest.mark.parametrize('where,field,value', [
    ('account','trade_mode',2),('account','trade_mode',1),('account','login',999),
    ('account','server','real-server'),('account','currency','EUR'),('account','margin_mode',0),
    ('account','trade_allowed',False),('account','trade_expert',False),
    ('terminal','connected',False),('terminal','trade_allowed',False),('terminal','tradeapi_disabled',True),
    ('info','point',0),('info','volume_step',0),('info','trade_mode',0),('info','filling_mode',0),
    ('tick','ask',100.1),('tick','ask',float('nan')),('tick','bid',float('inf')),
    ('tick','time_msc',int((TIME-timedelta(seconds=4)).timestamp()*1000))])
def test_native_shape_fail_closed(tmp_path,where,field,value):
    native,adapter,command=adapter_fixture(tmp_path)
    setattr(getattr(native,where),field,value)
    with pytest.raises(ValueError):adapter.submit(command)
    assert native.sent==[]


@pytest.mark.parametrize('retcode,order,deal,expected', [(10006,0,0,'REJECTED'),(10012,0,0,'AMBIGUOUS'),
    (10031,0,0,'AMBIGUOUS'),(99999,0,0,'AMBIGUOUS'),(10006,321,654,'AMBIGUOUS'),
    (10009,0,654,'AMBIGUOUS'),(10010,321,654,'ACKNOWLEDGED'),(10008,321,0,'ACKNOWLEDGED')])
def test_response_classification_no_retries(tmp_path,retcode,order,deal,expected):
    native,adapter,command=adapter_fixture(tmp_path)
    native.result=NS(retcode=retcode,order=order,deal=deal)
    assert adapter.submit(command).outcome==expected
    assert len(native.sent)==1


def test_none_response_ambiguous(tmp_path):
    native,adapter,command=adapter_fixture(tmp_path)
    native.result=None
    assert adapter.submit(command).outcome=='AMBIGUOUS'


def test_account_switch_before_send_blocked(tmp_path):
    native,adapter,command=adapter_fixture(tmp_path)
    def switch(c):
        if c.account_calls==2:c.account.trade_mode=2
    native.on_account=switch
    with pytest.raises(ValueError):adapter.submit(command)
    assert native.sent==[]


def test_expired_command_never_sends(tmp_path):
    native,adapter,command=adapter_fixture(tmp_path)
    command['valid_until']=TIME.isoformat()
    with pytest.raises(ValueError):adapter.submit(command)
    assert native.sent==[]


def test_missing_snapshot_no_empty_inventory_fallback(tmp_path):
    _,adapter,_=adapter_fixture(tmp_path)
    with pytest.raises(ValueError):adapter.snapshot(TIME)
