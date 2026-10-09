"""Synthetic provider fixtures; these are never real-data qualification evidence."""
from datetime import datetime, timedelta
from decimal import Decimal
import gzip
import json

import httpx
import pytest

from core.rebuild.evtl_provider import EVTLProvider, acquire, CATALOG, ORIGIN
from core.rebuild.market_data import Candle, MarketStore, UTC, series, resample
from core.rebuild.export_research import assess, expected_hour, ExportResearch, kronos_rows
from core.rebuild.research_reader import ResearchDatasetReader
from core.rebuild.provider_comparison import compare

START = datetime(2021, 1, 4, tzinfo=UTC)


def row(index=0, **changes):
    value = dict(ts=int((START+timedelta(hours=index)).timestamp()),
                 o=100, h=103, l=99, c=102, ao=101, ah=104, al=100, ac=103, v=2)
    value.update(changes)
    return value


def packed(rows):
    return gzip.compress(json.dumps(rows).encode(), mtime=0)


def parse(rows):
    return EVTLProvider().normalize(packed(rows), 'XAUUSD', '1H', 2021)


def provider(rows=None, **entry_changes):
    rows = [row(), row(1)] if rows is None else rows
    raw = packed(rows)
    path = '/api/simulator/data/XAUUSD/H1/2021.json.gz'
    entry = dict(key='XAUUSD/H1/2021.json.gz', symbol='XAUUSD', tf='H1', year=2021,
                 url=path, bars=len(rows), first=min(r['ts'] for r in rows),
                 last=max(r['ts'] for r in rows), bytes=len(raw))
    entry.update(entry_changes)
    def handle(request):
        if str(request.url) == CATALOG:
            return httpx.Response(200, json={'files':[entry]})
        assert str(request.url) == ORIGIN+path
        return httpx.Response(200, content=raw)
    return EVTLProvider(httpx.Client(transport=httpx.MockTransport(handle)))


def test_native_sides_timestamp_and_unknown_volume():
    c = parse([row()])[0]
    assert c.opened == START and c.closed == START+timedelta(hours=1)
    assert c.source_time == str(row()['ts'])
    assert c.price_basis == 'BID' and c.open == 100 and c.ask_ohlc['open'] == 101
    assert c.volume_kind == 'UNKNOWN' and c.volume == 2 and c.spread is None
    assert Candle.model_validate(c.payload()).payload() == c.payload()


@pytest.mark.parametrize('change', [
    {'o':float('nan')}, {'ao':float('inf')}, {'v':-1}, {'v':True}, {'o':'100'},
    {'ts':True}, {'ts':row()['ts']+1}, {'ts':1609459199}, {'o':0}, {'l':105},
    {'ah':99}, {'ao':99}, {'ac':None}, {'extra':1}, {'v':None}])
def test_invalid_native_rejected(change):
    with pytest.raises(ValueError): parse([row(**change)])


def test_missing_field_duplicate_json_and_corrupt_gzip_rejected():
    r = row(); del r['ao']
    with pytest.raises(ValueError): parse([r])
    for raw in (b'not gzip', packed([row()])[:-5], gzip.compress(b'[{"ts":1,"ts":2}]')):
        with pytest.raises((ValueError, OSError, EOFError)):
            EVTLProvider().normalize(raw, 'XAUUSD', '1H', 2021)


def test_duplicate_conflict_order_and_no_repair():
    bars = parse([row(3), row(), row(), row(1), row(1,c=101)])
    ordered, issues, gaps = series(bars, START, START+timedelta(hours=4), '1H')
    assert [c.opened for c in ordered] == [START, START+timedelta(hours=3)]
    assert sum(g['missing_count'] for g in gaps) == 2
    assert {i['kind'] for i in issues} >= {'IDENTICAL_DUPLICATE','CONFLICTING_DUPLICATE','OUT_OF_ORDER'}
    with pytest.raises(ValueError): resample(ordered, '4H')


@pytest.mark.parametrize('changes', [{'bars':3}, {'bars':2.0}, {'bytes':0}, {'first':0}, {'symbol':'XAGUSD'},
                                     {'url':'https://untrusted.example/file'}, {'year':2022}])
def test_catalogue_consistency(changes):
    p = provider(**changes)
    _, entries = p.catalogue()
    with pytest.raises(ValueError): p.download('XAUUSD','1H',2021,entries)


def test_origin_redirect_and_missing_export_rejected():
    p = provider()
    with pytest.raises(ValueError): p._get('https://evtradelabs.com.evil/api/data')
    with pytest.raises(ValueError): p.download('USOIL','1H',2021,[])
    with pytest.raises(ValueError): p.download('XAUUSD','1H',2026,[])
    redirect = EVTLProvider(httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={'location':'https://other.example/'}))))
    with pytest.raises((ValueError,httpx.HTTPStatusError)): redirect.catalogue()


def test_replay_restart_incremental_and_provider_isolation(tmp_path):
    store = MarketStore(tmp_path/'research', fixture=True)
    p = provider()
    a = acquire(store,p,'XAUUSD','1H',START,START+timedelta(hours=2))
    assert acquire(store,p,'XAUUSD','1H',START,START+timedelta(hours=2)) == a
    b = acquire(store,provider([row(),row(1),row(2)]),'XAUUSD','1H',
                START,START+timedelta(hours=3),parent=a)
    reopened = MarketStore(store.root,fixture=True)
    assert len(reopened.query(a,research=False)['candles']) == 2
    assert len(reopened.query(b,research=False)['candles']) == 3
    assert reopened.query(a,research=False)['manifest']['provider'] == 'EV_TRADING_LABS'
    with pytest.raises(ValueError): reopened.query(a)  # Fixture root cannot qualify.
    with pytest.raises(ValueError):
        store.save('XAUUSD','1H',START,START+timedelta(hours=2),parse([row()]),
                   raw=b'fixture',provenance={'fixture':True})
    legacy = Candle(instrument='XAUUSD',provider_symbol='XAUUSD',timeframe='1H',
        opened=START,closed=START+timedelta(hours=1),open=100,high=103,low=99,close=102,
        source_time='fixture',timezone_evidence='UTC')
    assert 'ask_ohlc' not in legacy.payload() and 'price_basis' not in legacy.payload()
    with pytest.raises(ValueError):
        store.save('XAUUSD','1H',START,START+timedelta(hours=2),[legacy],
                   raw=b'fixture',provenance={'fixture':True},parent=a)


def test_failed_acquisition_does_not_publish_dataset(tmp_path):
    store = MarketStore(tmp_path/'research', fixture=True)
    with pytest.raises(ValueError):
        acquire(store,provider(bars=3),'XAUUSD','1H',START,START+timedelta(hours=2))
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM datasets').fetchone()[0] == 0


def saved(store, rows, start=START, end=None, frame='1H'):
    bars=EVTLProvider().normalize(packed(rows),'XAUUSD',frame,2021)
    identity=store.save('XAUUSD',frame,start,end or start+timedelta(hours=4),bars,
        raw=packed(rows),provenance={'fixture':True},provider='EV_TRADING_LABS')
    return store.query(identity,research=False)


@pytest.mark.parametrize('stamp,expected', [
    ('2021-01-04T22:00:00+00:00',False),('2021-01-04T23:00:00+00:00',True),
    ('2021-07-05T21:00:00+00:00',False),('2021-07-05T22:00:00+00:00',True),
    ('2021-03-14T21:00:00+00:00',False),('2021-03-14T22:00:00+00:00',True),
    ('2021-11-07T22:00:00+00:00',False),('2021-11-07T23:00:00+00:00',True),
    ('2021-01-09T12:00:00+00:00',False),('2021-01-08T22:00:00+00:00',False)])
def test_regular_session_dst_boundaries(stamp,expected):
    assert expected_hour(datetime.fromisoformat(stamp)) is expected


def test_unknown_hour_withholds_native_h4_and_never_repairs(tmp_path):
    store=MarketStore(tmp_path/'research',fixture=True)
    hourly=saved(store,[row(),row(1),row(3)])
    h4=saved(store,[row()],frame='4H')
    report=assess(h4,hourly)
    assert report['unexplained_bars']==1 and not report['segments']
    assert len(store.query(h4['dataset_id'],research=False)['candles'])==1
    q=ExportResearch(store).qualify(h4['dataset_id'],hourly_dataset=hourly['dataset_id'])
    assert q['state']=='REJECTED'
    with pytest.raises(ValueError): ResearchDatasetReader(store).query(q['qualification_id'],start=START,end=START+timedelta(hours=4))


def test_h4_mismatch_and_calendar_contradiction(tmp_path):
    store=MarketStore(tmp_path/'research',fixture=True)
    hourly=saved(store,[row(i) for i in range(4)])
    h4=saved(store,[row(h=104,ah=105)],frame='4H')
    assert assess(h4,hourly)['unresolved_intervals'][0]['classification']=='PROVIDER_AGGREGATION_CONFLICT'
    bad=saved(store,[row(22)],end=START+timedelta(hours=24))
    assert assess(bad,bad)['conflicts']==[(START+timedelta(hours=22)).isoformat()]


def test_multi_month_calendar_complete_fixture_is_not_real_qualified(tmp_path):
    store=MarketStore(tmp_path/'research',fixture=True)
    end=datetime(2021,4,1,tzinfo=UTC)
    rows=[row(i) for i in range(int((end-START).total_seconds()/3600)) if expected_hour(START+timedelta(hours=i))]
    hourly=saved(store,rows,end=end)
    report=assess(hourly,hourly)
    assert report['unexplained_bars']==0 and not report['conflicts']
    assert report['longest_range']['end']==end.isoformat()
    service=ExportResearch(store)
    q=service.qualify(hourly['dataset_id'],hourly_dataset=hourly['dataset_id'])
    assert q['state']=='REJECTED' and service.qualify(hourly['dataset_id'],hourly_dataset=hourly['dataset_id'])==q


def test_complete_h4_session_bin_only_uses_observed_hours(tmp_path):
    store=MarketStore(tmp_path/'research',fixture=True)
    start=START+timedelta(hours=20); end=start+timedelta(hours=4)
    hourly=saved(store,[row(20),row(21),row(23)],start=start,end=end)
    h4=saved(store,[row(20)],start=start,end=end,frame='4H')
    report=assess(h4,hourly)
    assert report['unexplained_bars']==0 and report['longest_range']['actual_bars']==1


def test_kronos_asof_identity_and_unknown_volume(tmp_path):
    store=MarketStore(tmp_path/'research',fixture=True)
    view=saved(store,[row()]); view['qualification_id']='fixture-not-qualified'
    export=kronos_rows(view,as_of=START+timedelta(hours=1))
    assert export['dataset_id']==view['dataset_id'] and export['volume_kind']=='UNKNOWN'
    assert export['rows'][0]['volume']=='2' and export['price_basis']=='BID'
    with pytest.raises(ValueError): kronos_rows(view,as_of=START)


def test_cross_provider_comparison_keeps_sources_separate(tmp_path):
    store=MarketStore(tmp_path/'research',fixture=True)
    left=saved(store,[row(i,c=100+i,ac=101+i) for i in range(3)])
    right=json.loads(json.dumps(left)); right['manifest']['provider']='HISTDATA'
    right['dataset_id']='fixture-histdata'
    for c in right['candles']: c['close']=str(Decimal(c['close'])+1)
    before=json.dumps([left,right],sort_keys=True)
    report=compare(left,right)
    assert report['paired_bars']==3 and report['price_correlation']==pytest.approx(1)
    assert report['median_relative_offset']<0 and not report['equivalent_contract_proven']
    assert json.dumps([left,right],sort_keys=True)==before
    with pytest.raises(ValueError): compare(left,left)


def test_query_replay_immutability_unknown_crossing_and_obsolete_rule(tmp_path,monkeypatch):
    import core.rebuild.export_research as module
    import sqlite3
    from core.rebuild.market_data import digest, encode
    store=MarketStore(tmp_path/'research',fixture=True)
    data=saved(store,[row(),row(1),row(3)])
    # Isolate the query mechanics; the separate tests prove fixtures reject without this mock.
    monkeypatch.setattr(module,'trusted',lambda data: True)
    service=ExportResearch(store)
    q=service.qualify(data['dataset_id'],hourly_dataset=data['dataset_id'])
    assert q['state']=='QUALIFIED_WITH_KNOWN_LIMITATIONS'
    reader=ResearchDatasetReader(store)
    a=reader.query(q['qualification_id'],start=START,end=START+timedelta(hours=2))
    reopened=ResearchDatasetReader(MarketStore(store.root,fixture=True))
    assert reopened.query(q['qualification_id'],start=START,end=START+timedelta(hours=2))==a
    with pytest.raises(ValueError): reader.query(q['qualification_id'],start=START,end=START+timedelta(hours=4))
    with pytest.raises(ValueError): reader.query('latest',start=START,end=START+timedelta(hours=2))
    old=dict(q); old.pop('qualification_id'); old['version']='obsolete'
    with store.connect() as c:
        c.execute('INSERT INTO p5_export_qualification VALUES(?,?,?)',(digest(old),data['dataset_id'],encode(old)))
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM p5_export_qualification')
        with pytest.raises(sqlite3.IntegrityError): c.execute("UPDATE p5_export_qualification SET payload='{}'")
    with pytest.raises(ValueError): reader.query(digest(old),start=START,end=START+timedelta(hours=2))
