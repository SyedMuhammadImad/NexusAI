"""Synthetic calendar contracts; not authoritative real-market evidence."""
from datetime import datetime, timedelta
import sqlite3

import pytest

from core.rebuild.market_data import UTC, MarketStore, MAPPINGS
from core.rebuild.sessions import Calendar, Window, SessionResearch, assess, histdata_2021
from test_p5_market_data import bar, store
from test_p5_qualification import source


def dt(day,hour=0): return datetime(2021,1,day,hour,tzinfo=UTC)


def window(a,b,kind='EXPECTED_SESSION_CLOSURE',**kw):
    return Window(start=a,end=b,kind=kind,evidence_ref='fixture-evidence',
                  evidence_note='Synthetic contract only',basis=kw.get('basis','PROVIDER_CONFIRMED'))


def test_calendar_normal_weekday_weekend_and_fixed_timezone():
    cal=histdata_2021('XAUUSD')
    assert cal.at('HISTDATA','XAUUSD',dt(1))['expected']
    assert not cal.at('HISTDATA','XAUUSD',dt(2))['expected']
    assert cal.at('HISTDATA','XAUUSD',dt(3))['expected']
    assert cal.identity==histdata_2021('XAUUSD').identity
    assert cal.source_timezone=='EST_FIXED_UTC_MINUS_05_NO_DST'
    for stamp in (datetime(2021,3,14,7,tzinfo=UTC),datetime(2021,11,7,7,tzinfo=UTC)):
        assert cal.at('HISTDATA','XAUUSD',stamp)['expected']
    for provider,instrument,stamp in [('OTHER','XAUUSD',dt(1)),('HISTDATA','USOIL',dt(1)),('HISTDATA','XAUUSD',dt(1).replace(tzinfo=None)),('HISTDATA','XAUUSD',datetime(2022,1,1,tzinfo=UTC))]:
        with pytest.raises(ValueError): cal.at(provider,instrument,stamp)


def test_explicit_holiday_and_maintenance_no_implicit_holidays():
    cal=Calendar(instrument='USOIL',version='fixture-v1',start=dt(1),end=dt(5),windows=(
        window(dt(1),dt(2),'EXPECTED_HOLIDAY_CLOSURE'),
        window(dt(4,22),dt(4,23),'EXPECTED_MAINTENANCE_BREAK')))
    assert cal.at('HISTDATA','USOIL',dt(1,12))['classification']=='EXPECTED_HOLIDAY_CLOSURE'
    assert not cal.at('HISTDATA','USOIL',dt(4,22))['expected']
    assert cal.at('HISTDATA','USOIL',dt(4,23))['expected']
    assert histdata_2021('USOIL').at('HISTDATA','USOIL',dt(1))['classification']=='UNKNOWN_GAP'


def test_calendar_order_identity_overlap_and_range():
    a=window(dt(1),dt(2)); b=window(dt(3),dt(4))
    values=dict(instrument='XAUUSD',version='fixture',start=dt(1),end=dt(5))
    assert Calendar(**values,windows=(a,b)).identity==Calendar(**values,windows=(b,a,a)).identity
    with pytest.raises(ValueError): Calendar(**values,windows=(a,window(dt(1,12),dt(2,12))))
    with pytest.raises(ValueError): Calendar(**values,windows=(window(dt(4),dt(6)),))
    with pytest.raises(ValueError): window(dt(2),dt(1))


def snapshot(store,missing=(24,),fixture=False):
    bars=[bar(timeframe='1H',opened=dt(1)+timedelta(hours=i),closed=dt(1)+timedelta(hours=i+1)) for i in range(72) if i not in missing]
    identity=store.save('XAUUSD','1H',dt(1),dt(4),bars,raw=b'synthetic only',provenance=source(fixture))
    return store.query(identity,research=False)


def test_closures_bridge_but_unknown_does_not(store):
    data=snapshot(store,missing=tuple(range(24,48))+(60,))
    report=assess(data,histdata_2021('XAUUSD'))
    assert report['expected_closures']==24 and report['unexplained_missing_bars']==1
    assert report['longest_range']['start']==dt(1).isoformat()
    assert report['longest_range']['end']==dt(3,12).isoformat()
    assert report['actual_bars']==47
    assert {g['classification'] for g in report['gaps']}=={'UNKNOWN_GAP','EXPECTED_SESSION_CLOSURE'}


def test_replay_restart_query_and_no_silent_bridge(store):
    data=snapshot(store,missing=tuple(range(24,48))+(60,))
    service=SessionResearch(store); cal=histdata_2021('XAUUSD')
    q=service.qualify(data['dataset_id'],cal)
    assert service.qualify(data['dataset_id'],cal)==q
    result=service.query(q['qualification_id'],start=dt(1),end=dt(3,12))
    assert len(result['candles'])==36
    assert SessionResearch(MarketStore(store.root,fixture=True)).query(q['qualification_id'],start=dt(1),end=dt(3,12))==result
    with pytest.raises(ValueError): service.query(q['qualification_id'],start=dt(1),end=dt(4))
    with pytest.raises(ValueError): service.query(q['qualification_id'],start=dt(2),end=dt(3))
    with store.connect() as c:
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM p5_session_qualification')


def test_conflicting_observation_and_synthetic_reject(store):
    service=SessionResearch(store)
    for fixture,missing in [(False,()),(True,tuple(range(24,48)))]:
        data=snapshot(store,missing,fixture)
        q=service.qualify(data['dataset_id'],histdata_2021('XAUUSD'))
        assert q['state']=='REJECTED'
        with pytest.raises(ValueError): service.query(q['qualification_id'],start=dt(1),end=dt(2))


def test_partial_aggregate_closure_and_provider_gap(store):
    data=snapshot(store)
    cal=Calendar(instrument='XAUUSD',version='partial',start=dt(1),end=dt(4),windows=(window(dt(2),dt(2)+timedelta(minutes=30)),))
    assert assess(data,cal)['unexplained_missing_bars']==1
    cal=cal.model_copy(update={'windows':(window(dt(2),dt(2,1),'PROVIDER_GAP'),)})
    assert assess(data,cal)['classification_counts']=={'PROVIDER_GAP':1}


def test_year_month_and_policy_identity():
    cal=histdata_2021('XAGUSD')
    assert cal.at('HISTDATA','XAGUSD',datetime(2021,2,1,tzinfo=UTC))['expected']
    assert cal.at('HISTDATA','XAGUSD',datetime(2021,12,31,23,59,tzinfo=UTC))['expected']
    assert cal.identity!=cal.model_copy(update={'version':'changed'}).identity


@pytest.mark.parametrize('instrument',['XAUUSD','XAGUSD','USOIL'])
@pytest.mark.parametrize('frame,hours',[('1H',1),('4H',4)])
def test_multimonth_contract_bridges_only_expected_closures(store,instrument,frame,hours):
    start=dt(1); end=datetime(2021,4,1,tzinfo=UTC)
    step=timedelta(hours=hours); cal=histdata_2021(instrument)
    stamps=[start+i*step for i in range(int((end-start)/step))]
    bars=[bar(instrument=instrument,provider_symbol=MAPPINGS[instrument]['provider_symbol'],
              timeframe=frame,opened=t,closed=t+step) for t in stamps if t.weekday()!=5]
    identity=store.save(instrument,frame,start,end,bars,raw=b'synthetic multi-month contract',provenance=source())
    service=SessionResearch(store); q=service.qualify(identity,cal)
    assert q['unexplained_missing_bars']==0 and q['longest_range']['start']==start.isoformat()
    assert q['longest_range']['end']==end.isoformat()
    assert len(service.query(q['qualification_id'],start=start,end=end)['candles'])==len(bars)
    # Fixture numbers exercise the interface, never real-price qualification.
