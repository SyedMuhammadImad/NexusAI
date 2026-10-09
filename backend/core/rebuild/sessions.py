"""Versioned, evidence-bearing calendars and append-only session qualification."""
from collections import Counter
from datetime import datetime, timedelta
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .market_data import INTERVALS, MAPPINGS, UTC, digest, encode, utc
from .research_data import ResearchData

VERSION='p5-session-continuity-v1'
CLOSED={'EXPECTED_SESSION_CLOSURE','EXPECTED_HOLIDAY_CLOSURE','EXPECTED_MAINTENANCE_BREAK'}


class Window(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    start: datetime
    end: datetime
    kind: Literal['EXPECTED_SESSION_CLOSURE','EXPECTED_HOLIDAY_CLOSURE',
                  'EXPECTED_MAINTENANCE_BREAK','PROVIDER_GAP']
    evidence_ref: str = Field(min_length=1)
    evidence_note: str = Field(min_length=1)
    basis: Literal['PROVIDER_CONFIRMED','MARKET_INFERENCE','FIXTURE']

    @model_validator(mode='after')
    def valid(self):
        a,b=utc(self.start),utc(self.end)
        if a>=b or a.timestamp()%60 or b.timestamp()%60:
            raise ValueError('Aligned nonempty session window required')
        if not self.evidence_ref.strip() or not self.evidence_note.strip():
            raise ValueError('Evidence required')
        object.__setattr__(self,'start',a); object.__setattr__(self,'end',b)
        return self


class Calendar(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    provider: Literal['HISTDATA'] = 'HISTDATA'
    instrument: Literal['XAUUSD','XAGUSD','USOIL']
    version: str = Field(min_length=1)
    source_timezone: Literal['EST_FIXED_UTC_MINUS_05_NO_DST'] = 'EST_FIXED_UTC_MINUS_05_NO_DST'
    start: datetime
    end: datetime
    windows: tuple[Window,...] = ()

    @model_validator(mode='after')
    def valid(self):
        a,b=utc(self.start),utc(self.end)
        if a>=b or (b-a).days>366 or a.timestamp()%60 or b.timestamp()%60:
            raise ValueError('Bounded calendar required')
        ordered=tuple(sorted(set(self.windows),key=lambda w:(w.start,w.end)))
        previous=a
        for w in ordered:
            if not a<=w.start<w.end<=b or w.start<previous:
                raise ValueError('Conflicting or out-of-range calendar windows')
            previous=w.end
        object.__setattr__(self,'start',a); object.__setattr__(self,'end',b)
        object.__setattr__(self,'windows',ordered)
        return self

    @property
    def identity(self):
        return digest(self.model_dump(mode='json'))

    def at(self,provider,instrument,stamp):
        stamp=utc(stamp)
        if (provider,instrument)!=(self.provider,self.instrument) or not self.start<=stamp<self.end:
            raise ValueError('Calendar identity/range mismatch')
        window=next((w for w in self.windows if w.start<=stamp<w.end),None)
        return dict(expected=not window or window.kind not in CLOSED,
                    classification=window.kind if window else 'UNKNOWN_GAP',
                    evidence=window.model_dump(mode='json') if window else None)


def histdata_2021(instrument):
    """Narrow inferred weekend core, not an exact HistData session calendar."""
    if instrument not in MAPPINGS: raise ValueError('Unknown instrument')
    a=datetime(2021,1,1,tzinfo=UTC); b=datetime(2022,1,1,tzinfo=UTC)
    reference=('https://www.cmegroup.com/notices/ser/2021/06/SER-8782R.pdf' if instrument=='USOIL'
               else 'https://www.cmegroup.com/trading/metals/precious/files/precious-metals-spot-spread.pdf')
    windows=[]; day=a
    while day<b:
        if day.weekday()==5:
            windows.append(Window(start=day,end=day+timedelta(days=1),kind='EXPECTED_SESSION_CLOSURE',
                evidence_ref=reference,
                evidence_note='Related-market Sunday-Friday schedule supports only a conservative Saturday UTC inference for 2021; not exact HistData identity, daily hours, holidays or provider attestation.',
                basis='MARKET_INFERENCE'))
        day+=timedelta(days=1)
    return Calendar(instrument=instrument,version='histdata-2021-saturday-core-v1',start=a,end=b,windows=tuple(windows))


def assess(data,calendar):
    calendar=Calendar.model_validate(calendar)
    m=data['manifest']; start=datetime.fromisoformat(m['start']); end=datetime.fromisoformat(m['end'])
    if (m['provider'],m['instrument'])!=(calendar.provider,calendar.instrument) or not calendar.start<=start<end<=calendar.end:
        raise ValueError('Dataset/calendar mismatch')
    seconds=INTERVALS[m['timeframe']]; step=timedelta(seconds=seconds)
    if (end-start)/step>600000: raise ValueError('Bounded assessment required')
    present={datetime.fromisoformat(c['opened']) for c in data['candles']}
    if len(present)!=len(data['candles']) or any(not start<=t<end or t.timestamp()%seconds for t in present):
        raise ValueError('Invalid observed timestamps')
    if any((c['provider'],c['instrument'],c['timeframe'])!=(m['provider'],m['instrument'],m['timeframe']) for c in data['candles']):
        raise ValueError('Mixed observations')
    gaps=[]; segments=[]; counts=Counter(); current=None; pointer=0; conflicts=[]
    stamp=start
    while stamp<end:
        stop=stamp+step
        while pointer<len(calendar.windows) and calendar.windows[pointer].end<=stamp: pointer+=1
        # Partial closure never exempts an entire aggregate: unresolved minutes stay visible.
        w=calendar.windows[pointer] if pointer<len(calendar.windows) else None
        covered=w is not None and w.start<=stamp and stop<=w.end
        kind=w.kind if covered else 'UNKNOWN_GAP'
        closed=covered and kind in CLOSED
        if stamp in present:
            if w is not None and w.kind in CLOSED and w.start<stop and stamp<w.end:
                conflicts.append(dict(start=stamp.isoformat(),end=stop.isoformat()))
            if current is None: current=dict(start=stamp.isoformat(),end=stop.isoformat(),actual_bars=0,expected_closures=0)
            current['actual_bars']+=1; current['end']=stop.isoformat()
        else:
            counts[kind]+=1
            if gaps and gaps[-1]['end']==stamp.isoformat() and gaps[-1]['classification']==kind and gaps[-1]['evidence_ref']==(w.evidence_ref if covered else None):
                gaps[-1]['end']=stop.isoformat(); gaps[-1]['bars']+=1
            else:
                gaps.append(dict(start=stamp.isoformat(),end=stop.isoformat(),bars=1,classification=kind,
                                 evidence_ref=w.evidence_ref if covered else None))
            if closed and current is not None:
                current['expected_closures']+=1; current['end']=stop.isoformat()
            elif not closed and current is not None:
                segments.append(current); current=None
        stamp=stop
    if current: segments.append(current)
    for s in segments:
        s['expected_bars']=s['actual_bars']; s['unexplained_missing_bars']=0; s['longest_unexplained_gap']=0
    segments.sort(key=lambda s:(-(datetime.fromisoformat(s['end'])-datetime.fromisoformat(s['start'])).total_seconds(),s['start']))
    unresolved=[g for g in gaps if g['classification'] not in CLOSED]
    return dict(rule=VERSION,dataset_id=data['dataset_id'],calendar_id=calendar.identity,
                calendar=calendar.model_dump(mode='json'),start=start.isoformat(),end=end.isoformat(),
                actual_bars=len(present),expected_bars=int((end-start)/step)-sum(counts[k] for k in CLOSED),
                expected_closures=sum(counts[k] for k in CLOSED),classification_counts=dict(counts),
                unexplained_missing_bars=sum(g['bars'] for g in unresolved),
                longest_unexplained_gap_seconds=max((g['bars']*seconds for g in unresolved),default=0),
                gaps=gaps,segments=segments,longest_range=segments[0] if segments else None,
                calendar_conflicts=conflicts,calendar_certainty='PARTIAL' if any(w.basis=='MARKET_INFERENCE' for w in calendar.windows) else 'EVIDENCE_SCOPED')


class SessionResearch:
    def __init__(self,store):
        self.store=store
        with store.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS p5_session_qualification(id TEXT PRIMARY KEY,dataset TEXT NOT NULL,payload TEXT NOT NULL,FOREIGN KEY(dataset) REFERENCES datasets(id))')
            c.execute('INSERT OR IGNORE INTO p5_schema VALUES(4)')
            for op in ('UPDATE','DELETE'):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_session_{op} BEFORE {op} ON p5_session_qualification BEGIN SELECT RAISE(ABORT,'Immutable session qualification'); END")

    def qualify(self,dataset,calendar):
        calendar=Calendar.model_validate(calendar)
        q=ResearchData(self.store).qualify(dataset)
        data=self.store.query(dataset,research=False)
        report=assess(data,calendar)
        fixture=any(w.basis=='FIXTURE' for w in calendar.windows)
        report['state']='REJECTED' if (not q['state'].startswith('QUALIFIED') or q['excluded_count'] or fixture or report['calendar_conflicts']) else 'QUALIFIED_SEGMENTS_ONLY'
        report['observation_qualification_id']=q['qualification_id']
        report['limitations']=['No crossing UNKNOWN_GAP/PROVIDER_GAP','Inferred market closures are not exact provider hours','No strategy or phase qualification follows']
        identity=digest(report)
        with self.store.connect() as c:
            c.execute('INSERT OR IGNORE INTO p5_session_qualification VALUES(?,?,?)',(identity,dataset,encode(report)))
        return dict(qualification_id=identity,**report)

    def query(self,identity,*,start,end):
        with self.store.connect() as c:
            row=c.execute('SELECT payload FROM p5_session_qualification WHERE id=?',(identity,)).fetchone()
        if not row: raise ValueError('Unknown session qualification')
        q=json.loads(row[0]); a,b=utc(start),utc(end)
        if q['rule']!=VERSION or q['state']!='QUALIFIED_SEGMENTS_ONLY': raise ValueError('Session qualification unavailable')
        if not any(datetime.fromisoformat(s['start'])<=a<b<=datetime.fromisoformat(s['end']) for s in q['segments']):
            raise ValueError('Unresolved gap in requested range')
        data=self.store.query(q['dataset_id'],start=a,end=b,research=False)
        if not data['candles']: raise ValueError('No observed bars')
        return dict(data,session_qualification=q,qualification_id=identity)
