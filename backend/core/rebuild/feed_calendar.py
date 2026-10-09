"""Retrospective empirical feed availability. Never execution-session evidence."""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
import json

from .market_data import Candle, INTERVALS, UTC, digest, encode, utc
from .research_data import ResearchData

VERSION='HISTDATA_FEED_CALENDAR_2021_V1'
RULE='all-expected-M1-present-empirical-v1'
MIN_WEEKS=48
MIN_QUARTER_WEEKS=12
WEEK=10080


def minute(stamp):
    value=utc(datetime.fromisoformat(stamp))
    if value.second or value.microsecond: raise ValueError('Minute alignment required')
    return int(value.timestamp())//60


def stamp(value): return datetime.fromtimestamp(value*60,UTC).isoformat()


def slot(value):
    # Unix epoch Thursday; index starts Monday 00:00 UTC, no machine timezone.
    return (value+3*1440)%WEEK


def runs(values,kind):
    out=[]
    for v in sorted(values):
        if out and out[-1]['end_minute']==v: out[-1]['end_minute']=v+1
        else: out.append(dict(start_minute=v,end_minute=v+1,classification=kind))
    return [dict(start=stamp(r['start_minute']),end=stamp(r['end_minute']),
                 missing_minutes=r['end_minute']-r['start_minute'],classification=kind) for r in out]


def derive(data):
    m=data['manifest']; a,b=minute(m['start']),minute(m['end'])
    if (m['provider'],m['timeframe'],m['start'][:10],m['end'][:10])!=('HISTDATA','1M','2021-01-01','2022-01-01'):
        raise ValueError('Complete bounded 2021 M1 snapshot required')
    observed={minute(c['opened']) for c in data['candles']}
    if not observed or len(observed)!=len(data['candles']) or min(observed)<a or max(observed)>=b:
        raise ValueError('Unique in-range observations required')
    if any((c['provider'],c['instrument'],c['timeframe'])!=(m['provider'],m['instrument'],'1M') for c in data['candles']):
        raise ValueError('Mixed feed')
    week_counts=Counter(v-slot(v) for v in observed)
    weeks=sorted(w for w in week_counts if a<=w and w+WEEK<=b)
    quarters=Counter((datetime.fromtimestamp(w*60,UTC).month-1)//3+1 for w in weeks)
    if len(weeks)<MIN_WEEKS or any(quarters[q]<MIN_QUARTER_WEEKS for q in range(1,5)):
        raise ValueError('Insufficient repeated seasonal evidence')
    all_counts=Counter(slot(v) for v in observed)
    week_set=set(weeks)
    full_counts=Counter(slot(v) for v in observed if v-slot(v) in week_set)
    seasonal={str(q):Counter() for q in range(1,5)}
    for v in observed:
        quarter=str((datetime.fromtimestamp(v*60,UTC).month-1)//3+1)
        seasonal[quarter][slot(v)]+=1
    absent=[s for s in range(WEEK) if all_counts[s]==0]
    return dict(version=VERSION,provider=m['provider'],instrument=m['instrument'],
                source_dataset_id=data['dataset_id'],source_content_hash=m['content_hash'],
                start=m['start'],end=m['end'],source_timezone='EST_FIXED_UTC_MINUS_05_NO_DST',
                derivation='weekly-minute-UTC-annual-and-quarter-v2',research_only=True,
                threshold=dict(absence_fraction='1.00',quarter_absence_fraction='1.00',min_full_weeks=MIN_WEEKS,min_weeks_per_quarter=MIN_QUARTER_WEEKS),
                comparable_weeks=[stamp(w) for w in weeks],weeks_per_quarter={str(k):v for k,v in sorted(quarters.items())},
                slot_observed_counts=[all_counts[s] for s in range(WEEK)],
                slot_comparable_observed_counts=[full_counts[s] for s in range(WEEK)],
                recurring_closed_slots=absent,
                quarterly_closed_slots={q:[s for s in range(WEEK) if counts[s]==0] for q,counts in seasonal.items()},
                quarterly_slot_observed_counts={q:[counts[s] for s in range(WEEK)] for q,counts in seasonal.items()},exceptions=[],
                limitations=['Retrospective 2021 availability only; not out-of-sample evidence',
                             'Not official exchange/broker hours; forbidden for execution eligibility'])


def exceptions(models,observed_days):
    if set(models)!={'XAUUSD','XAGUSD','USOIL'} or set(observed_days)!=set(models):
        raise ValueError('All three separately derived feeds required')
    a,b=minute(models['XAUUSD']['start']),minute(models['XAUUSD']['end'])
    if any((m['provider'],minute(m['start']),minute(m['end']))!=('HISTDATA',a,b) for m in models.values()):
        raise ValueError('Cross-feed range mismatch')
    evidence={k:m['source_dataset_id'] for k,m in models.items()}
    for m in models.values():
        closed=closed_minutes(m); found=[]
        for day in range(a//1440,b//1440):
            if all(day not in observed_days[k] for k in models) and any(v not in closed for v in range(day*1440,(day+1)*1440)):
                found.append(dict(start=stamp(day*1440),end=stamp((day+1)*1440),
                    classification='EMPIRICALLY_OBSERVED_HOLIDAY_OR_SPECIAL_CLOSURE',
                    evidence=evidence,basis='Entire UTC day absent across all three feeds; cause not asserted'))
        m['exceptions']=found
    return models


def closed_minutes(model):
    a,b=minute(model['start']),minute(model['end'])
    slots={q:set(values) for q,values in model['quarterly_closed_slots'].items()}
    closed=set()
    for v in range(a,b):
        quarter=str((datetime.fromtimestamp(v*60,UTC).month-1)//3+1)
        if slot(v) in slots[quarter]: closed.add(v)
    for e in model['exceptions']: closed.update(range(minute(e['start']),minute(e['end'])))
    return closed


def aggregate(data,model,frame):
    if frame not in {'1H','4H'}: raise ValueError('Aggregate timeframe required')
    if (data['dataset_id'],data['manifest']['content_hash'],data['manifest']['instrument'])!=(model['source_dataset_id'],model['source_content_hash'],model['instrument']):
        raise ValueError('Calendar/source version mismatch')
    bars={minute(c['opened']):c for c in data['candles']}; closed=closed_minutes(model)
    if closed & bars.keys(): raise ValueError('Observed candle contradicts empirical closure')
    a,b=minute(model['start']),minute(model['end']); width=INTERVALS[frame]//60
    if a%width or b%width: raise ValueError('Aligned aggregates required')
    result=[]; audit=[]; identity=digest(model)
    for start in range(a,b,width):
        expected=set(range(start,start+width))-closed
        missing={v for v in expected if v not in bars}
        kind='UNKNOWN_GAP' if missing else 'EXPECTED_FEED_CLOSURE' if not expected else 'COMPLETE'
        audit.append(dict(start=stamp(start),end=stamp(start+width),classification=kind,
                          expected_minutes=len(expected),actual_minutes=len(expected)-len(missing),
                          missing_minutes=len(missing)))
        if not expected or missing: continue
        group=[bars[v] for v in sorted(expected)]; first=group[0]
        result.append(Candle(instrument=first['instrument'],provider_symbol=first['provider_symbol'],timeframe=frame,
            opened=stamp(start),closed=stamp(start+width),open=first['open'],close=group[-1]['close'],
            high=max(Decimal(c['high']) for c in group),low=min(Decimal(c['low']) for c in group),
            source_time=f'1M:{model["source_dataset_id"]}:{identity}:{first["source_time"]}:{group[-1]["source_time"]}',
            timezone_evidence=model['source_timezone']))
    return result,audit


class FeedResearch:
    def __init__(self,store):
        self.store=store
        with store.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS p5_feed_calendars(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS p5_feed_qualification(id TEXT PRIMARY KEY,dataset TEXT NOT NULL,payload TEXT NOT NULL,FOREIGN KEY(dataset) REFERENCES datasets(id))')
            c.execute('INSERT OR IGNORE INTO p5_schema VALUES(5)')
            for table in ('p5_feed_calendars','p5_feed_qualification'):
                for op in ('UPDATE','DELETE'):
                    c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'Immutable feed evidence'); END")

    def rebuild(self,data,model,frame,raw,provenance):
        # Models are regenerated from source, not trusted caller-supplied closure lists.
        if digest(data['candles'])!=data['manifest']['content_hash']:
            raise ValueError('Source content hash mismatch')
        base=derive(data)
        if any(model[k]!=v for k,v in base.items() if k!='exceptions'):
            raise ValueError('Unverified empirical model')
        for e in model['exceptions']:
            if e['classification']!='EMPIRICALLY_OBSERVED_HOLIDAY_OR_SPECIAL_CLOSURE' or set(e['evidence'])!={'XAUUSD','XAGUSD','USOIL'}:
                raise ValueError('Cross-feed exception evidence required')
            start,end=minute(e['start']),minute(e['end'])
            if end-start!=1440 or start%1440: raise ValueError('Only full-day exceptions permitted')
            for instrument,source in e['evidence'].items():
                evidence=self.store.query(source,start=datetime.fromisoformat(e['start']),end=datetime.fromisoformat(e['end']),research=False)
                if evidence['manifest']['instrument']!=instrument or evidence['manifest']['provider']!='HISTDATA' or evidence['manifest']['timeframe']!='1M' or not evidence['manifest']['real_data'] or evidence['candles']:
                    raise ValueError('Cross-feed absence contradicted')
        q=ResearchData(self.store).qualify(data['dataset_id'])
        if not q['state'].startswith('QUALIFIED') or q['excluded_count']:
            raise ValueError('Source observation qualification required')
        calendar_id=digest(model); bars,audit=aggregate(data,model,frame)
        with self.store.connect() as c:
            c.execute('INSERT OR IGNORE INTO p5_feed_calendars VALUES(?,?)',(calendar_id,encode(model)))
        identity=self.store.save(model['instrument'],frame,datetime.fromisoformat(model['start']),datetime.fromisoformat(model['end']),
            bars,raw=raw,provenance=provenance,derivation=dict(calendar_id=calendar_id,source_dataset_id=data['dataset_id'],resampling_rule=RULE))
        segments=[]; current=None
        for row in audit:
            if row['classification']=='UNKNOWN_GAP':
                if current: segments.append(current); current=None
            elif row['classification']=='COMPLETE':
                if current is None: current=dict(start=row['start'],end=row['end'],actual_bars=0,closure_bars=0)
                current['actual_bars']+=1; current['end']=row['end']
            elif current:
                current['closure_bars']+=1; current['end']=row['end']
        if current: segments.append(current)
        segments.sort(key=lambda s:(-(minute(s['end'])-minute(s['start'])),s['start']))
        unknown=[r for r in audit if r['classification']=='UNKNOWN_GAP']
        report=dict(dataset_id=identity,calendar_id=calendar_id,version=VERSION,resampling_rule=RULE,
                    source_qualification_id=q['qualification_id'],state='QUALIFIED_SEGMENTS_ONLY',
                    actual_bars=len(bars),expected_closure_bars=sum(r['classification']=='EXPECTED_FEED_CLOSURE' for r in audit),
                    unknown_bars=len(unknown),unknown_minutes=sum(r['missing_minutes'] for r in unknown),
                    unresolved_gaps=unknown,segments=segments,longest_range=segments[0] if segments else None,
                    research_only=True,limitations=model['limitations'])
        report_id=digest(report)
        with self.store.connect() as c:
            c.execute('INSERT OR IGNORE INTO p5_feed_qualification VALUES(?,?,?)',(report_id,identity,encode(report)))
        return dict(qualification_id=report_id,**report)

    def query(self,identity,start,end):
        with self.store.connect() as c:
            row=c.execute('SELECT payload FROM p5_feed_qualification WHERE id=?',(identity,)).fetchone()
        if not row: raise ValueError('Unknown feed qualification')
        q=json.loads(row[0])
        if q['version']!=VERSION or q['resampling_rule']!=RULE: raise ValueError('Obsolete feed qualification')
        if not any(minute(s['start'])<=minute(start.isoformat())<minute(end.isoformat())<=minute(s['end']) for s in q['segments']):
            raise ValueError('Unknown gap in requested interval')
        data=self.store.query(q['dataset_id'],start=start,end=end,research=False)
        if not data['candles'] or data['manifest'].get('derivation',{}).get('calendar_id')!=q['calendar_id']:
            raise ValueError('Empty or mismatched calendar binding')
        return dict(data,feed_qualification=q,qualification_id=identity)
