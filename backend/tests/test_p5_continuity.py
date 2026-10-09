"""Synthetic coverage/provenance contracts only; no live provider or market qualification."""
from copy import deepcopy
from datetime import timedelta
import sqlite3

import pytest

from core.rebuild.continuity import ClosureEvidence, CoverageStore, measure
from core.rebuild.market_data import Candle, MarketStore, MAPPINGS, digest
from core.rebuild.research_data import ResearchData
from test_p5_market_data import START, bar, store


def snapshot(store,missing=()):
    bars=[bar(i) for i in range(120) if i not in missing]
    identity=store.save('XAUUSD','1M',START,START+timedelta(minutes=120),bars,
                        raw=b'synthetic coverage fixture',provenance={'fixture':True})
    return store.query(identity,research=False)


def closure(a=60,b=61,**changes):
    return dict(provider='HISTDATA',instrument='XAUUSD',start=START+timedelta(minutes=a),
                end=START+timedelta(minutes=b),valid_from=START,valid_until=START+timedelta(days=90),
                evidence_ref='fixture calendar; not real session proof',evidence_sha256='a'*64,**changes)


def test_metrics_unexplained_gaps_and_no_repair(store):
    data=snapshot(store,missing={3,4,5,10})
    before=deepcopy(data); result=measure(data)
    assert result['total_grid_bars']==result['total_expected_bars']==120
    assert result['actual_bars']==116 and result['unexplained_missing_bars']==4
    assert result['unexplained_gap_percentage']=='3.333333'
    assert result['longest_unexplained_gap_bars']==3
    assert result['longest_unexplained_gap_seconds']==180
    assert result['expected_closure_bars']==0 and not result['continuity_proven']
    assert result['first_timestamp']==data['candles'][0]['opened']
    assert result['last_timestamp']==data['candles'][-1]['opened']
    assert data==before and not result['qualification_changed']


def test_evidenced_closure_is_not_unexplained_gap(store):
    data=snapshot(store,missing={60})
    result=measure(data,closures=[closure()])
    assert result['expected_closure_bars']==1 and result['total_expected_bars']==119
    assert result['unexplained_missing_bars']==0 and result['continuity_proven']
    # Diagnostic continuity never promotes the synthetic fixture.
    assert ResearchData(store).qualify(data['dataset_id'])['state']=='REJECTED'


@pytest.mark.parametrize('field,value',[
    ('provider','DUKASCOPY'),('instrument','USOIL'),('evidence_sha256','bad'),
    ('evidence_ref',''),('valid_from',START+timedelta(days=1)),
    ('valid_until',START),('start',START.replace(tzinfo=None)),('end',START)])
def test_bad_or_wrong_provider_closure_cannot_excuse_gap(store,field,value):
    evidence=closure(); evidence[field]=value
    with pytest.raises(ValueError): measure(snapshot(store,missing={60}),closures=[evidence])


def test_partial_overlap_and_contradictory_closure(store):
    data=snapshot(store,missing={60})
    c=closure(); c['start']+=timedelta(seconds=30)
    result=measure(data,closures=[c])
    assert result['partial_closure_bars']==1 and result['expected_closure_bars']==0
    assert result['unexplained_missing_bars']==1
    observed=measure(data,closures=[closure(10,11)])
    assert observed['closure_conflicting_observation_bars']==1 and not observed['continuity_proven']


def test_closure_union_order_and_identity(store):
    data=snapshot(store,missing={60,61,62})
    c1,c2=closure(60,62),closure(61,63)
    a=measure(data,closures=[c1,c2,c1]); b=measure(data,closures=[c2,c1])
    assert a==b and a['expected_closure_bars']==3 and a['unexplained_missing_bars']==0
    assert digest(a)!=digest(measure(data))


def test_persisted_coverage_is_immutable_restart_and_pinned(store):
    data=snapshot(store,missing={60}); service=CoverageStore(store)
    result=service.assess(data['dataset_id'])
    assert service.assess(data['dataset_id'])==result
    assert CoverageStore(MarketStore(store.root,fixture=True)).assess(data['dataset_id'])==result
    revised=service.assess(data['dataset_id'],closures=[closure()])
    assert revised['coverage_id']!=result['coverage_id']
    assert store.query(data['dataset_id'],research=False)==data
    with store.connect() as c:
        assert c.execute('SELECT count(*) FROM p5_coverage').fetchone()[0]==2
        with pytest.raises(sqlite3.IntegrityError): c.execute('UPDATE p5_coverage SET payload=?',('{}',))
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM p5_coverage')


def test_provider_comparison_inputs_cannot_merge_or_relabel(store):
    first=snapshot(store); second=deepcopy(first)
    second['manifest']['provider']='DUKASCOPY'; second['dataset_id']='independent-fixture'
    for c in second['candles']: c['provider']='DUKASCOPY'
    assert measure(first)['provider']=='HISTDATA' and measure(second)['provider']=='DUKASCOPY'
    assert digest(measure(first))!=digest(measure(second))
    second['candles'][0]['provider']='HISTDATA'
    with pytest.raises(ValueError): measure(second)
    with pytest.raises(ValueError): Candle.model_validate(dict(first['candles'][0],provider='DUKASCOPY'))
    # A foreign receipt cannot turn HistData candles into a qualified second provider.
    identity=store.save('XAUUSD','1M',START,START+timedelta(minutes=1),[bar()],raw=b'fixture',
                        provenance={'fixture':False,'responses':[{'provider':'DUKASCOPY','fixture':False}]})
    assert ResearchData(store).qualify(identity)['state']=='REJECTED'


@pytest.mark.parametrize('frame,hours',[('1H',1),('4H',4)])
@pytest.mark.parametrize('instrument',['XAUUSD','XAGUSD','USOIL'])
def test_multimonth_independent_instrument_coverage(store,frame,hours,instrument):
    step=timedelta(hours=hours); count=90*24//hours
    bars=[bar(instrument=instrument,provider_symbol=MAPPINGS[instrument]['provider_symbol'],
              timeframe=frame,opened=START+i*step,closed=START+(i+1)*step) for i in range(count)]
    identity=store.save(instrument,frame,START,START+count*step,bars,raw=b'synthetic only',provenance={'fixture':True})
    service=CoverageStore(store); end=START+timedelta(days=60)
    result=service.assess(identity,start=START,end=end)
    assert result==service.assess(identity,start=START,end=end)
    assert result['actual_bars']==result['total_expected_bars']==60*24//hours
    assert result['continuity_proven'] and result['unexplained_gap_percentage']=='0.000000'
    if instrument=='USOIL':
        assert result['mapping']['provider_symbol']=='WTIUSD'
        assert 'unverified' in result['mapping']['basis']
    with pytest.raises(ValueError): service.assess(identity,end=end+timedelta(seconds=1))


def test_quality_discontinuity_not_hidden_by_zero_missing_count(store):
    bars=[bar(),bar(1,open='1000',high='1002',low='999',close='1001')]
    identity=store.save('XAUUSD','1M',START,START+timedelta(minutes=2),bars,
                        raw=b'synthetic',provenance={'fixture':True})
    result=CoverageStore(store).assess(identity)
    assert result['unexplained_missing_bars']==0 and result['quality_withheld_bars']==0
    assert result['classification_counts']['PRICE_GAP_OBSERVATION']==1
    assert result['continuity_proven']  # Timestamp continuity, not price-quality certification.
