"""Fixture-only P8 temporal, baseline, registry and research firewall regressions."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

import numpy as np
import pytest

from core.rebuild.market_data import Candle,digest,encode
from core.rebuild.p8_evidence import (NUMERIC,CATEGORIES,SCHEMA_ID,LABEL_POLICY,
    features,folds,stamp,validate_features,verify)
from core.rebuild.p8_models import (evaluate,train,predict_artifact,metrics,
    trade_stats,filter_stats,POLICY)
from core.rebuild.p8_registry import Registry
from core.rebuild.p8_human import audit_archive,records
from core.rebuild.p8_kronos import context_view,audit_runtime
from core.rebuild.p8_projection import projection

T=datetime(2025,9,2,tzinfo=timezone.utc)


def sample(i):
    f={k:float((i%17)+1) for k in NUMERIC}
    f.update(instrument=('XAUUSD','XAGUSD','USOIL')[i%3],timeframe='1H',
             direction='BUY' if i%2 else 'SELL',family='TREND',strategy_id='p6-01' if i%3 else 'p6-02')
    return dict(id=str(i),signal_at=(T+timedelta(hours=i)).isoformat(),
        resolved_at=(T+timedelta(hours=i+1)).isoformat(),feature_available_at=(T+timedelta(hours=i)).isoformat(),
        label=i%2,outcome='WIN' if i%2 else 'LOSS',features=f,r_multiple=1.7 if i%2 else -1,
        schema_id=SCHEMA_ID,label_policy=LABEL_POLICY)


def bar(i=0):
    return Candle(instrument='XAUUSD',provider='EV_TRADING_LABS',provider_symbol='XAUUSD',timeframe='1H',
        opened=T+timedelta(hours=i),closed=T+timedelta(hours=i+1),open=100,high=102,low=99,close=101,
        ask_ohlc=dict(open='100.1',high='102.1',low='99.1',close='101.1'),price_basis='BID',
        volume=0,volume_kind='UNKNOWN',timezone_evidence='fixture UTC',source_time='fixture')


def signal():
    return dict(signal_timestamp=bar().closed.isoformat(),instrument='XAUUSD',timeframe='1H',direction='BUY',
        family='TREND',strategy_id='p6-01',entry_reference='101.1',stop_loss='99.1',take_profit='105.1',
        features=dict(rsi14='50',atr='1',ema20='100',ema50='100',macd='0.1'),context_closed_at=None)


def archive(text):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z: z.writestr('_chat.txt',text)
    return b.getvalue()


def entry(status='EXPERIMENTAL'):
    return dict(track='PROFITABILITY',task='fixture WIN/LOSS',model_type='prior',dataset_ids=['fixture'],
        schema_id=SCHEMA_ID,label_policy=LABEL_POLICY,train_range=['start','end'],validation_ranges=[],test_ranges=[],
        hyperparameters=POLICY,seed=314159,metrics={},status=status,execution_eligible=False)


def test_cutoff_excludes_late_resolution_and_allows_equality():
    rows=[sample(i) for i in range(100)]
    baseline=folds(rows,T,T+timedelta(hours=100))
    cutoff=stamp(baseline[0]['cutoff']); exact=sample(1); crossing=sample(2)
    exact['resolved_at']=cutoff.isoformat(); crossing['resolved_at']=(cutoff+timedelta(seconds=1)).isoformat()
    result=folds([exact,crossing],T,T+timedelta(hours=100))[0]
    assert [r['id'] for r in result['train']]==['1']
    assert result['crossing_excluded']==1


def test_folds_disjoint_test_and_expanding_training():
    rows=[sample(i) for i in range(1000)]
    result=folds(rows,T,T+timedelta(hours=1000))
    sets=[{r['id'] for r in f['test']} for f in result]
    assert all(not a&b for i,a in enumerate(sets) for b in sets[i+1:])
    assert all({r['id'] for r in a['train']}<={r['id'] for r in b['train']} for a,b in zip(result,result[1:]))
    assert result==folds(rows,T,T+timedelta(hours=1000))
    for f in result:
        assert all(stamp(r['resolved_at'])<=stamp(f['cutoff']) for r in f['train'])


@pytest.mark.parametrize('key',['outcome','exit_price','r_multiple','held_bars','p7_rank','label','resolution_timestamp'])
def test_feature_whitelist_blocks_outcomes(key):
    f=sample(1)['features']; f[key]=1
    with pytest.raises(ValueError,match='schema'): validate_features(f)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf')])
def test_nonfinite_features_reject(value):
    f=sample(1)['features']; f['atr_fraction']=value
    with pytest.raises(ValueError,match='Non-finite'): validate_features(f)


def test_features_ignore_future_execution_values():
    s=signal(); initial=features(s,bar()); s.update(exit_price=1e10,entry=1e9,outcome='LOSS',r_multiple=-10)
    assert features(s,bar())==initial
    assert initial['signal_reward_r']==pytest.approx(2)


@pytest.mark.parametrize('field,value',[('direction','CLOSE'),('direction','UNKNOWN'),('stop_loss','101.1'),
                                       ('take_profit','99'),('stop_loss','NaN')])
def test_feature_source_rejects_invalid_direction_geometry(field,value):
    s=signal(); s[field]=value
    with pytest.raises(ValueError): features(s,bar())


@pytest.mark.parametrize('value',[True,'123',{}])
def test_feature_numeric_type_contract(value):
    f=sample(1)['features']; f['rsi2']=value
    with pytest.raises(ValueError): validate_features(f)


@pytest.mark.parametrize('field',['signal_timestamp','context_closed_at'])
def test_future_closed_context_reject(field):
    s=signal(); s[field]=(bar().closed+timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError): features(s,bar())


def test_naive_timestamp_reject():
    with pytest.raises(ValueError): stamp('2025-09-02T00:00:00')


@pytest.mark.parametrize('outcome',['UNKNOWN','AMBIGUOUS','CANCELLED','TIMEOUT','BREAKEVEN'])
def test_invalid_label_never_trains(outcome):
    r=sample(1); r['outcome']=outcome
    with pytest.raises(ValueError,match='Label policy'): evaluate([r],T,T+timedelta(hours=100))


@pytest.mark.parametrize('bad',['feature_available_at','resolved_at'])
def test_evaluation_temporal_violation(bad):
    r=sample(1); r[bad]=(T+timedelta(hours=3 if bad=='feature_available_at' else 0)).isoformat()
    with pytest.raises(ValueError,match='Temporal'): evaluate([r],T,T+timedelta(hours=100))


@pytest.mark.parametrize('kind',['prior','logistic','shallow_tree'])
@pytest.mark.parametrize('identity',[True,False])
def test_models_exactly_reproduce_and_json_replay(kind,identity):
    rows=[sample(i) for i in range(200)]; rows[2]['features']['rsi2']=None
    p,a=train(rows[:150],rows[150:],kind,strategy_id=identity)
    q,b=train(rows[:150],rows[150:],kind,strategy_id=identity)
    assert p==q and a==b
    portable=json.loads(encode(a))
    assert np.allclose(p,predict_artifact(portable,rows[150:]),atol=1e-12,rtol=0)
    if kind!='prior': assert ('strategy_id' in a['preprocessing']['categories'])==identity


def test_transform_fitted_only_on_training():
    rows=[sample(i) for i in range(200)]
    p,a=train(rows[:150],rows[150:],'logistic',strategy_id=False)
    for r in rows[150:]:
        r['features']['atr_fraction']=1e8
        r['features']['instrument']='UNSEEN_FIXTURE_CATEGORY'
    q,b=train(rows[:150],rows[150:],'logistic',strategy_id=False)
    assert a==b and p!=q
    assert b['preprocessing']['fit_on_train_only'] is True


def test_realized_r_not_a_predictor():
    rows=[sample(i) for i in range(200)]
    p,a=train(rows[:150],rows[150:],'logistic')
    for r in rows: r['r_multiple']=-1e9
    q,b=train(rows[:150],rows[150:],'logistic')
    assert (p,a)==(q,b)


@pytest.mark.parametrize('label',[0,1])
def test_one_class_metrics_are_explicit(label):
    m=metrics([label]*10,[.25]*10)
    assert m['roc_auc'] is None and m['pr_auc'] is None and m['balanced_accuracy'] is None
    assert m['status'].startswith('ONE_CLASS') and len(m['confusion_matrix'])==2


@pytest.mark.parametrize('p',[[float('nan')],[1.1],[-.1],[float('inf')]])
def test_invalid_probability_reject(p):
    with pytest.raises(ValueError): metrics([1],p)


def test_no_sample_no_false_quality():
    result,artifacts,p=evaluate([sample(i) for i in range(30)],T,T+timedelta(hours=30))
    assert result['filter_status']=='INSUFFICIENT_DATA' and not artifacts and not p


def test_filter_denominator_and_threshold_equality():
    rows=[sample(i) for i in range(10)]
    result=filter_stats(rows,[.5]*10,.5)
    assert result['coverage']==1 and result['before']==result['after']
    empty=filter_stats(rows,[.4]*10,.5)
    assert empty['after']['count']==0 and empty['after']['expectancy'] is None
    assert trade_stats(rows)['drawdown_basis'].endswith('NOT account equity')


def test_registry_restart_idempotency(tmp_path):
    root=tmp_path/'p8'; r=Registry(root,fixture=True); e=entry(); a={'prior':.3}
    identity=r.register(e,a); assert identity==r.register(e,a)
    recovered,artifact=Registry(root,fixture=True).read(identity)
    assert artifact==a and recovered['execution_eligible'] is False
    with r.connect() as c: assert c.execute('SELECT count(*) FROM models').fetchone()[0]==1


def test_registry_atomic_rollback_retry(tmp_path):
    r=Registry(tmp_path/'p8',fixture=True)
    def crash(): raise RuntimeError('fixture crash')
    with pytest.raises(RuntimeError): r.register(entry(),{'prior':.3},checkpoint=crash)
    with r.connect() as c: assert c.execute('SELECT count(*) FROM models').fetchone()[0]==0
    identity=r.register(entry(),{'prior':.3})
    assert r.read(identity)[1]=={'prior':.3}


def test_registry_concurrent_replay(tmp_path):
    r=Registry(tmp_path/'p8',fixture=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids=list(pool.map(lambda _:r.register(entry(),{'prior':.3}),range(12)))
    assert len(set(ids))==1
    with r.connect() as c: assert c.execute('SELECT count(*) FROM models').fetchone()[0]==1


@pytest.mark.parametrize('mutation',['UPDATE models SET created_at=created_at','DELETE FROM models'])
def test_registry_append_only(tmp_path,mutation):
    r=Registry(tmp_path/'p8',fixture=True); r.register(entry(),{'prior':.3})
    with pytest.raises(sqlite3.IntegrityError):
        with r.connect() as c: c.execute(mutation)


def test_artifact_tamper_detected(tmp_path):
    r=Registry(tmp_path/'p8',fixture=True); identity=r.register(entry(),{'prior':.3})
    value,a=r.read(identity); (r.root/value['artifact_path']).write_text('{}')
    with pytest.raises(ValueError,match='hash'): r.read(identity)


@pytest.mark.parametrize('key,value',[('status','LIVE'),('execution_eligible',True)])
def test_registry_never_execution_capable(tmp_path,key,value):
    r=Registry(tmp_path/'p8',fixture=True); e=entry(); e[key]=value
    with pytest.raises(ValueError): r.register(e,{})


@pytest.mark.parametrize('name',['private','data','.env','.p3-verification'])
def test_registry_storage_isolation(tmp_path,name):
    with pytest.raises(ValueError): Registry(tmp_path/name/'p8',fixture=True)


def test_human_positive_only_shape_audit():
    text='[02/09/2025, 10:00:00 AM] Person: EUR USD\nBUY on current rate\nStoploss: 1.15840\nTake profit: 1.16000\n'
    text+='[02/09/2025, 11:00:00 AM] Person: EURUSD\nSELL at 1.16\nSL 1.161\nTP 1.158\n'
    result=audit_archive(archive(text))
    assert result['raw_messages']==2 and result['usable_signal_shapes']==2
    assert result['negatives']==0 and result['no_signal_classifier'] is False
    assert result['utc_qualified_signals']==0 and result['verified_outcomes']==0
    assert result['status']=='INSUFFICIENT_DATA'
    assert 'Person' not in encode(result) and '1.15840' not in encode(result)


def test_human_duplicates_not_new_signals():
    text='[02/09/2025, 10:00:00 AM] P: EURUSD BUY at 1.16 SL 1.15 TP 1.18\n'
    result=audit_archive(archive(text+text))
    assert result['duplicate_messages']==1 and result['usable_signal_shapes']==1


def test_human_ambiguous_and_updates_not_training():
    text='[02/09/2025, 10:00 AM] P: EURUSD BUY SELL at 1.16 SL 1.15 TP 1.18\n'
    text+='[02/09/2025, 11:00 AM] P: move SL for EURUSD BUY to 1.16\n'
    result=audit_archive(archive(text))
    assert result['ambiguous_signals']==1 and result['usable_signal_shapes']==0 and result['excluded_updates']==1


def test_human_does_not_fix_malformed_prices():
    text='[02/09/2025, 10:00 AM] P: GOLD BUY current rate SL 44250 TP 4436\n'
    result=audit_archive(archive(text))
    assert result['usable_signal_shapes']==0


def test_transcript_requires_recognized_records():
    with pytest.raises(ValueError): records('not a transcript')


def test_kronos_context_lineage_and_asof():
    view=dict(dataset_id='pinned',qualification_id='qualified',candles=[bar(i).payload() for i in range(3)])
    result=context_view(view,as_of=bar(2).closed.isoformat())
    assert result['dataset_id']=='pinned' and result['execution_eligible'] is False
    assert result['rows'][0]['volume'] is None
    assert result['context_id']==context_view(view,as_of=bar(2).closed.isoformat())['context_id']
    with pytest.raises(ValueError): context_view(view,as_of=bar(1).closed.isoformat())


@pytest.mark.parametrize('horizon',[0,-1,25,True,1.5])
def test_kronos_invalid_horizon(horizon):
    with pytest.raises(ValueError): context_view(dict(candles=[]),as_of=T.isoformat(),horizon=horizon)


def test_kronos_runtime_blocker_not_fake_inference(monkeypatch):
    monkeypatch.setattr('core.rebuild.p8_kronos.importlib.util.find_spec',lambda _:None)
    monkeypatch.setattr('core.rebuild.p8_kronos.probe_torch',lambda:'ModuleNotFoundError')
    r=audit_runtime(network=False)
    assert r['runtime']=='BLOCKED' and r['evaluation']=='NOT_RUN' and not r['checkpoint_loaded']
    assert not r['execution_eligible'] and r['torch_import']=='ModuleNotFoundError'


def test_projection_is_hash_validated_read_only(tmp_path):
    p=tmp_path/'result.json'
    assert projection(p)['status']=='NOT_AVAILABLE'
    value=dict(version='p8-research-v1',status='EVALUATED_RESEARCH_ONLY',scope='RESEARCH_ONLY',
        feature_schema_id=SCHEMA_ID,track_a=dict(filter_status='PASS_THROUGH',policy_hash='p8',result='INSUFFICIENT_DATA'),
        track_b=dict(status='INSUFFICIENT_DATA',result='HUMAN_IMITATION_PARTIAL'),
        kronos=dict(runtime='BLOCKED',added_value='BLOCKED'),registry=[],execution_eligible=False)
    value['result_id']=digest(value); p.write_text(encode(value))
    before=p.read_bytes(); report=projection(p)
    assert report['ml_filter']=='PASS_THROUGH' and p.read_bytes()==before
    value['execution_eligible']=True; value['result_id']=digest({k:v for k,v in value.items() if k!='result_id'})
    p.write_text(encode(value)); assert projection(p)['status']=='INVALID_EVIDENCE'
    p.write_text('{}'); assert projection(p)['status']=='INVALID_EVIDENCE'


def test_evidence_hash_rejects_corruption():
    value=dict(a=1); value['id']=digest(value); assert verify(value,'id')==value
    value['a']=2
    with pytest.raises(ValueError): verify(value,'id')


def test_process_death_after_artifact_before_registry_commit(tmp_path):
    root=tmp_path/'p8'; registry=Registry(root,fixture=True)
    script='''import os,sys,json
sys.path.insert(0,sys.argv[1])
from core.rebuild.p8_registry import Registry
r=Registry(sys.argv[2],fixture=True)
r.register(json.loads(sys.argv[3]),{'prior':.3},checkpoint=lambda:os._exit(17))
'''
    result=subprocess.run([sys.executable,'-B','-c',script,str(Path(__file__).resolve().parents[1]),
                           str(root),encode(entry())],capture_output=True,timeout=30)
    assert result.returncode==17,result.stderr.decode()
    with registry.connect() as c: assert c.execute('SELECT count(*) FROM models').fetchone()[0]==0
    identity=Registry(root,fixture=True).register(entry(),{'prior':.3})
    assert registry.read(identity)[1]=={'prior':.3}


def test_pinned_reader_uses_readonly_fixture_store(tmp_path,monkeypatch):
    from core.rebuild import p8_evidence as mod
    from core.rebuild.research_strategies import Features
    from core.rebuild.export_research import VERSION as QVERSION
    from core.rebuild.evtl_provider import VERSION as NORMALIZER
    from core.rebuild.market_data import VALIDATOR
    root=tmp_path/'repo'; market=root/'research/p5-market-data'; market.mkdir(parents=True)
    notes=root/'knowledge/Audits'; notes.mkdir(parents=True)
    bars=[bar(i) for i in range(3)]; payloads=[b.payload() for b in bars]
    from core.rebuild.evtl_provider import ORIGIN
    manifest=dict(provider='EV_TRADING_LABS',normalization=NORMALIZER,validation=VALIDATOR,
                  price_basis='BID_WITH_SEPARATE_ASK_OHLC',real_data=True,timeframe='1H',mapping={'provider_symbol':'XAUUSD'})
    did=digest(manifest); start=T.isoformat(); end=bars[-1].closed.isoformat()
    q=dict(version=QVERSION,dataset_id=did,state='QUALIFIED_WITH_KNOWN_LIMITATIONS',segments=[dict(start=start,end=end)])
    qid=digest(q); receipt=dict(raw_id='fixture-source',ingested_at=T.isoformat(),provenance=encode(
        {'fixture':False,'responses':[dict(fixture=False,provider='EV_TRADING_LABS',adapter=NORMALIZER,
            price_side='BID_WITH_SEPARATE_ASK_OHLC',url=ORIGIN+'/api/simulator/data/XAUUSD/H1/fixture',sha256='f'*64)]}))
    data=dict(dataset_id=did,qualification_id=qid,fixture=False,start=start,end=end,
        rows_hash=digest(payloads),provenance_hash=digest(dict(manifest=manifest,qualification=q,receipts=[receipt])))
    config=dict(data=data); run_id=digest(config)
    s=signal(); s.update(features={k:str(v) for k,v in Features().push(bars[0]).features.items()},
        dataset_id=did,qualification_id=qid,provider='EV_TRADING_LABS',execution_eligible=False,strategy_version='fixture-v1')
    s['signal_id']=digest(s); s['disposition']='RESEARCH_TRADE'
    t=dict(research_trade_id=digest(dict(run_id=run_id,signal_id=s['signal_id'])),signal=s,
        outcome='WIN',exit_timestamp=bars[1].closed.isoformat(),evidence_hash=digest(payloads[1]),r_multiple='1.7')
    run=dict(run_id=run_id,configuration=config,trades=[t]); run['artifact_id']=digest(run)
    index=dict(configuration=dict(split={}),cells=[dict(replays={'development':dict(run_id=run_id,artifact_id=run['artifact_id'])})])
    index['run_id']=digest(index['configuration']); index['result_id']=digest(index)
    (notes/'P7-TOURNAMENT-RESULTS.json').write_text(encode(index))
    p5=dict(common_qualified_start=start,common_qualified_end_exclusive=end); p5['evidence_id']=digest(p5)
    (notes/'P5-ALTERNATIVE-DATA-EVIDENCE.json').write_text(encode(p5))
    path=market/'market-data.sqlite3'
    with sqlite3.connect(path) as c:
        c.executescript('''CREATE TABLE p6_runs(id TEXT,payload TEXT);CREATE TABLE datasets(id TEXT,manifest TEXT);
            CREATE TABLE p5_export_qualification(id TEXT,payload TEXT);CREATE TABLE bars(dataset TEXT,opened TEXT,payload TEXT);
            CREATE TABLE receipts(id INTEGER,dataset TEXT,raw_id TEXT,ingested_at TEXT,provenance TEXT);''')
        c.execute('INSERT INTO p6_runs VALUES(?,?)',(run_id,encode(run)))
        c.execute('INSERT INTO datasets VALUES(?,?)',(did,encode(manifest)))
        c.execute('INSERT INTO p5_export_qualification VALUES(?,?)',(qid,encode(q)))
        c.execute('INSERT INTO receipts VALUES(?,?,?,?,?)',(1,did,*receipt.values()))
        c.executemany('INSERT INTO bars VALUES(?,?,?)',[(did,b.opened.isoformat(),encode(b.payload())) for b in bars])
    before=path.read_bytes(); calls=[]; native=sqlite3.connect
    def connect(database,**kwargs):
        calls.append(database); assert database.endswith('?mode=ro') and kwargs['uri'] is True
        return native(database,**kwargs)
    monkeypatch.setattr(mod,'ROOT',root); monkeypatch.setattr(mod.sqlite3,'connect',connect)
    rows,audit,a,b=mod.read_inputs()
    assert len(rows)==audit['labels']==1 and calls and path.read_bytes()==before
    bad=deepcopy(index); bad['cells'][0]['replays']['development']['artifact_id']='wrong'
    bad['result_id']=digest({k:v for k,v in bad.items() if k!='result_id'})
    (notes/'P7-TOURNAMENT-RESULTS.json').write_text(encode(bad))
    with pytest.raises(ValueError,match='Pinned'): mod.read_inputs()
