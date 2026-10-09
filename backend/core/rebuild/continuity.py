"""Immutable P5 coverage diagnostics; never repairs or qualifies price evidence."""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .market_data import INTERVALS, digest, encode, utc
from .research_data import classify, partition

RULE = 'p5-continuity-metrics-v2'


class ClosureEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    provider: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    start: datetime
    end: datetime
    valid_from: datetime
    valid_until: datetime
    evidence_ref: str = Field(min_length=1)
    evidence_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid(self):
        a,b,v,w = (utc(getattr(self,n)) for n in ('start','end','valid_from','valid_until'))
        if not v <= a < b <= w or not self.evidence_ref.strip():
            raise ValueError('Closure outside evidenced validity')
        for name,value in zip(('start','end','valid_from','valid_until'),(a,b,v,w)):
            object.__setattr__(self,name,value)
        return self


def _merge(intervals):
    result=[]
    for a,b in sorted(intervals):
        if result and a<=result[-1][1]: result[-1][1]=max(b,result[-1][1])
        else: result.append([a,b])
    return result


def _runs(indices,start,step):
    result=[]
    for i in sorted(indices):
        if result and result[-1][1]==i: result[-1][1]=i+1
        else: result.append([i,i+1])
    return [dict(start=(start+step*a).isoformat(),end=(start+step*b).isoformat(),bars=b-a)
            for a,b in result]


def measure(data, *, start=None, end=None, closures=()):
    """Trusted stored snapshot input; closure assertions require external verification."""
    m=data['manifest']; bars=data['candles']
    start=utc(start) if start else datetime.fromisoformat(m['start'])
    end=utc(end) if end else datetime.fromisoformat(m['end'])
    seconds=INTERVALS[m['timeframe']]; step=timedelta(seconds=seconds)
    if not datetime.fromisoformat(m['start'])<=start<end<=datetime.fromisoformat(m['end']):
        raise ValueError('Coverage outside dataset')
    if start.timestamp()%seconds or end.timestamp()%seconds:
        raise ValueError('Aligned coverage required')
    count=int((end-start)/step)
    if count>600000: raise ValueError('Bounded coverage required')
    evidence=[ClosureEvidence.model_validate(c) for c in closures]
    for c in evidence:
        if (c.provider,c.instrument)!=(m['provider'],m['instrument']):
            raise ValueError('Closure provider/instrument mismatch')
    intervals=_merge((c.start,c.end) for c in evidence)
    present=set(); previous=None; closed=set(); partial=set(); pointer=0
    for c in bars:
        a=datetime.fromisoformat(c['opened']); b=datetime.fromisoformat(c['closed'])
        if (c['provider'],c['instrument'],c['timeframe'])!=(m['provider'],m['instrument'],m['timeframe']):
            raise ValueError('Mixed provider/instrument/timeframe snapshot')
        if not start<=a<b<=end or b-a!=step or a.timestamp()%seconds or previous is not None and a<=previous:
            raise ValueError('Invalid ordered coverage snapshot')
        previous=a; present.add(int((a-start)/step))
    # Only a fully evidenced closed bar is exempt. Partial closure never hides missing data.
    for i in range(count):
        a=start+i*step; b=a+step
        while pointer<len(intervals) and intervals[pointer][1]<=a: pointer+=1
        if pointer<len(intervals) and intervals[pointer][0]<b:
            if intervals[pointer][0]<=a and b<=intervals[pointer][1]: closed.add(i)
            else: partial.add(i)
    conflicting=present & closed
    missing=set(range(count))-present-closed
    events,excluded,unbounded=classify(m)
    kept,segments,withheld=partition(bars,excluded)
    gaps=_runs(missing,start,step); expected=count-len(closed)
    with localcontext() as context:
        context.prec=32
        pct=format((Decimal(len(missing))*100/expected).quantize(Decimal('0.000001')),'f') if expected else None
    evidence_payload=sorted({encode(c.model_dump(mode='json')) for c in evidence})
    return dict(rule=RULE,dataset_id=data['dataset_id'],provider=m['provider'],instrument=m['instrument'],
                timeframe=m['timeframe'],mapping=m['mapping'],start=start.isoformat(),end=end.isoformat(),
                total_grid_bars=count,total_expected_bars=expected,actual_bars=len(bars),
                expected_closure_bars=len(closed),partial_closure_bars=len(partial),
                closure_conflicting_observation_bars=len(conflicting),
                unexplained_missing_bars=len(missing),unexplained_gap_percentage=pct,
                longest_unexplained_gap_bars=max((g['bars'] for g in gaps),default=0),
                longest_unexplained_gap_seconds=max((g['bars']*seconds for g in gaps),default=0),
                unexplained_gaps=gaps,first_timestamp=bars[0]['opened'] if bars else None,
                last_timestamp=bars[-1]['opened'] if bars else None,last_close=bars[-1]['closed'] if bars else None,
                quality_withheld_bars=withheld,usable_bars=len(kept),unbounded_quality=unbounded,
                longest_usable_segment_bars=max((s['count'] for s in segments),default=0),
                classification_counts=dict(sorted(Counter(e['classification'] for e in events).items())),
                classification_scope='ENTIRE_PINNED_DATASET',
                closures=[json.loads(c) for c in evidence_payload],
                continuity_proven=bool(bars) and not (missing or conflicting or withheld or unbounded),
                qualification_changed=False,
                limitations=['Diagnostic only; not phase or dataset qualification',
                             'No closure exemption without provider/date-specific evidence',
                             'Missing bars include unproven sessions; price flags are separate',
                             'Evidence references/hashes require trusted caller verification'])


class CoverageStore:
    def __init__(self,store):
        self.store=store
        with store.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS p5_coverage(id TEXT PRIMARY KEY,dataset TEXT NOT NULL,payload TEXT NOT NULL,FOREIGN KEY(dataset) REFERENCES datasets(id))')
            c.execute('INSERT OR IGNORE INTO p5_schema VALUES(3)')
            for action in ('UPDATE','DELETE'):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_coverage_{action} BEFORE {action} ON p5_coverage BEGIN SELECT RAISE(ABORT,'Immutable coverage'); END")

    def assess(self,dataset,*,start=None,end=None,closures=()):
        data=self.store.query(dataset,start=start,end=end,research=False)
        report=measure(data,start=start,end=end,closures=closures)
        identity=digest(report)
        with self.store.connect() as c:
            c.execute('INSERT OR IGNORE INTO p5_coverage VALUES(?,?,?)',(identity,dataset,encode(report)))
        return dict(coverage_id=identity,**report)
