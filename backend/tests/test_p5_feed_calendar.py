"""Synthetic availability evidence tests; never authoritative price qualification."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import sqlite3

import pytest

from core.rebuild.market_data import UTC, MAPPINGS, digest
from core.rebuild.feed_calendar import derive, exceptions, aggregate, FeedResearch, minute, closed_minutes
from test_p5_market_data import bar, store
from test_p5_qualification import source

A=datetime(2021,1,1,tzinfo=UTC); B=datetime(2022,1,1,tzinfo=UTC)


def snapshot(instrument='XAUUSD',skip=None,extra=False):
    candles=[]; t=datetime(2021,1,4,tzinfo=UTC)
    for week in range(52):
        for offset in (0,1):
            if (week,offset)==skip: continue
            opened=t+timedelta(weeks=week,minutes=offset)
            candles.append(bar(instrument=instrument,provider_symbol=MAPPINGS[instrument]['provider_symbol'],
                               opened=opened,closed=opened+timedelta(minutes=1)).payload())
    if extra:
        opened=t+timedelta(minutes=2)
        candles.append(bar(instrument=instrument,provider_symbol=MAPPINGS[instrument]['provider_symbol'],opened=opened,closed=opened+timedelta(minutes=1)).payload())
        candles.sort(key=lambda c:c['opened'])
    m=dict(provider='HISTDATA',instrument=instrument,timeframe='1M',start=A.isoformat(),end=B.isoformat(),content_hash=digest(candles))
    return dict(dataset_id=digest(m),manifest=m,candles=candles)


def test_recurrence_confidence_and_isolated_gap():
    data=snapshot(skip=(5,0)); model=derive(data)
    assert len(model['comparable_weeks'])==51
    assert model['weeks_per_quarter']=={'1':13,'2':13,'3':13,'4':12}
    assert 0 not in model['recurring_closed_slots']
    assert model['slot_observed_counts'][0]==51
    assert 2 in model['recurring_closed_slots']
    assert 2 not in derive(snapshot(extra=True))['recurring_closed_slots']
    assert derive(data)==json.loads(json.dumps(model))


def test_insufficient_and_mixed_evidence_rejects():
    data=snapshot(); data['candles']=data['candles'][:-8]
    with pytest.raises(ValueError): derive(data)
    with pytest.raises(ValueError): minute('2021-01-01T00:00:00')
    with pytest.raises(ValueError): minute('2021-01-01T00:00:01+00:00')
    data=snapshot(); data['candles'][0]['instrument']='USOIL'
    with pytest.raises(ValueError): derive(data)


@pytest.mark.parametrize('frame',['1H','4H'])
def test_aggregation_requires_all_expected_minutes(frame):
    data=snapshot(skip=(5,0)); model=derive(data)
    bars,audit=aggregate(data,model,frame)
    assert len(bars)==51
    assert sum(r['classification']=='UNKNOWN_GAP' for r in audit)==1
    assert all(b.open==100 and b.close==101 and b.volume is None for b in bars)
    assert all(r['expected_minutes']==2 for r in audit if r['classification']=='COMPLETE')
    wrong=deepcopy(model); wrong['source_dataset_id']='wrong'
    with pytest.raises(ValueError): aggregate(data,wrong,frame)


def test_instrument_calendars_are_independent():
    first=derive(snapshot()); second=derive(snapshot('USOIL',extra=True))
    assert digest(first)!=digest(second)
    assert 2 in first['recurring_closed_slots'] and 2 not in second['recurring_closed_slots']
    assert 2 not in second['quarterly_closed_slots']['1']
    assert all(2 in second['quarterly_closed_slots'][q] for q in ('2','3','4'))


def test_shared_full_day_exception_not_single_feed_absence():
    data={i:snapshot(i,skip=(5,0)) for i in MAPPINGS}
    models={i:derive(d) for i,d in data.items()}
    days={i:{minute(c['opened'])//1440 for c in d['candles']} for i,d in data.items()}
    assert all(not m['exceptions'] for m in exceptions(models,days).values())
    day=minute('2021-02-08T00:00:00+00:00')//1440
    for s in days.values(): s.discard(day)
    result=exceptions(models,days)
    assert all(len(m['exceptions'])==1 for m in result.values())
    assert all(day*1440 in closed_minutes(m) for m in result.values())


def test_source_calendar_binding_and_restart(store):
    data=snapshot(); from core.rebuild.market_data import Candle, MarketStore
    identity=store.save('XAUUSD','1M',A,B,[Candle(**c) for c in data['candles']],raw=b'fixture',provenance=source())
    data=store.query(identity,research=False); model=derive(data); service=FeedResearch(store)
    q=service.rebuild(data,model,'1H',b'fixture',source())
    assert q==service.rebuild(data,json.loads(json.dumps(model)),'1H',b'fixture',source())
    r=q['longest_range']; start=datetime.fromisoformat(r['start']); end=datetime.fromisoformat(r['end'])
    assert (end-start).days>300
    result=service.query(q['qualification_id'],start,end)
    assert result==FeedResearch(MarketStore(store.root,fixture=True)).query(q['qualification_id'],start,end)
    assert result['manifest']['derivation']['calendar_id']==digest(model)
    changed=deepcopy(model); changed['threshold']['absence_fraction']='0.99'
    with pytest.raises(ValueError): service.rebuild(data,changed,'1H',b'fixture',source())
    changed_data=deepcopy(data); changed_data['candles'][0]['open']='101'
    with pytest.raises(ValueError): service.rebuild(changed_data,model,'1H',b'fixture',source())
    with store.connect() as c:
        for table in ('p5_feed_calendars','p5_feed_qualification'):
            with pytest.raises(sqlite3.IntegrityError): c.execute(f'DELETE FROM {table}')
