"""Append-only P5 qualification and gap-aware segmented research views."""
from datetime import datetime, timedelta
import json

from .market_data import INTERVALS, VALIDATOR, digest, encode, utc

RULE = 'p5-observation-validity-v2'


def classify(manifest, closures=()):
    start, end = datetime.fromisoformat(manifest['start']), datetime.fromisoformat(manifest['end'])
    step = INTERVALS[manifest['timeframe']]
    events, unbounded = [], False
    for closure in closures:
        a,b = utc(closure['start']), utc(closure['end'])
        if b<=a or not closure.get('evidence_ref') or closure.get('instrument')!=manifest['instrument']:
            raise ValueError('Invalid evidenced closure')

    def add(kind, a, b, reason):
        a,b = max(start,a), min(end,b)
        if a < b: events.append(dict(classification=kind,start=a.isoformat(),end=b.isoformat(),reason=reason))

    def gap(g):
        a,b = datetime.fromisoformat(g['start']), datetime.fromisoformat(g['end'])
        known = next((c for c in closures if utc(c['start'])<=a and b<=utc(c['end'])),None)
        kind = 'EXPECTED_MARKET_CLOSURE' if known else 'SOURCE_BOUNDARY' if a==start or b==end else 'PROVIDER_GAP'
        add(kind,a,b,known['evidence_ref'] if known else 'Missing provider interval; session cause unproven')

    for g in manifest['gaps']: gap(g)
    for issue in manifest['issues']:
        kind = issue['kind']
        if kind=='SOURCE_GAPS':
            for g in issue['gaps']: gap(g)
        elif kind=='IDENTICAL_DUPLICATE' or kind=='OUT_OF_ORDER':
            # Canonical uniqueness/order has already been verified. Do not exclude resolved duplicates.
            events.append(dict(classification='DUPLICATE/CORRECTION',start=issue['at'],end=issue['at'],reason=kind))
        elif kind == 'DISJOINT_ADJACENT_PRICE_RANGES':
            # Adjacent valid OHLC ranges need not overlap. Preserve evidence, not an exclusion.
            events.append(dict(classification='PRICE_GAP_OBSERVATION',start=issue['at'],
                               end=issue['at'],reason=kind))
        elif kind in {'INCOMPLETE_RESAMPLE','CONFLICTING_DUPLICATE'}:
            a = datetime.fromisoformat(issue['at'])
            span = INTERVALS.get(issue.get('source_timeframe'),step)
            category = {'DISJOINT_ADJACENT_PRICE_RANGES':'UNKNOWN', 'INCOMPLETE_RESAMPLE':'RESAMPLING_BOUNDARY',
                        'CONFLICTING_DUPLICATE':'DUPLICATE/CORRECTION'}[kind]
            add(category,a-timedelta(seconds=span) if kind=='DISJOINT_ADJACENT_PRICE_RANGES' else a,
                a+timedelta(seconds=span),kind)
        else:
            unbounded=True
            events.append(dict(classification='CORRUPT_OBSERVATION' if kind=='MALFORMED_NATIVE_ROW' else 'UNKNOWN',
                               start=start.isoformat(),end=end.isoformat(),reason=kind))
    events=[json.loads(x) for x in sorted({encode(e) for e in events})]
    intervals=[]
    for e in sorted(events,key=lambda x:x['start']):
        a,b=datetime.fromisoformat(e['start']),datetime.fromisoformat(e['end'])
        if a==b: continue
        if intervals and a<=intervals[-1][1]: intervals[-1][1]=max(b,intervals[-1][1])
        else: intervals.append([a,b])
    return events, intervals, unbounded


def partition(candles, intervals):
    accepted, segments, excluded = [], [], 0
    pointer=0
    for c in candles:
        a,b=datetime.fromisoformat(c['opened']),datetime.fromisoformat(c['closed'])
        while pointer<len(intervals) and intervals[pointer][1]<=a: pointer+=1
        if pointer<len(intervals) and intervals[pointer][0]<b:
            excluded+=1
            continue
        if not segments or datetime.fromisoformat(segments[-1]['end'])!=a:
            segments.append(dict(start=a.isoformat(),end=b.isoformat(),count=1))
        else:
            segments[-1]['end']=b.isoformat(); segments[-1]['count']+=1
        accepted.append(c)
    return accepted,segments,excluded


class ResearchData:
    def __init__(self,store):
        self.store=store
        with store.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS p5_qualification(id TEXT PRIMARY KEY,dataset TEXT NOT NULL,payload TEXT NOT NULL,FOREIGN KEY(dataset) REFERENCES datasets(id))')
            c.execute('INSERT OR IGNORE INTO p5_schema VALUES(2)')
            for operation in ('UPDATE','DELETE'):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_qualification_{operation} BEFORE {operation} ON p5_qualification BEGIN SELECT RAISE(ABORT,'Immutable qualification'); END")

    def qualify(self,dataset,*,closures=()):
        result=self.store.query(dataset,research=False)
        m=result['manifest']
        events,intervals,unbounded=classify(m,closures)
        bars,segments,excluded=partition(result['candles'],intervals)
        receipts=[json.loads(r['provenance']) for r in result['provenance']]
        known=bool(receipts) and all(p.get('responses') and not p.get('fixture',True) and all(
            x.get('provider')=='HISTDATA' and x.get('adapter') and x.get('price_side')=='BID'
            and x.get('url','').startswith('https://www.histdata.com/') and not x.get('fixture',True)
            for x in p['responses']) for p in receipts)
        state = 'REJECTED' if not m['real_data'] or not known else 'REVIEW_REQUIRED' if (
            unbounded or not bars or m['validation']!=VALIDATOR) else 'QUALIFIED_WITH_KNOWN_LIMITATIONS'
        report=dict(dataset_id=dataset,rule=RULE,validation=VALIDATOR,state=state,events=events,
                    usable_count=len(bars),excluded_count=excluded,segments=segments,
                    limitations=['Research proxy; not broker-equivalent','Bid-only; volume/spread unavailable',
                                 'Do not bridge excluded intervals; use segment boundaries'],
                    content_hash=digest(bars))
        identity=digest(report)
        with self.store.connect() as c:
            c.execute('INSERT OR IGNORE INTO p5_qualification VALUES(?,?,?)',(identity,dataset,encode(report)))
        return dict(qualification_id=identity,**report)

    def query(self,qualification_id,*,start=None,end=None,allow_segments=False):
        with self.store.connect() as c:
            row=c.execute('SELECT payload FROM p5_qualification WHERE id=?',(qualification_id,)).fetchone()
        if not row: raise ValueError('Unknown qualification version')
        q=json.loads(row[0])
        if q['rule']!=RULE or q['validation']!=VALIDATOR or not q['state'].startswith('QUALIFIED'):
            raise ValueError('Dataset qualification unavailable')
        data=self.store.query(q['dataset_id'],start=start,end=end,research=False)
        intervals=[]
        for e in sorted(q['events'],key=lambda x:x['start']):
            a,b=datetime.fromisoformat(e['start']),datetime.fromisoformat(e['end'])
            if a<b:
                if intervals and a<=intervals[-1][1]: intervals[-1][1]=max(b,intervals[-1][1])
                else: intervals.append([a,b])
        bars,segments,excluded=partition(data['candles'],intervals)
        a=utc(start) if start else datetime.fromisoformat(data['manifest']['start'])
        b=utc(end) if end else datetime.fromisoformat(data['manifest']['end'])
        if not bars or not allow_segments and (len(segments)!=1 or datetime.fromisoformat(segments[0]['start'])!=a or datetime.fromisoformat(segments[0]['end'])!=b):
            raise ValueError('Requested contiguous range includes excluded/missing observations')
        return dict(data, candles=bars,qualification=q,qualification_id=qualification_id,
                    requested_range=dict(start=a.isoformat(),end=b.isoformat()),segments=segments,excluded_count=excluded)
