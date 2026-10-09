"""Version-pinned public-export research views; no price repair or execution."""
from datetime import datetime, timedelta
from decimal import Decimal
import json
from zoneinfo import ZoneInfo
from importlib.resources import files
import tzdata

from .evtl_provider import PROVIDER, VERSION as NORMALIZER, ORIGIN
from .market_data import Candle, INTERVALS, VALIDATOR, digest, encode, utc

VERSION = 'evtl-hourly-session-v1'
HOUR = timedelta(hours=1)
if tzdata.__version__ != '2025.2':
    raise RuntimeError('Pinned historical timezone package required')
with files('tzdata.zoneinfo.America').joinpath('New_York').open('rb') as _zone:
    NY = ZoneInfo.from_file(_zone, key='America/New_York')
REFERENCES = [
    ORIGIN+'/data',
    'https://www.dukascopy.com/swiss/english/forex/forex-trading-accounts/link/',
    'https://www.dukascopy.com/swiss/english/cfd/range-of-markets/wti-oil-cfd-trading/',
]


def expected_hour(stamp):
    """Documented upstream regular hours, subject to whole-source conflict checks.

    Application to distributor history is an explicit market inference, not an
    attestation of historical holidays or a future execution-session calendar.
    """
    t = utc(stamp).astimezone(NY)
    return not (t.weekday()==5 or t.weekday()==4 and t.hour>=17
                or t.weekday()==6 and t.hour<18 or t.hour==17)


def verified_rows(data):
    m = data['manifest']
    if m['provider']!=PROVIDER or m['normalization']!=NORMALIZER or m['validation']!=VALIDATOR:
        raise ValueError('Unsupported provider/normalizer/validator')
    if m['timeframe'] not in {'1H','4H'} or m.get('price_basis')!='BID_WITH_SEPARATE_ASK_OHLC':
        raise ValueError('Unsupported bar semantics')
    bars = [Candle.model_validate(c) for c in data['candles']]
    if digest([b.payload() for b in bars]) != m['content_hash'] or len(bars)!=m['bar_count']:
        raise ValueError('Content identity mismatch')
    if any((b.provider,b.instrument,b.timeframe)!=(PROVIDER,m['instrument'],m['timeframe']) for b in bars):
        raise ValueError('Mixed source identities')
    if any(a.opened>=b.opened for a,b in zip(bars,bars[1:])):
        raise ValueError('Noncanonical ordering or duplicates')
    return {b.opened:b for b in bars}


def aggregate_matches(parent, children):
    if not children: return False
    for side in ('BID','ASK'):
        rows = [{k:getattr(c,k) for k in ('open','high','low','close')} for c in children] if side=='BID' else [c.ask_ohlc for c in children]
        actual = {k:getattr(parent,k) for k in rows[0]} if side=='BID' else parent.ask_ohlc
        expected = dict(open=rows[0]['open'],high=max(r['high'] for r in rows),
                        low=min(r['low'] for r in rows),close=rows[-1]['close'])
        if actual!=expected: return False
    return True


def assess(data, hourly):
    """Pure deterministic assessment; fixtures may test this but cannot qualify."""
    bars, hours = verified_rows(data), verified_rows(hourly)
    m,h = data['manifest'],hourly['manifest']
    if h['timeframe']!='1H' or any(m[k]!=h[k] for k in ('provider','instrument','start','end')):
        raise ValueError('Hourly evidence identity/range mismatch')
    start,end = datetime.fromisoformat(m['start']),datetime.fromisoformat(m['end'])
    if start.year<2021 or end>datetime(2026,1,1,tzinfo=start.tzinfo):
        raise ValueError('Calendar evidence scope is 2021-2025 only')
    if end<=start or end-start>timedelta(days=366*5): raise ValueError('Bounded interval required')
    closed = []
    t = start
    while t<end:
        if not expected_hour(t): closed.append(t.isoformat())
        t+=HOUR
    conflicts = [t.isoformat() for t in hours if not expected_hour(t)]
    unsafe = {'CONFLICTING_DUPLICATE','MALFORMED_NATIVE_ROW','INCOMPLETE_RESAMPLE'}
    allowed = {'DISJOINT_ADJACENT_PRICE_RANGES','IDENTICAL_DUPLICATE','OUT_OF_ORDER'}
    invalid = [i for d in (m,h) for i in d['issues'] if i['kind'] in unsafe or i['kind'] not in allowed]
    calendar = dict(version=VERSION,provider=PROVIDER,instrument=m['instrument'],
        start=m['start'],end=m['end'],basis='DOCUMENTED_UPSTREAM_PLUS_EMPIRICAL_DISTRIBUTOR_CHECK',
        references=REFERENCES,timezone_package='tzdata==2025.2',closed_hour_hash=digest(closed),closed_hours=len(closed),
        holiday_exemptions=[],conflicts=conflicts)
    step = timedelta(seconds=INTERVALS[m['timeframe']])
    audit,segments,current = [],[],None
    t=start
    while t<end:
        slots = [t+HOUR*i for i in range(int(step/HOUR))]
        required = [s for s in slots if expected_hour(s)]
        missing = [s.isoformat() for s in required if s not in hours]
        children = [hours[s] for s in slots if s in hours]
        mismatch = t in bars and m['timeframe']=='4H' and not aggregate_matches(bars[t],children)
        if missing or (required and t not in bars) or mismatch:
            kind = 'UNKNOWN_GAP' if not mismatch else 'PROVIDER_AGGREGATION_CONFLICT'
        elif not required:
            kind = 'EXPECTED_FEED_CLOSURE' if t not in bars else 'CLOSURE_CONFLICT'
        else:
            kind = 'COMPLETE'
        item = dict(start=t.isoformat(),end=(t+step).isoformat(),classification=kind,
                    missing_hours=missing,actual_bar=t in bars)
        audit.append(item)
        if kind=='COMPLETE':
            if current is None: current=dict(start=t.isoformat(),end=item['end'],actual_bars=0,closure_bars=0)
            current['actual_bars']+=1; current['end']=item['end']
        elif kind=='EXPECTED_FEED_CLOSURE':
            if current: current['closure_bars']+=1; current['end']=item['end']
        else:
            if current: segments.append(current); current=None
        t+=step
    if current: segments.append(current)
    segments.sort(key=lambda s:(-(datetime.fromisoformat(s['end'])-datetime.fromisoformat(s['start'])).total_seconds(),s['start']))
    unknown = [r for r in audit if r['classification'] not in {'COMPLETE','EXPECTED_FEED_CLOSURE'}]
    longest,current_length = 0,0
    for r in audit:
        current_length = current_length+int(step.total_seconds()) if r['classification'] not in {'COMPLETE','EXPECTED_FEED_CLOSURE'} else 0
        longest=max(longest,current_length)
    return dict(version=VERSION,dataset_id=data['dataset_id'],hourly_dataset_id=hourly['dataset_id'],
        calendar=calendar,calendar_id=digest(calendar),conflicts=conflicts,invalid_issues=invalid,
        actual_bars=len(bars),expected_bars=sum(bool(r['classification']!='EXPECTED_FEED_CLOSURE') for r in audit),
        known_closure_bars=sum(r['classification']=='EXPECTED_FEED_CLOSURE' for r in audit),
        unexplained_bars=len(unknown),longest_unexplained_gap_seconds=longest,
        unresolved_intervals=unknown,segments=segments,longest_range=segments[0] if segments else None,
        research_only=True,price_basis=m['price_basis'],mapping=m['mapping'],
        limitations=['Provider-native H1 bars; sub-hour completeness not independently attested',
          'Historical regular-session inference only; unconfirmed holidays remain UNKNOWN',
          'No bridging unknown intervals, no synthetic fill, no mixed providers',
          'Bid and ask extrema need not be simultaneous; no intrabar spread inference',
          'Provider v units unknown; not validated exchange or tick volume',
          'WTI construction/roll and broker equivalence unverified; research proxy only'])


def trusted(data):
    if not data['manifest']['real_data'] or not data['provenance']: return False
    symbol=data['manifest']['mapping']['provider_symbol']
    frame={'1H':'H1','4H':'H4'}[data['manifest']['timeframe']]
    for receipt in data['provenance']:
        p=json.loads(receipt['provenance'])
        if p.get('fixture',True) or not p.get('responses'): return False
        for r in p['responses']:
            if (r.get('fixture',True) or r.get('provider')!=PROVIDER or r.get('adapter')!=NORMALIZER
                or r.get('price_side')!='BID_WITH_SEPARATE_ASK_OHLC'
                or not r.get('url','').startswith(ORIGIN+f'/api/simulator/data/{symbol}/{frame}/')
                or len(r.get('sha256',''))!=64): return False
    return True


class ExportResearch:
    def __init__(self,store):
        self.store=store
        with store.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS p5_export_qualification(id TEXT PRIMARY KEY,dataset TEXT NOT NULL,payload TEXT NOT NULL,FOREIGN KEY(dataset) REFERENCES datasets(id))')
            c.execute('INSERT OR IGNORE INTO p5_schema VALUES(6)')
            for op in ('UPDATE','DELETE'):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_export_{op} BEFORE {op} ON p5_export_qualification BEGIN SELECT RAISE(ABORT,'Immutable export qualification'); END")

    def qualify(self,dataset,*,hourly_dataset):
        data=self.store.query(dataset,research=False)
        hourly=self.store.query(hourly_dataset,research=False)
        report=assess(data,hourly)
        report['state']='QUALIFIED_WITH_KNOWN_LIMITATIONS' if (
            trusted(data) and trusted(hourly) and not report['conflicts'] and not report['invalid_issues']
            and report['segments']) else 'REJECTED'
        identity=digest(report)
        with self.store.connect() as c:
            c.execute('INSERT OR IGNORE INTO p5_export_qualification VALUES(?,?,?)',(identity,dataset,encode(report)))
        return dict(qualification_id=identity,**report)

    def query(self,identity,*,start,end):
        with self.store.connect() as c:
            row=c.execute('SELECT payload FROM p5_export_qualification WHERE id=?',(identity,)).fetchone()
        if not row: raise ValueError('Unknown qualification')
        q=json.loads(row[0]); a,b=utc(start),utc(end)
        if digest(q)!=identity or q['version']!=VERSION or q['state']!='QUALIFIED_WITH_KNOWN_LIMITATIONS':
            raise ValueError('Qualification unavailable or superseded')
        if not any(datetime.fromisoformat(s['start'])<=a<b<=datetime.fromisoformat(s['end']) for s in q['segments']):
            raise ValueError('Unresolved interval in requested range')
        data=self.store.query(q['dataset_id'],start=a,end=b,research=False)
        if not data['candles']: raise ValueError('No observed bars')
        return dict(data,qualification_id=identity,qualification=q)


def kronos_rows(view,*,as_of):
    """K-line representation only; UNKNOWN volume remains explicit in sidecar."""
    as_of=utc(as_of)
    rows=[]
    for c in view['candles']:
        bar=Candle.model_validate(c)
        if bar.closed>as_of: raise ValueError('Incomplete/future candle cannot be exposed')
        rows.append(dict(timestamp=bar.opened.isoformat(),open=c['open'],high=c['high'],
                         low=c['low'],close=c['close'],volume=c['volume']))
    return dict(rows=rows,dataset_id=view['dataset_id'],qualification_id=view['qualification_id'],
        row_hash=digest(rows),price_basis='BID',ask_retained_in_dataset=True,
        volume_kind='UNKNOWN',runtime_compatible='UNVERIFIED',as_of=as_of.isoformat())
