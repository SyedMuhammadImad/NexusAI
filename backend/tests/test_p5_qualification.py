"""Synthetic contract tests only, never real-market qualification evidence."""
from datetime import datetime, timedelta
import json
import sqlite3
import pytest
from test_p5_market_data import START, bar, store
from core.rebuild.market_data import MarketStore, MAPPINGS
from core.rebuild.research_data import ResearchData, classify


def source(fixture=False):
    return dict(fixture=fixture,responses=[dict(provider='HISTDATA',adapter='fixture-contract',price_side='BID',
                                             url='https://www.histdata.com/fixture',fixture=fixture)])


def dataset(store,kind='clean'):
    data=[bar(i) for i in range(120)]
    if kind=='gap': data.pop(60)
    if kind=='jump': data[60]=bar(60,open='1000',high='1002',low='999',close='1001')
    return store.save('XAUUSD','1M',START,START+timedelta(minutes=120),data,raw=b'synthetic test only',provenance=source(kind=='fixture'),
                      issues=[dict(kind='MALFORMED_NATIVE_ROW',row=5)] if kind=='corrupt' else [])


def test_qualified_acceptance_pinning_and_replay(store):
    service=ResearchData(store); identity=dataset(store)
    q=service.qualify(identity)
    assert q['state']=='QUALIFIED_WITH_KNOWN_LIMITATIONS'
    assert service.qualify(identity)==q
    data=service.query(q['qualification_id'])
    assert len(data['candles'])==120 and data['dataset_id']==identity
    assert data['manifest']['mapping']['broker_symbol']=='XAUUSDm'
    assert data['qualification']['limitations']
    assert ResearchData(MarketStore(store.root,fixture=True)).query(q['qualification_id'])==data
    with store.connect() as c:
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM p5_qualification')


@pytest.mark.parametrize('kind,state',[('gap','QUALIFIED_WITH_KNOWN_LIMITATIONS'),('jump','QUALIFIED_WITH_KNOWN_LIMITATIONS'),('fixture','REJECTED'),('corrupt','REVIEW_REQUIRED')])
def test_qualification_states_and_no_clearing(store,kind,state):
    view=ResearchData(store); identity=dataset(store,kind); before=store.query(identity,research=False)
    q=view.qualify(identity); assert q['state']==state
    if kind=='jump':
        assert len(view.query(q['qualification_id'])['candles'])==120
        assert q['excluded_count']==0
        assert any(e['classification']=='PRICE_GAP_OBSERVATION' for e in q['events'])
        assert store.query(identity,research=False)==before
        return
    with pytest.raises(ValueError): view.query(q['qualification_id'])
    if state.startswith('QUALIFIED'):
        result=view.query(q['qualification_id'],allow_segments=True)
        assert result['qualification']['events'] and len(result['candles'])<120
        assert len(result['segments'])==2
    else:
        with pytest.raises(ValueError): view.query(q['qualification_id'],allow_segments=True)
    assert store.query(identity,research=False)==before


def test_expected_closure_requires_evidence(store):
    view=ResearchData(store); identity=dataset(store,'gap')
    q=view.qualify(identity)
    assert any(e['classification']=='PROVIDER_GAP' for e in q['events'])
    closure=dict(instrument='XAUUSD',start=START+timedelta(minutes=60),end=START+timedelta(minutes=61),evidence_ref='fixture-provider-calendar')
    revised=view.qualify(identity,closures=[closure])
    assert revised['qualification_id']!=q['qualification_id']
    assert any(e['classification']=='EXPECTED_MARKET_CLOSURE' for e in revised['events'])
    with pytest.raises(ValueError): view.qualify(identity,closures=[dict(closure,evidence_ref='')])
    with pytest.raises(ValueError): view.qualify(identity,closures=[dict(closure,instrument='USOIL')])


def test_exact_clean_subrange_and_bad_boundaries(store):
    view=ResearchData(store); q=view.qualify(dataset(store,'gap'))
    result=view.query(q['qualification_id'],start=START,end=START+timedelta(minutes=60))
    assert len(result['candles'])==60
    with pytest.raises(ValueError): view.query(q['qualification_id'],end=START+timedelta(seconds=30))
    with pytest.raises(ValueError): view.query('unknown')


def test_unproven_provenance_rejects(store):
    identity=store.save('XAUUSD','1M',START,START+timedelta(minutes=1),[bar()],raw=b'fixture',provenance={})
    assert ResearchData(store).qualify(identity)['state']=='REJECTED'


@pytest.mark.parametrize('frame,hours',[('1H',1),('4H',4)])
@pytest.mark.parametrize('instrument',['XAUUSD','XAGUSD','USOIL'])
def test_multimonth_and_multiday_range_contract(store,frame,hours,instrument):
    step=timedelta(hours=hours); count=24*90//hours
    bars=[bar(instrument=instrument,provider_symbol=MAPPINGS[instrument]['provider_symbol'],
              timeframe=frame,opened=START+i*step,closed=START+(i+1)*step) for i in range(count)]
    identity=store.save(instrument,frame,START,START+count*step,bars,raw=b'synthetic contract only',provenance=source())
    view=ResearchData(store); q=view.qualify(identity)
    for days in (3,60):
        end=START+timedelta(days=days)
        result=view.query(q['qualification_id'],start=START,end=end)
        assert result==view.query(q['qualification_id'],start=START,end=end)
        assert result['dataset_id']==identity
        assert len(result['candles'])==24*days//hours
        assert result['manifest']['instrument']==instrument and result['manifest']['timeframe']==frame
        assert datetime.fromisoformat(result['candles'][0]['opened'])==START
        assert datetime.fromisoformat(result['candles'][-1]['closed'])==end
