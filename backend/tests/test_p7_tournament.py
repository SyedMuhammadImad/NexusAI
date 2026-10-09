"""Test-only synthetic metrics/prices never become qualified research evidence."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
from datetime import timedelta
import json
import sqlite3
import pytest

from core.rebuild.market_data import MarketStore, digest
from core.rebuild.strategy_research import Costs, ResearchLedger, replay
from core.rebuild.research_strategies import catalogue
from core.rebuild.tournament import (assess, split_at, correlation, daily_returns,
    removal_metrics, run_tournament, save_tournament, validate_replay)
from test_p6_research import T, bar, data


def metric(**changes):
    result=dict(resolved_barrier_denominator=30,expectancy_r='.1',profit_factor='1.20',
                win_rate='.35',max_drawdown_r='10',excluded_outcome_rate='.10')
    result.update(changes)
    return result


def verdict(dev=None,oos=None,**flags):
    defaults=dict(data_quality=True,leakage=True,cost_assumption=True); defaults.update(flags)
    return assess(dev or metric(),oos or metric(resolved_barrier_denominator=20),**defaults)


def test_inclusive_boundaries_and_research_only():
    v=verdict()
    assert v['status']=='RESEARCH_QUALIFIED'
    assert len(v['gates'])==10 and all(g['status']=='PASS' for g in v['gates'].values())
    assert not v['execution_eligible'] and v['warning']=='SHORT_SAMPLE_RESEARCH_ONLY'


@pytest.mark.parametrize('field,value,gate',[
    ('expectancy_r','0','EXPECTANCY'),('expectancy_r','-.001','EXPECTANCY'),
    ('profit_factor','1.199999','PROFIT_FACTOR'),('win_rate','.349999','WIN_RATE'),
    ('max_drawdown_r','10.000001','DRAWDOWN'),('excluded_outcome_rate','.100001','AMBIGUITY')])
def test_each_numeric_gate_fails(field,value,gate):
    result=verdict(oos=metric(**{field:value}))
    assert result['status']=='REJECTED' and result['gates'][gate]['status']=='FAIL'


@pytest.mark.parametrize('field',['expectancy_r','profit_factor','win_rate','max_drawdown_r','excluded_outcome_rate'])
@pytest.mark.parametrize('value',[None,'NaN','Infinity','-Infinity',True])
def test_missing_nonfinite_metrics_never_qualify(field,value):
    assert verdict(oos=metric(**{field:value}))['status']=='INSUFFICIENT_EVIDENCE'


@pytest.mark.parametrize('a,b',[(29,20),(50,19),(0,0)])
def test_samples_cannot_be_rescued_by_performance(a,b):
    assert verdict(metric(resolved_barrier_denominator=a),metric(resolved_barrier_denominator=b))['status']=='INSUFFICIENT_EVIDENCE'


@pytest.mark.parametrize('bad',[-1,True,2.5,'50',None])
def test_invalid_sample_count(bad):
    with pytest.raises(ValueError): verdict(oos=metric(resolved_barrier_denominator=bad))


def test_degradation_boundaries():
    assert verdict(metric(profit_factor='2.4'))['status']=='RESEARCH_QUALIFIED'
    assert verdict(metric(profit_factor='2.400001'))['gates']['DEGRADATION']['status']=='FAIL'
    assert verdict(oos=metric(expectancy_r='0'))['gates']['DEGRADATION']['status']=='FAIL'
    v=verdict(metric(profit_factor=None))
    assert v['gates']['DEGRADATION']['evidence']['pf_check']=='NOT_APPLICABLE'


@pytest.mark.parametrize('flag',['data_quality','leakage','cost_assumption'])
@pytest.mark.parametrize('value',[False,None,'True'])
def test_integrity_gates_override_small_sample(flag,value):
    assert verdict(oos=metric(resolved_barrier_denominator=1),**{flag:value})['status']=='REJECTED'


def test_split_is_chronological_aligned_and_not_bar_shuffled():
    end=T+timedelta(hours=2084)
    assert split_at(T,end)==T+timedelta(hours=1456)
    with pytest.raises(ValueError): split_at(T,T+timedelta(hours=1))
    with pytest.raises(ValueError): split_at(T.replace(tzinfo=None),end)


def test_correlation_absolute_cluster_and_insufficient_variance():
    vectors={'a':{'1':D(1),'2':D(2),'3':D(3)},'b':{'1':D(-1),'2':D(-2),'3':D(-3)},
             'flat':{'1':D(0),'2':D(0),'3':D(0)}}
    out=correlation(vectors)
    assert out['clusters']==[['a','b']]
    assert out['pairs'][0]['pearson']=='-1'
    assert any(p['status']=='INSUFFICIENT_EVIDENCE' for p in out['pairs'])
    assert correlation({})['status']=='NOT_APPLICABLE_NO_QUALIFIED_PAIR'
    assert correlation({'a':vectors['flat'],'b':vectors['flat']})['status']=='INSUFFICIENT_EVIDENCE'


def test_unresolved_days_are_not_synthetic_zero_returns():
    report={'configuration':{'start':T.isoformat(),'end':(T+timedelta(days=3)).isoformat()},
            'trades':[{'entry_at':T.isoformat(),'r_multiple':None}]}
    assert all(v is None for v in daily_returns(report).values())
    assert len(daily_returns(report,{T.date().isoformat()}))==1


def test_correlation_exact_point_eight_passes():
    x=dict(zip('1234',map(D,['-1','-1','1','1'])))
    y=dict(zip('1234',map(D,['-1.4','-.2','.2','1.4'])))
    p=correlation({'x':x,'y':y})['pairs'][0]
    assert D(p['pearson'])==D('.8') and p['highly_correlated']


@pytest.mark.parametrize('key,value',[('profit_factor','-1'),('max_drawdown_r','-1'),
    ('win_rate','1.01'),('excluded_outcome_rate','-.1')])
def test_impossible_metric_ranges_abort(key,value):
    with pytest.raises(ValueError): verdict(oos=metric(**{key:value}))


def test_best_worst_removal_preserves_other_trade_order():
    rows=[dict(research_trade_id=str(i),outcome='WIN' if r>0 else 'LOSS',r_multiple=str(r))
          for i,r in enumerate([2,-1,2,-2])]
    report=dict(trades=rows,signals=[])
    assert removal_metrics(report,True)['removed_trade_id']=='0'
    assert removal_metrics(report,False)['removed_trade_id']=='3'
    assert D(removal_metrics(report,True)['metrics']['total_r'])==D(-1)


def test_p6_validation_detects_tampering_and_parameters():
    d=data(); s=catalogue()[0]
    with localcontext() as ctx:
        ctx.prec=40
        r=replay(d,s,start=d.start,end=d.end)
        assert validate_replay(r,d,s,d.start,d.end,Costs(),None)
        bad=deepcopy(r); bad['metrics']['expectancy_r']='999'
        bad['artifact_id']=digest({k:v for k,v in bad.items() if k!='artifact_id'})
        with pytest.raises(ValueError,match='metric'): validate_replay(bad,d,s,d.start,d.end,Costs(),None)
        bad=deepcopy(r); bad['configuration']['strategy']['version']='tampered'
        with pytest.raises(ValueError): validate_replay(bad,d,s,d.start,d.end,Costs(),None)
        assert removal_metrics(r,True)['status'] in {'MEASURED','INSUFFICIENT_EVIDENCE'}


def test_full_fixture_tournament_restart_idempotency_and_immutability(tmp_path):
    store=MarketStore(tmp_path/'p7',fixture=True)
    loaded={}
    for symbol in ('XAUUSD','XAGUSD','USOIL'):
        for frame,step in [('1H',1),('4H',4)]:
            loaded[symbol,frame]=data(tuple(bar(i,frame=frame,symbol=symbol) for i in range(0,96,step)),symbol=symbol)
    result=run_tournament(loaded,ResearchLedger(store))
    assert len(result['cells'])==180 and result['counts']['EXCLUDED']==66
    assert result['verified_replays']==570 and result['counts']['RESEARCH_QUALIFIED']==0
    assert result['configuration']['evidence_scope']=='FIXTURE'
    assert result['result']=='NO_STRATEGY_RESEARCH_QUALIFIED'
    save_tournament(store,result); save_tournament(store,result)
    with MarketStore(tmp_path/'p7',fixture=True).connect() as c:
        rows=c.execute('SELECT payload FROM p7_runs').fetchall()
        assert len(rows)==1 and json.loads(rows[0][0])==result
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM p7_runs')
    bad=deepcopy(result); bad['counts']['RESEARCH_QUALIFIED']=999
    with pytest.raises(ValueError): save_tournament(store,bad)
    bad['result_id']=digest({k:v for k,v in bad.items() if k!='result_id'})
    with pytest.raises(ValueError,match='conflict'): save_tournament(store,bad)
    from core.rebuild.tournament_projection import project, TournamentReader
    from core.rebuild.application import create_app
    from fastapi.testclient import TestClient
    projection=project(result,ResearchLedger(store))
    assert projection==project(result,ResearchLedger(store))
    assert len(projection['strategies'])==20
    view=projection['views']['XAGUSD:1H']
    assert all(r['status']=='ACTIVE' for r in view['snapshots'][0])
    assert all(r['status']=='INSUFFICIENT_EVIDENCE' for r in view['snapshots'][-1])
    assert all(r['status'] not in {'REJECTED','INSUFFICIENT_EVIDENCE','RESEARCH_QUALIFIED'} for rows in view['snapshots'][:-1] for r in rows)
    assert all(e['at']==result['configuration']['end'] for e in projection['events'] if e['type']=='FINAL_STATUS')
    assert any(e['type']=='OOS_START' and e['at']==result['configuration']['split'] for e in projection['events'])
    assert any(e['type']=='GATE_TRANSITION' for e in projection['events'])
    for row in view['snapshots'][-1]:
        assert row['gates']==view['cells'][row['cell_id']]['gates']
    payload=tmp_path/'arena.json'; payload.write_text(json.dumps(projection),encoding='utf-8')
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(dict(filename=payload.name,projection_id=projection['projection_id'],result_id=result['result_id'])),encoding='utf-8')
    reader=TournamentReader(manifest)
    assert reader.read()==projection
    from test_p2_safety import ACCOUNT
    app=create_app(database_path=tmp_path/'lifecycle.sqlite3',token='fixture-p7-only',fixture_mode=True,tournament_reader=reader,lifecycle_account=ACCOUNT)
    with TestClient(app) as client:
        assert client.get('/api/core/tournament/summary').status_code==403
        client.headers['X-Control-Token']='fixture-p7-only'
        assert client.get('/api/core/tournament/summary').json()['result_id']==result['result_id']
        response=client.get('/api/core/tournament/snapshot',params={'index':len(projection['timeline'])-1}).json()
        assert response['rows']==view['snapshots'][-1] and len(response['events'])<=40
        early=client.get('/api/core/tournament/inspector',params={'cell_id':'p6-01:XAGUSD:1H','index':0}).json()
        assert early['robustness'] is None and early['correlation'] is None
        assert client.get('/api/core/tournament/snapshot?index=127').status_code==422
        assert client.get('/api/core/tournament/snapshot?instrument=BAD').status_code==422
        assert client.post('/api/core/tournament/snapshot').status_code==423
        assert app.state.execution is None
        assert reader.read()==projection
