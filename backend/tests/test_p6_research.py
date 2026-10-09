"""Synthetic test-only prices, never qualified or promoted to research evidence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import json
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import subprocess
import sys
from types import MappingProxyType

import pytest

from core.rebuild.market_data import Candle, MarketStore, digest
from core.rebuild.research_strategies import BaseStrategy, Features, Frame, catalogue
from core.rebuild.strategy_research import (Costs, ResearchData, ResearchLedger, barrier,
    canonical_signal, finer_bars, frames, make_signal, metrics, reconstruct, replay, validate_geometry)

T = datetime(2025, 9, 2, tzinfo=timezone.utc)


def bar(i=0, *, o='100', h='101', l='99', c='100', spread='.1', frame='1H', symbol='XAUUSD'):
    values = dict(open=D(o), high=D(h), low=D(l), close=D(c))
    hours = 1 if frame == '1H' else 4
    return Candle(instrument=symbol, provider='EV_TRADING_LABS', provider_symbol='WTI' if symbol == 'USOIL' else symbol,
        timeframe=frame, opened=T+timedelta(hours=i), closed=T+timedelta(hours=i+hours),
        **values, ask_ohlc={k:v+D(spread) for k,v in values.items()}, price_basis='BID',
        source_time=str(i), timezone_evidence='synthetic UTC test fixture', volume_kind='NONE')


def data(rows=None, *, symbol='XAUUSD'):
    rows = tuple(rows or (bar(i, o=str(100+i%13),h=str(102+i%13),l=str(98+i%13),c=str(101+i%13), symbol=symbol) for i in range(90)))
    return ResearchData(digest([b.payload() for b in rows]), 'f'*64, rows[0].opened, rows[-1].closed, rows,
                        json.dumps({'fixture':True}), fixture=True)


def signal(side='BUY', **updates):
    out = dict(signal_timestamp=T.isoformat(), direction=side, stop_loss='90' if side=='BUY' else '110',
               take_profit='120' if side=='BUY' else '80')
    out.update(updates)
    return out


def rule_case(rule, side):
    v = dict(close=D(101),low=D(98),high=D(102),atr=D(2))
    p = dict(close=D(100))
    buy = side == 'BUY'
    if rule.startswith('ema_cross_'):
        a,b = rule.removeprefix('ema_cross_').split('_')
        p.update({'ema'+a:D(99 if buy else 101),'ema'+b:D(100)})
        v.update({'ema'+a:D(101 if buy else 99),'ema'+b:D(100)})
    elif rule in {'macd','ema_pullback'}:
        a,b = ('macd','macd_signal') if rule == 'macd' else ('close','ema200')
        p.update({a:D(99 if buy else 101),b:D(100)})
        v.update({a:D(101 if buy else 99),b:D(100)})
    elif rule in {'supertrend','adx','rsi','rsi2','stochastic','williams','cci'}:
        key, lo, hi = {'supertrend':('st_direction',0,0),'adx':('di_difference',0,0),
                      'rsi':('rsi14',30,70),'rsi2':('rsi2',10,90),'stochastic':('stochastic',20,80),
                      'williams':('williams',-80,-20),'cci':('cci',-100,100)}[rule]
        p[key] = D(lo-1 if buy else hi+1)
        v[key] = D(lo+1 if buy else hi-1)
        v['adx'] = D(30)
    elif rule == 'divergence':
        v.update(div_price=D(-1 if buy else 1),div_rsi=D(1 if buy else -1),rsi14=D(35 if buy else 65))
    elif rule.startswith('bb_'):
        p.update(bb_lower=D(99),bb_upper=D(103),close=D(98 if buy else 104))
        v.update(bb_lower=D(99),bb_upper=D(103),low=D(98 if buy else 100), high=D(102 if buy else 104))
    elif rule in {'donchian','atr_breakout','day','week','london','ny','hhhl'}:
        prefix = 'prior' if rule in {'donchian','atr_breakout'} else ('recent' if rule=='hhhl' else rule)
        v.update({prefix+'_high':D(101),prefix+'_low':D(99), 'close':D(102 if buy else 98), 'consolidation_width':D(3),
                  'earlier_high':D(100 if buy else 103),'earlier_low':D(97 if buy else 100)})
    elif rule == 'flip':
        p.update(prior_high=D(100),prior_low=D(99),close=D(101 if buy else 98))
        v.update(close=D(101 if buy else 98))
    elif rule == 'sweep':
        v.update(prior_high=D(103 if buy else 101),prior_low=D(99 if buy else 97),close=D(100))
    elif rule == 'fvg': v['fvg_buy' if buy else 'fvg_sell'] = D(1)
    elif rule == 'fib':
        v.update(prior_high=D(110),prior_low=D(90),ema50=D(99 if buy else 102),low=D(97),high=D(103))
    return v, p, 9 if rule == 'london' else 14


IMPLEMENTED = [s for s in catalogue() if s.eligibility in {'TOURNAMENT_READY','EXPERIMENTAL'}]


@pytest.mark.parametrize('strategy',IMPLEMENTED,ids=lambda s:s.strategy_id)
@pytest.mark.parametrize('side',['BUY','SELL'])
def test_each_implemented_rule_positive_and_no_evidence(strategy, side):
    v,p,hour = rule_case(strategy.rule, side)
    assert strategy.evaluate(v,p,hour) == side
    assert strategy.evaluate({}, {}, hour) is None
    f = Frame(bar(hour),0,MappingProxyType(v),MappingProxyType(p))
    assert strategy.direction(f) is None


def test_catalogue_honest_classifications():
    rows = catalogue()
    assert len(rows) == len({s.strategy_id for s in rows}) == 30
    assert len(IMPLEMENTED) == 26
    assert sum(s.eligibility=='TOURNAMENT_READY' for s in rows) == 20
    assert sum(s.eligibility=='EXPERIMENTAL' for s in rows) == 6
    assert sum(s.eligibility=='INSUFFICIENT_DEFINITION' for s in rows) == 3
    assert rows[22].eligibility == 'DISABLED_VOLUME_SEMANTICS'
    for s in rows:
        assert s.parameters and s.version and s.instruments


def test_closed_history_prefix_future_mutation_and_indicator_initialization():
    a = data()
    b = data(a.bars[:60]+tuple(bar(i,o='200',h='220',l='180',c='210') for i in range(60,90)))
    x,y = list(frames(a)),list(frames(b))
    assert x[:60] == y[:60]
    assert 'ema21' not in x[19].features
    assert abs(x[20].features['ema21']-sum(z.close for z in a.bars[:21])/21) < D('1e-25')
    for s in IMPLEMENTED:
        assert [make_signal(s,f,a) for f in x[:60]] != []
        assert [s.direction(f) for f in x[:60]] == [s.direction(f) for f in y[:60]]
    with pytest.raises(TypeError): x[50].features['close'] = D(0)
    assert not hasattr(x[50], 'outcome') and not hasattr(x[50], 'future')


def test_flat_and_monotone_rsi_not_silent_fallback():
    flat = list(frames(data(tuple(bar(i) for i in range(25)))))
    assert flat[-1].features['rsi14'] == 50
    rising = list(frames(data(tuple(bar(i,o=str(100+i),h=str(102+i),l=str(99+i),c=str(101+i)) for i in range(25)))))
    assert rising[-1].features['rsi14'] == 100


def test_context_only_closed_and_exact_identity():
    primary = data(tuple(bar(i) for i in range(12)))
    context = data(tuple(bar(i,frame='4H') for i in (0,4,8)))
    result = list(frames(primary,context))
    assert all(x.context is None for x in result[:3])
    assert result[3].context.closed == T+timedelta(hours=4)
    assert result[6].context.closed == T+timedelta(hours=4)
    assert result[7].context.closed == T+timedelta(hours=8)
    with pytest.raises(ValueError): Features().push(primary.bars[0],context.bars[0])
    with pytest.raises(ValueError): list(frames(primary,data(tuple(bar(i,frame='4H',symbol='XAGUSD') for i in (0,4,8)))))


@pytest.mark.parametrize('side,entry,stop,target',[('BUY','100','90','115'),('SELL','100','110','85')])
def test_rr_exact_boundary(side,entry,stop,target):
    assert validate_geometry(side,entry,stop,target)[1] == D('1.5')
    with pytest.raises(ValueError): validate_geometry(side,entry,stop,'114.999' if side=='BUY' else '85.001')
    with pytest.raises(ValueError): validate_geometry(side,entry,stop,target,Costs(commission_per_unit_round_trip='0.1',commission_evidence='fixture'))


@pytest.mark.parametrize('bad',['NaN','Infinity','-Infinity','0','-1',True])
def test_nonfinite_bad_geometry(bad):
    with pytest.raises(ValueError): validate_geometry('BUY',bad,'90','120')


def test_geometry_no_unknown_action_or_repair():
    for side in ('HOLD','buy',None):
        with pytest.raises(ValueError): validate_geometry(side,'100','90','120')
    with pytest.raises(ValueError): validate_geometry('SELL','100','90','120')
    with pytest.raises(ValueError): reconstruct(signal(),[bar(o='125',h='130',l='120',c='126')])


@pytest.mark.parametrize('side',['BUY','SELL'])
def test_entry_exit_side_spread_and_costs(side):
    out,_ = reconstruct(signal(side),[bar()],costs=Costs(),horizon=1)
    assert D(out['base_entry']) == (D('100.1') if side=='BUY' else D(100))
    assert out['outcome']=='TIMEOUT' and D(out['pnl_per_unit']) < D('-.1')
    assert out['cost_model']['commission_status']=='EXCLUDED_UNKNOWN'
    assert out['exit_timestamp'] == bar().closed.isoformat()
    with pytest.raises(ValueError): Costs(commission_per_unit_round_trip='0.1')
    fee,_=reconstruct(signal(side),[bar()],costs=Costs(commission_per_unit_round_trip='.1',commission_evidence='synthetic fee/unit'),horizon=1)
    assert D(fee['pnl_per_unit']) == D(out['pnl_per_unit'])-D('.1')


@pytest.mark.parametrize('h,l,outcome',[('121','99','WIN'),('101','89','LOSS'),('121','89','AMBIGUOUS')])
def test_tp_sl_both_barriers(h,l,outcome):
    result,_=reconstruct(signal(),[bar(h=h,l=l)])
    assert result['outcome']==outcome
    assert (result['r_multiple'] is None)==(outcome=='AMBIGUOUS')


def test_gap_loss_is_not_clamped_to_stop_and_no_fabricated_close():
    result,_=reconstruct(signal(),[bar(),bar(1,o='85',h='87',l='84',c='86')])
    assert result['outcome']=='LOSS' and D(result['exit_price']) < 85
    assert not result['broker_observed'] and result['exit_timestamp'] == bar(1).opened.isoformat()


def test_timeout_unknown_split_and_no_entry():
    assert reconstruct(signal(),[bar()],horizon=1)[0]['outcome']=='TIMEOUT'
    assert reconstruct(signal(),[bar()],horizon=2)[0]['outcome']=='UNKNOWN'
    assert reconstruct(signal(),[])[0]['reason']=='NO_ENTRY_BAR'


def test_finer_qualified_shape_disambiguates_without_inventing_order():
    large=bar(frame='4H',h='121',l='89')
    small=data((bar(0,h='121'),bar(1,h='121',l='89'),bar(2),bar(3)))
    assert len(finer_bars(large,small))==4
    result,_=reconstruct(signal(),[large],lower=small)
    assert result['outcome']=='WIN' and result['lower_dataset_id']==small.dataset_id
    broken=data((bar(0,h='120'),bar(1,l='89'),bar(2),bar(3)))
    assert reconstruct(signal(),[large],lower=broken)[0]['outcome']=='AMBIGUOUS'
    ambiguous=data((bar(0,h='121',l='89'),bar(1),bar(2),bar(3)))
    assert reconstruct(signal(),[large],lower=ambiguous)[0]['outcome']=='AMBIGUOUS'


def test_metrics_zero_exclusions_and_exact_denominators():
    rows=[dict(outcome=k,r_multiple=r,holding_hours_upper_bound='2') for k,r in
          [('WIN','2'),('LOSS','-1'),('BREAKEVEN','0'),('TIMEOUT','-.5'),('AMBIGUOUS',None),('UNKNOWN',None)]]
    m=metrics(rows,[],Costs())
    assert m['resolved_barrier_denominator']==3
    assert D(m['win_rate']) == D(1)/3
    assert D(m['expectancy_r']) == D('.125')
    assert D(m['total_r']) == D('.5') and D(m['max_drawdown_r']) == D('1.5')
    assert D(m['profit_factor']) == D(2)/D('1.5')
    assert m['excluded_outcome_count']==2 and m['sharpe'] is None
    z=metrics([],[],Costs())
    assert z['win_rate'] is None and z['profit_factor'] is None and z['research_trade_count']==0


def test_replay_identity_splits_versions_instrument_and_canonical_mapping():
    d=data()
    s=catalogue()[0]
    a=replay(d,s,start=d.start,end=d.end,horizon=3)
    assert a==replay(d,s,start=d.start,end=d.end,horizon=3)
    assert a['run_id']!=replay(d,replace(s,version='test-v2'),start=d.start,end=d.end,horizon=3)['run_id']
    assert a['run_id']!=replay(d,s,start=d.start,end=d.end,costs=Costs('0.02'),horizon=3)['run_id']
    other=data(symbol='XAGUSD')
    assert a['run_id']!=replay(other,s,start=other.start,end=other.end,horizon=3)['run_id']
    assert a['signals']
    canonical=canonical_signal(a['signals'][0])
    assert canonical.source_type=='NEXUSAI_STRATEGY' and canonical.symbol=='XAUUSD'
    assert canonical.signal_id==a['signals'][0]['signal_id']
    split=T+timedelta(hours=60)
    early=replay(d,s,start=d.start,end=split)
    changed=data(d.bars[:60]+tuple(bar(i,o='250',h='260',l='240',c='250') for i in range(60,90)))
    replay_changed=replay(changed,s,start=d.start,end=split)
    assert [(x['signal_timestamp'],x['direction']) for x in early['signals']]==[(x['signal_timestamp'],x['direction']) for x in replay_changed['signals']]
    assert [t['outcome'] for t in early['trades']]==[t['outcome'] for t in replay_changed['trades']]
    assert all(not t.get('exit_interval_end') or datetime.fromisoformat(t['exit_interval_end'])<=split for t in early['trades'])
    with pytest.raises(ValueError): replay(d,s,start=d.start-timedelta(hours=1),end=d.end)


def test_ledger_atomic_retry_concurrent_restart_and_immutable(tmp_path):
    store=MarketStore(tmp_path/'research',fixture=True)
    ledger=ResearchLedger(store)
    d=data(); report=replay(d,catalogue()[0],start=d.start,end=d.end,horizon=3)
    def crash(): raise RuntimeError('fixture crash before trade publication')
    with pytest.raises(RuntimeError): ledger.save(report,checkpoint=crash)
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM p6_runs').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM p6_trades').fetchone()[0]==0
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(lambda _:ledger.save(report),range(8))))==1
    restarted=ResearchLedger(MarketStore(store.root,fixture=True))
    assert restarted.read(report['run_id'])==report
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM p6_trades').fetchone()[0]==len(report['trades'])
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM p6_runs')
    tampered=json.loads(json.dumps(report)); tampered['metrics']['total_r']='999'
    with pytest.raises(ValueError): ledger.save(tampered)


def test_p5_reader_mandatory_not_duck_typed_and_fixture_not_qualified(tmp_path):
    from core.rebuild.research_reader import ResearchDatasetReader
    with pytest.raises(ValueError): ResearchData.load(object(),'x',dataset_id='x',start=T,end=T+timedelta(hours=1))
    with pytest.raises(ValueError): ResearchData.load(ResearchDatasetReader(MarketStore(tmp_path/'r',fixture=True)),
                                                    'x',dataset_id='x',start=T,end=T+timedelta(hours=1))
    with pytest.raises(ValueError): data((bar(1),bar(0)))
    with pytest.raises(ValueError): data((bar(0),bar(1,symbol='XAGUSD')))


def test_sessions_are_fixed_utc_and_no_4h_window_guess():
    london=catalogue()[18]; ny=catalogue()[19]
    for s in (london,ny):
        v,p,hour=rule_case(s.rule,'BUY')
        assert s.evaluate(v,p,hour)=='BUY'
        assert s.evaluate(v,p,0) is None
        assert s.direction(Frame(bar(0,frame='4H'),500,v,p)) is None


def test_module_imports_no_execution_runtime():
    assert not any(m in {'MetaTrader5','main','legacy_application'} or m.startswith('agents.') for m in sys.modules)


def test_process_death_rolls_back_replay_then_restart(tmp_path):
    # Child inherits scrubbed environment; uses only this synthetic temporary research store.
    root=tmp_path/'crash-research'
    script='''
import os,sys
sys.path[:0]=['backend','backend/tests']
from test_p6_research import data,catalogue
from core.rebuild.market_data import MarketStore
from core.rebuild.strategy_research import ResearchLedger,replay
s=MarketStore(sys.argv[1],fixture=True)
d=data(); r=replay(d,catalogue()[0],start=d.start,end=d.end,horizon=3)
ResearchLedger(s).save(r,checkpoint=lambda:os._exit(73))
'''
    result=subprocess.run([sys.executable,'-B','-c',script,str(root)],capture_output=True,text=True,timeout=40)
    assert result.returncode==73, result.stderr
    store=MarketStore(root,fixture=True); ledger=ResearchLedger(store)
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM p6_runs').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM p6_trades').fetchone()[0]==0
    d=data(); report=replay(d,catalogue()[0],start=d.start,end=d.end,horizon=3)
    ledger.save(report)
    assert ledger.read(report['run_id'])==report


def test_horizon_cost_range_and_invalid_stop_no_fallback():
    for value in (0,-1,True,1.5):
        with pytest.raises(ValueError): reconstruct(signal(),[bar()],horizon=value)
    for value in ('NaN','Infinity','-1','1.01'):
        with pytest.raises(ValueError): Costs(value)
    d=data(); s=catalogue()[0]
    v,p,h=rule_case(s.rule,'BUY')
    v['atr']=D(0)
    with pytest.raises(ValueError): make_signal(s,Frame(bar(),500,v,p),d)
    with pytest.raises(ValueError): replace(s,parameters=(('atr_period','99'),('stop_atr','2'),('reward_r','2')))
    with pytest.raises(ValueError): replace(s,parameters=(('atr_period','14'),('stop_atr','NaN'),('reward_r','2')))
    with pytest.raises(ValueError): replay(d,catalogue()[26],start=d.start,end=d.end,horizon=0)


def test_unknown_outcome_does_not_break_metric_denominator_or_assign_zero():
    m=metrics([dict(outcome='UNKNOWN',r_multiple=None),dict(outcome='AMBIGUOUS',r_multiple=None)],[],Costs())
    assert m['priced_denominator']==0 and m['average_r'] is None and m['win_rate'] is None
    assert m['excluded_outcome_rate']=='1'


def test_forged_fixture_cannot_claim_qualified_evidence():
    d=data()
    with pytest.raises((ValueError,KeyError)): replace(d,fixture=False)


def test_loader_pins_real_contract_and_detects_mutated_content(tmp_path,monkeypatch):
    from core.rebuild.research_reader import ResearchDatasetReader
    store=MarketStore(tmp_path/'raw-fixture',fixture=True)
    reader=ResearchDatasetReader(store)
    rows=[bar().payload()]
    manifest=dict(real_data=True,content_hash=digest(rows))
    ds=digest(manifest)
    q=dict(dataset_id=ds,state='QUALIFIED_WITH_KNOWN_LIMITATIONS')
    qi=digest(q)
    view=dict(dataset_id=ds,qualification=q,manifest=manifest,candles=rows,provenance=[{'fixture':'synthetic loader contract'}])
    monkeypatch.setattr('core.rebuild.strategy_research.fixture_store',lambda _:False)
    monkeypatch.setattr(reader,'query',lambda *a,**kw:view)
    monkeypatch.setattr(store,'query',lambda *a,**kw:dict(candles=rows))
    loaded=ResearchData.load(reader,qi,dataset_id=ds,start=T,end=T+timedelta(hours=1))
    assert loaded.dataset_id==ds
    with pytest.raises(ValueError): ResearchData.load(reader,'wrong',dataset_id=ds,start=T,end=T+timedelta(hours=1))
    with pytest.raises(ValueError): ResearchData.load(reader,qi,dataset_id='wrong',start=T,end=T+timedelta(hours=1))
    monkeypatch.setattr(store,'query',lambda *a,**kw:dict(candles=[bar(c='100.5').payload()]))
    with pytest.raises(ValueError,match='content changed'):
        ResearchData.load(reader,qi,dataset_id=ds,start=T,end=T+timedelta(hours=1))


def test_unsupported_timeframe_is_classified_in_stored_artifact():
    d=data(tuple(bar(i,frame='4H') for i in range(0,40,4)))
    report=replay(d,catalogue()[18],start=d.start,end=d.end)
    assert report['eligibility']=='INSUFFICIENT_DATA'
    assert report['metrics']['research_trade_count']==0


def test_p6_canonical_representation_does_not_authorize_p4_source(tmp_path):
    from core.rebuild.source_registry import SourceRule, SourceConfiguration, check_signal
    from core.rebuild.source_ingestion import SourceIngestion, SourceSubmission
    from core.rebuild.ledger import Ledger
    ledger=Ledger(tmp_path/'canonical.sqlite3')
    d=data(); s=catalogue()[0]
    report=replay(d,s,start=d.start,end=d.end)
    original=report['signals'][0]; canonical=canonical_signal(original)
    rule=SourceRule(source_type='NEXUSAI_STRATEGY',source_id=canonical.source_id)
    service=SourceIngestion(ledger,SourceConfiguration(sources=(rule,)),clock=lambda:d.end)
    request=SourceSubmission(source_type='NEXUSAI_STRATEGY',source_id=canonical.source_id,
        message_id=canonical.signal_id,original_timestamp=original['signal_timestamp'],timezone_evidence='UTC',
        provenance={'dataset_id':d.dataset_id,'research_run_id':report['run_id']},
        strategy_id=s.strategy_id,strategy_version=s.version,
        signal=dict(instrument=canonical.symbol,direction=canonical.direction,entry_type='MARKET',
                    entry=canonical.entry,stop_loss=canonical.stop_loss,take_profit=canonical.take_profit))
    result=service.ingest(request)
    assert result['status']=='VALIDATED'
    assert result['broker_execution']=='HARD_DISABLED' and result['execution_eligibility']=='NONE'
    assert service.ingest(request)==result
    with ledger.connect() as conn:
        with pytest.raises(ValueError,match='P4_SOURCE_RESEARCH_ONLY'):
            check_signal(conn,result['signal_id'],current=d.end)
        assert conn.execute('SELECT COUNT(*) FROM p3_attempts').fetchone()[0]==0
    with pytest.raises(ValueError):
        SourceRule(source_type='NEXUSAI_STRATEGY',source_id=canonical.source_id,execution_eligibility='P2_ONLY')
