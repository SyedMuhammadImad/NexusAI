"""Synthetic validation fixtures only; never qualification price evidence."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
import json
import sqlite3
import zipfile

import pytest

from core.rebuild.market_data import Candle, MarketStore, MAPPINGS, UTC, series, resample
from core.rebuild.histdata_provider import HistDataProvider, sync, DownloadForm

START = datetime(2025, 1, 6, 12, tzinfo=UTC)


def bar(index=0, **change):
    values = dict(instrument='XAUUSD', provider_symbol='XAUUSD', timeframe='1M',
                  opened=START+timedelta(minutes=index), closed=START+timedelta(minutes=index+1),
                  open='100', high='102', low='99', close='101', timezone_evidence='UTC', source_time='fixture')
    values.update(change)
    return Candle(**values)


@pytest.fixture
def store(tmp_path):
    return MarketStore(tmp_path/'p5', fixture=True)


def save(store, data=None, end=None, **kwargs):
    return store.save('XAUUSD', '1M', START, end or START+timedelta(minutes=2), data or [bar(), bar(1)],
                      raw=b'fixture-only', provenance={'fixture': True}, **kwargs)


def test_valid_precise_and_timezone():
    c = bar(open='100.000000000001', opened=START.astimezone(timezone(timedelta(hours=5))))
    assert c.open == Decimal('100.000000000001') and c.opened == START
    assert c.opened.utcoffset() == timedelta(0)


def test_decimal_identity_does_not_round_through_default_context():
    c=bar(open='100000000000000000.000000000001',high='100000000000000001',
          low='99999999999999999',close='100000000000000000')
    assert c.payload()['open']=='100000000000000000.000000000001'
    assert bar(open='100.000').payload()==bar(open='100').payload()


@pytest.mark.parametrize('changes', [
    {'open':'NaN'}, {'high':'Infinity'}, {'low':'-Infinity'}, {'close':'0'}, {'low':'103'},
    {'open':'1e100'}, {'volume':'-1'}, {'volume':'NaN'}, {'volume':'1'}, {'volume_kind':'REAL'},
    {'opened':START.replace(tzinfo=None)}, {'closed':START+timedelta(minutes=2)},
    {'opened':START+timedelta(seconds=1)}, {'provider_symbol':'GC=F'}, {'instrument':'EURUSD'},
    {'timeframe':'15M'}, {'spread':'-1'}, {'open':'oops'}])
def test_bad_candles_reject(changes):
    with pytest.raises(ValueError): bar(**changes)


def test_gaps_duplicates_conflicts_and_order():
    data = [bar(2), bar(), bar(), bar(1), bar(1,close='100')]
    ordered, issues, gaps = series(data, START, START+timedelta(minutes=4), '1M')
    assert [c.opened for c in ordered] == [START, START+timedelta(minutes=2)]
    assert {x['kind'] for x in issues} == {'OUT_OF_ORDER','IDENTICAL_DUPLICATE','CONFLICTING_DUPLICATE'}
    assert sum(g['missing_count'] for g in gaps)==2
    assert all(g['classification']=='UNKNOWN_SESSION_OR_MISSING' for g in gaps)


@pytest.mark.parametrize('timeframe,count',[('1H',60),('4H',240)])
def test_complete_resampling_reproducible(timeframe,count):
    data = [bar(i) for i in range(count)]
    result, issues = resample(data,timeframe)
    assert not issues and len(result)==1
    assert result[0].open==100 and result[0].close==101 and result[0].volume is None
    assert result[0].opened==START and result[0].closed==START+timedelta(minutes=count)
    assert resample(list(reversed(data)),timeframe)==(result,issues)
    partial, warnings = resample(data[:-1],timeframe)
    assert partial==[] and warnings[0]['kind']=='INCOMPLETE_RESAMPLE'


def test_store_replay_correction_range_and_restart(store):
    a=save(store)
    assert save(store)==a
    b=save(store,[bar(close='100'),bar(1)],parent=a)
    assert b!=a and store.query(a,research=False)['candles'][0]['close']=='101'
    reopened=MarketStore(store.root,fixture=True)
    assert reopened.query(b,research=False)['candles'][0]['close']=='100'
    assert len(reopened.query(a,start=START+timedelta(minutes=1),research=False)['candles'])==1
    with pytest.raises(ValueError): reopened.query(a,end=START+timedelta(seconds=30),research=False)
    with pytest.raises(ValueError): reopened.query(a,start=START-timedelta(minutes=1),research=False)
    with pytest.raises(ValueError): reopened.query(a)  # Fixtures cannot qualify as real research data.
    with reopened.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM datasets').fetchone()[0]==2
        assert c.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]==2
        for table in ('bars','raw','datasets','receipts'):
            with pytest.raises(sqlite3.IntegrityError): c.execute(f'DELETE FROM {table}')


def test_invalid_parent_rolls_back(store):
    with pytest.raises(ValueError): save(store,parent='absent')
    with store.connect() as c:
        assert c.execute('SELECT count(*) FROM datasets').fetchone()[0]==0


def test_superseded_validator_cannot_qualify_old_dataset(store,monkeypatch):
    import core.rebuild.market_data as module
    identity=store.save('XAUUSD','1M',START,START+timedelta(minutes=1),[bar()],raw=b'contract-fixture',provenance={})
    assert store.query(identity)['candles']
    monkeypatch.setattr(module,'VALIDATOR','future-validator-fixture')
    with pytest.raises(ValueError): store.query(identity)
    assert store.query(identity,research=False)['candles']


def test_transport_monthly_and_annual_identity(monkeypatch):
    import httpx
    import core.rebuild.histdata_provider as module
    seen=[]
    original=httpx.Client
    def respond(request):
        seen.append(request)
        if request.method=='POST': return httpx.Response(200,content=archive())
        monthly=request.url.path.endswith('historical-data/') and str(request.url).endswith('/1')
        if monthly: return httpx.Response(200,text='<html>No monthly file</html>')
        fields=dict(tk='public-fixture-form-marker',date='2025',datemonth='2025',platform='ASCII',timeframe='M1',fxpair='XAUUSD')
        return httpx.Response(200,text=''.join(f'<input name="{k}" value="{v}">' for k,v in fields.items()))
    monkeypatch.setattr(module.httpx,'Client',lambda **kw: original(transport=httpx.MockTransport(respond),**kw))
    raw,provenance=HistDataProvider().download('XAUUSD',2025,1)
    assert raw==archive() and provenance['period']=='2025'
    assert len(seen)==3 and 'tk' not in provenance


def test_transport_wrong_symbol_never_posts(monkeypatch):
    import httpx
    import core.rebuild.histdata_provider as module
    original=httpx.Client
    seen=[]
    def respond(request):
        seen.append(request.method)
        return httpx.Response(200,text='<input name="tk" value="fixture"><input name="fxpair" value="WRONG">')
    monkeypatch.setattr(module.httpx,'Client',lambda **kw: original(transport=httpx.MockTransport(respond),**kw))
    with pytest.raises(ValueError): HistDataProvider().download('XAUUSD',2025,1)
    assert seen==['GET']


def test_research_gaps_reject(store):
    identity=store.save('XAUUSD','1M',START,START+timedelta(minutes=3),[bar()],raw=b'real-shaped-fixture',provenance={})
    assert store.query(identity,research=False)['manifest']['status']=='REVIEW_REQUIRED'
    with pytest.raises(ValueError): store.query(identity)


def archive(symbol='XAUUSD', lines=None):
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr(zipfile.ZipInfo(f'DAT_ASCII_{symbol}_M1_202501.csv'),lines or '20250106 070000;100;102;99;101;0\n')
    return stream.getvalue()


def test_native_normalization_missing_volume_and_est():
    values, issues=HistDataProvider().normalize(archive(),'XAUUSD',2025,1)
    assert not issues and values[0].opened==START and values[0].volume is None
    assert values[0].source_time=='20250106 070000'


@pytest.mark.parametrize('line',[
    '20250106 070000;100;90;99;101;0', '20250106 070000;NaN;102;99;101;0',
    '20250106 070000;100;102;99;101;10', '20250206 070000;100;102;99;101;0',
    '20250106 070001;100;102;99;101;0', 'broken'])
def test_native_invalid_rows_recorded(line):
    values, issues=HistDataProvider().normalize(archive(lines=line),'XAUUSD',2025,1)
    assert not values and issues==[{'kind':'MALFORMED_NATIVE_ROW','row':1}]


def test_archive_identity_and_incomplete_response():
    with pytest.raises(ValueError): HistDataProvider().normalize(archive('XAGUSD'),'XAUUSD',2025,1)
    with pytest.raises(zipfile.BadZipFile): HistDataProvider().normalize(b'partial','XAUUSD',2025,1)


def test_annual_archive_explicit_period_and_no_silent_month_guess():
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('DAT_ASCII_WTIUSD_M1_202501.csv','20250106 070000;100;102;99;101;0\n')
    values, issues=HistDataProvider().normalize(stream.getvalue(),'USOIL',2025,1)
    assert len(values)==1 and not issues
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('DAT_ASCII_WTIUSD_M1_2025.csv','20250106 070000;100;102;99;101;0\n20250206 070000;100;102;99;101;0\n')
    values, issues=HistDataProvider().normalize(stream.getvalue(),'USOIL',2025,1)
    assert len(values)==1 and values[0].opened==START and not issues
    annual, issues=HistDataProvider().normalize(stream.getvalue(),'USOIL',2025,None)
    assert [c.opened.month for c in annual]==[1,2] and not issues
    assert all(c.instrument=='USOIL' and c.provider_symbol=='WTIUSD' for c in annual)
    assert HistDataProvider().normalize(stream.getvalue(),'USOIL',2025,None)==(annual,issues)
    with pytest.raises(ValueError): HistDataProvider().normalize(stream.getvalue(),'USOIL',2024,None)


def test_extreme_discontinuity_is_quarantined_not_deleted(store):
    second=bar(1,open='1000000',low='999999',high='1000002',close='1000001')
    identity=save(store,[bar(),second])
    result=store.query(identity,research=False)
    assert len(result['candles'])==2
    assert result['manifest']['issues'][0]['kind']=='DISJOINT_ADJACENT_PRICE_RANGES'
    assert result['manifest']['status']=='REVIEW_REQUIRED'


def test_parent_cannot_cross_instruments(store):
    a=save(store)
    with pytest.raises(ValueError):
        store.save('USOIL','1M',START,START+timedelta(minutes=1),
                   [bar(instrument='USOIL',provider_symbol='WTIUSD')],raw=b'fixture',provenance={'fixture':True},parent=a)


def test_partial_multi_month_download_has_no_dataset(store):
    class Partial(Provider):
        def download(self,instrument,year,month):
            if month==2: raise TimeoutError('fixture second chunk failure')
            return archive(lines='20250131 190000;100;102;99;101;0\n'),dict(fixture=True)
    with pytest.raises(TimeoutError):
        sync(store,Partial(),'XAUUSD','1H',datetime(2025,2,1,4,tzinfo=UTC),datetime(2025,2,1,6,tzinfo=UTC))
    with store.connect() as c:
        assert c.execute('SELECT count(*) FROM datasets').fetchone()[0]==0


class Provider(HistDataProvider):
    def __init__(self): self.fail=False; self.correct=False
    def download(self,instrument,year,month):
        if self.fail: raise TimeoutError('fixture provider unavailable')
        lines='\n'.join(f'{(START+timedelta(minutes=i,hours=-5)).strftime("%Y%m%d %H%M%S")};100;102;99;{100 if self.correct else 101};0' for i in range(480))
        return archive(MAPPINGS[instrument]['provider_symbol'],lines),dict(fixture=True,provider='HISTDATA',adapter=self.version)


@pytest.mark.parametrize('timeframe',['1M','1H','4H'])
@pytest.mark.parametrize('instrument',['XAUUSD','XAGUSD','USOIL'])
def test_sync_mapping_timeframes_replay_incremental(store,timeframe,instrument):
    provider=Provider()
    end=START+timedelta(hours=4)
    a=sync(store,provider,instrument,timeframe,START,end)
    assert sync(store,provider,instrument,timeframe,START,end)==a
    record=store.query(a,research=False)
    assert record['manifest']['instrument']==instrument and record['manifest']['status']=='VALIDATED'
    extended=sync(store,provider,instrument,timeframe,START,end+timedelta(hours=4),parent=a)
    assert extended!=a and len(store.query(extended,research=False)['candles'])==2*len(record['candles'])
    provider.correct=True
    corrected=sync(store,provider,instrument,timeframe,START,end,parent=a)
    assert corrected!=a
    provider.fail=True
    with pytest.raises(TimeoutError): sync(store,provider,instrument,timeframe,START,end)
    assert store.query(a,research=False)==record


def test_unknown_mapping_no_download(store):
    with pytest.raises(ValueError): sync(store,Provider(),'EURUSD','1H',START,START+timedelta(hours=1))


def test_storage_cannot_use_arbitrary_or_unowned_path(tmp_path):
    with pytest.raises(ValueError): MarketStore(tmp_path/'not-default')
    occupied=tmp_path/'occupied'; occupied.mkdir(); (occupied/'unrelated.txt').write_text('fixture')
    with pytest.raises(ValueError): MarketStore(occupied,fixture=True)
    assert not (occupied/'market-data.sqlite3').exists()


def test_public_form_parser():
    form=DownloadForm(); form.feed('<input name="fxpair" value="XAUUSD"><input name="irrelevant" value="unused">')
    assert form.fields=={'fxpair':'XAUUSD'}


def test_no_execution_imports():
    import ast
    from pathlib import Path
    for name in ('market_data.py','histdata_provider.py'):
        source=Path(__file__).parents[1]/'core/rebuild'/name
        tree=ast.parse(source.read_text())
        modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        assert not any(x and any(t in x for t in ('execution','ledger','strategy','backtest','MetaTrader5')) for x in modules)
