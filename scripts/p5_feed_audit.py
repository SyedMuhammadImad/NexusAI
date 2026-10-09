"""Derive and verify empirical calendars using only the owned P5 research store."""
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.market_data import MarketStore, digest, encode
from core.rebuild.feed_calendar import FeedResearch, derive, exceptions, minute, closed_minutes, runs


def main():
    store=MarketStore(); service=FeedResearch(store)
    prior=json.loads((store.root/'histdata-audit-4bec5e21d18fa89b1dbaaa190ccffb43d60bcb4944ca77ff398be07c75094458.json').read_text())
    models={}; days={}; sources={}
    for instrument,a in prior['instruments'].items():
        source=next(d['dataset_id'] for d in a['datasets'] if d['timeframe']=='1M'); sources[instrument]=source
        data=store.query(source,research=False)
        models[instrument]=derive(data)
        assert models[instrument]==derive(data)
        days[instrument]={minute(c['opened'])//1440 for c in data['candles']}
        print(encode(dict(instrument=instrument,closed_weekly_minutes=len(models[instrument]['recurring_closed_slots']),
                          weeks=len(models[instrument]['comparable_weeks']),quarters=models[instrument]['weeks_per_quarter'],
                          quarter_closed_minutes={q:len(s) for q,s in models[instrument]['quarterly_closed_slots'].items()})),flush=True)
        del data
    models=exceptions(models,days); results=[]; missing={}
    for instrument,model in models.items():
        data=store.query(sources[instrument],research=False)
        observed={minute(c['opened']) for c in data['candles']}
        missing[instrument]=runs(set(range(minute(model['start']),minute(model['end'])))-closed_minutes(model)-observed,'UNKNOWN_GAP')
        receipt=data['provenance'][0]; provenance=json.loads(receipt['provenance'])
        with store.connect() as c: raw=c.execute('SELECT body FROM raw WHERE id=?',(receipt['raw_id'],)).fetchone()[0]
        for frame in ('1H','4H'):
            q=service.rebuild(data,model,frame,raw,provenance)
            assert q==service.rebuild(data,model,frame,raw,provenance)
            r=q['longest_range']
            if r:
                start,end=datetime.fromisoformat(r['start']),datetime.fromisoformat(r['end'])
                assert service.query(q['qualification_id'],start,end)==FeedResearch(MarketStore()).query(q['qualification_id'],start,end)
            results.append(dict(q,instrument=instrument,timeframe=frame))
            print(encode(dict(instrument=instrument,timeframe=frame,longest=r,unknown_bars=q['unknown_bars'],unknown_minutes=q['unknown_minutes'],actual=q['actual_bars'])),flush=True)
        del data
    report=dict(models=models,qualifications=results,unresolved_source_minutes=missing,broker_actions=0)
    identity=digest(report); filename=f'feed-audit-{identity}.json'; path=store.root/filename
    if path.exists(): assert json.loads(path.read_text())==json.loads(encode(report))
    else: path.write_text(json.dumps(report,indent=2),newline='\n')
    lines=['# P5 Empirical Feed Calendar Audit','','Policy: HISTDATA_FEED_CALENDAR_2021_V1. Research only; execution HARD DISABLED.',
           'Derivation is retrospective. No official exchange/broker hours are inferred.',
           f'Complete models, confidence arrays, exceptions and residual intervals: `research/p5-market-data/{filename}`.','',
           '| Instrument | Comparable weeks | Weekly closed minute slots | Special days | Residual M1 minutes |',
           '|---|---:|---:|---|---:|']
    for i,m in models.items():
        lines.append(f'| {i} | {len(m["comparable_weeks"])} | {len(m["recurring_closed_slots"])} | {", ".join(e["start"][:10] for e in m["exceptions"])} | {sum(g["missing_minutes"] for g in missing[i])} |')
    lines+=['','## Longest Strictly Continuous Ranges','',
            'These ranges cross expected feed closures, never UNKNOWN_GAP. Range unknown count is zero.',
            'Expected M1 completeness is 100%; fully closed bins emit no candle.', '',
            '| Instrument/frame | Start UTC | End UTC | Actual range bars | Range closure bins | Annual unknown bins |',
            '|---|---|---|---:|---:|---:|']
    for q in results:
        r=q['longest_range']
        lines.append(f'| {q["instrument"]}/{q["timeframe"]} | {r["start"]} | {r["end"]} | {r["actual_bars"]} | {r["closure_bars"]} | {q["unknown_bars"]} |')
    lines+=['','## Identity and Residual Examples','']
    for q in results:
        lines += [f'### {q["instrument"]} {q["timeframe"]}',f'Dataset `{q["dataset_id"]}`; calendar `{q["calendar_id"]}`;',
                  f'qualification `{q["qualification_id"]}`.','',
                  'First ten unresolved aggregate intervals (all intervals and source M1 gaps are in the hashed JSON):']
        for g in q['unresolved_gaps'][:10]: lines.append(f'- {g["start"]} to {g["end"]}: {g["missing_minutes"]}/{g["expected_minutes"]} expected minutes missing.')
        lines.append('')
    lines+=['## Verification Scope','','Repeated derivation, re-ingestion and reopen/query equality passed for every instrument/frame.',
            'Source versions and old datasets are preserved. No synthetic repair or broker action.',
            'Full-day shared absence is descriptive, not official holiday attribution. Irregular and',
            'partial-day gaps remain UNKNOWN. See TESTING.md for fixture regression results.','']
    (Path(__file__).resolve().parents[1]/'knowledge/Audits/P5-EMPIRICAL-FEED-CALENDAR.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    print(encode(dict(report=filename,identity=identity)),flush=True)


if __name__=='__main__': main()
