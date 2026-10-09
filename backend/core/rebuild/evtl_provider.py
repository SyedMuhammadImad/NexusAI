"""Public closed-year EV Trading Labs exports; no account or broker access.

Data attribution: EV Trading Labs (https://evtradelabs.com/data).
Upstream Dukascopy identity is the distributor's assertion, not direct acquisition.
"""
from datetime import datetime, timedelta
from decimal import Decimal
import gzip
import hashlib
import io
import json

import httpx

from .market_data import Candle, EVTL_MAPPINGS, INTERVALS, UTC, utc

PROVIDER = 'EV_TRADING_LABS'
VERSION = 'evtl-json-v1'
ORIGIN = 'https://evtradelabs.com'
CATALOG = ORIGIN + '/api/data/catalog'
MAX_RAW = 4 * 1024 * 1024
MAX_JSON = 16 * 1024 * 1024


def read_json(body):
    def pairs(items):
        result = {}
        for k,v in items:
            if k in result: raise ValueError('Duplicate JSON field')
            result[k] = v
        return result
    def invalid(_):
        raise ValueError('Non-finite JSON number')
    return json.loads(body, parse_float=Decimal, parse_constant=invalid, object_pairs_hook=pairs)


class EVTLProvider:
    def __init__(self, client=None):
        self.client = client
        self.fixture = client is not None

    def _get(self, url):
        if not url.startswith(ORIGIN + '/api/'):
            raise ValueError('Provider origin mismatch')
        def get(client):
            with client.stream('GET', url) as response:
                response.raise_for_status()
                if response.is_redirect: raise ValueError('Redirect not authorized')
                chunks, size = [], 0
                for block in response.iter_bytes():
                    size += len(block)
                    if size > MAX_RAW: raise ValueError('Oversized provider response')
                    chunks.append(block)
                return b''.join(chunks)
        if self.client is not None: return get(self.client)
        with httpx.Client(timeout=45, follow_redirects=False, trust_env=False) as client:
            return get(client)

    def catalogue(self):
        raw = self._get(CATALOG)
        data = read_json(raw)
        if not isinstance(data,dict) or not isinstance(data.get('files'),list):
            raise ValueError('Invalid provider catalogue')
        return raw, data['files']

    def download(self, instrument, timeframe, year, catalogue):
        if instrument not in EVTL_MAPPINGS or timeframe not in {'1H','4H'}:
            raise ValueError('Unsupported export')
        if type(year) is not int or not 2000 <= year < datetime.now(UTC).year:
            raise ValueError('Only closed public calendar years supported')
        symbol = EVTL_MAPPINGS[instrument]['provider_symbol']
        native_frame = {'1H':'H1','4H':'H4'}[timeframe]
        key = f'{symbol}/{native_frame}/{year}.json.gz'
        if not isinstance(catalogue,list) or any(not isinstance(e,dict) for e in catalogue):
            raise ValueError('Malformed catalogue entries')
        entries = [e for e in catalogue if e.get('key') == key]
        if len(entries) != 1: raise ValueError('Missing/duplicate catalogue identity')
        entry = entries[0]
        if any(type(entry.get(k)) is not int for k in ('year','bars','first','last','bytes')):
            raise ValueError('Catalogue integer fields required')
        path = '/api/simulator/data/' + key
        if (entry.get('symbol'),entry.get('tf'),entry.get('year'),entry.get('url')) != (symbol,native_frame,year,path):
            raise ValueError('Contradictory catalogue metadata')
        raw = self._get(ORIGIN + path)
        if len(raw)!=entry['bytes']: raise ValueError('Catalogue byte count mismatch')
        candles = self.normalize(raw,instrument,timeframe,year)
        if not candles or len(candles)!=entry.get('bars'):
            raise ValueError('Partial export/count mismatch')
        stamps = [int(c.opened.timestamp()) for c in candles]
        if (min(stamps),max(stamps)) != (entry.get('first'),entry.get('last')):
            raise ValueError('Catalogue bounds mismatch')
        return raw, candles, dict(provider=PROVIDER, adapter=VERSION, fixture=self.fixture,
                                  url=ORIGIN+path, key=key, catalogue_entry=entry,
                                  sha256=hashlib.sha256(raw).hexdigest(), raw_observation_count=len(candles),
                                  price_side='BID_WITH_SEPARATE_ASK_OHLC',
                                  volume_semantics='Unverified provider v; not exchange trade volume',
                                  timestamp_semantics='Unix seconds UTC bar open',
                                  upstream='Dukascopy, distributor assertion',
                                  license_ref=ORIGIN+'/data', attribution='EV Trading Labs')

    def normalize(self, raw, instrument, timeframe, year):
        if instrument not in EVTL_MAPPINGS or timeframe not in {'1H','4H'}:
            raise ValueError('Unsupported normalization')
        if len(raw)>MAX_RAW: raise ValueError('Oversized compressed source')
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:
            text = source.read(MAX_JSON+1)
        if len(text)>MAX_JSON: raise ValueError('Oversized decompressed source')
        rows = read_json(text)
        if not isinstance(rows,list) or len(rows)>9000:
            raise ValueError('Invalid annual row collection')
        fields = {'ts','o','h','l','c','ao','ah','al','ac','v'}
        candles=[]
        for row in rows:
            if not isinstance(row,dict) or set(row)!=fields or type(row['ts']) is not int:
                raise ValueError('Malformed native row')
            if any(isinstance(row[k],bool) or not isinstance(row[k],(Decimal,int)) for k in fields-{'ts'}):
                raise ValueError('Native numeric types required')
            stamp=datetime.fromtimestamp(row['ts'],UTC)
            if stamp.year!=year: raise ValueError('Observation outside source year')
            candles.append(Candle(instrument=instrument,provider=PROVIDER,
                provider_symbol=EVTL_MAPPINGS[instrument]['provider_symbol'],timeframe=timeframe,
                opened=stamp,closed=stamp+timedelta(seconds=INTERVALS[timeframe]),
                open=row['o'],high=row['h'],low=row['l'],close=row['c'],
                ask_ohlc=dict(open=row['ao'],high=row['ah'],low=row['al'],close=row['ac']),
                price_basis='BID',volume=row['v'],volume_kind='UNKNOWN',spread=None,
                source_time=str(row['ts']),timezone_evidence='Provider-documented Unix seconds UTC, bar open'))
        return candles


def acquire(store,provider,instrument,timeframe,start,end,*,parent=None):
    start,end=utc(start),utc(end)
    if end<=start or end-start>timedelta(days=366*6): raise ValueError('Bounded research interval required')
    catalog_raw, entries=provider.catalogue()
    raw_parts=[catalog_raw]
    bars,responses=[],[]
    for year in range(start.year,(end-timedelta(microseconds=1)).year+1):
        raw, rows, response=provider.download(instrument,timeframe,year,entries)
        raw_parts.append(raw); responses.append(response)
        bars.extend(c for c in rows if start<=c.opened<end)
    bundle=b''.join(len(p).to_bytes(8,'big')+p for p in raw_parts)
    return store.save(instrument,timeframe,start,end,bars,raw=bundle,
        provenance=dict(fixture=provider.fixture,responses=responses,catalogue_sha256=hashlib.sha256(catalog_raw).hexdigest()),
        parent=parent,provider=PROVIDER)
