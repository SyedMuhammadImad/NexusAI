"""Reclassify pinned real P5 versions offline; no download/operator dependencies."""
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.market_data import MarketStore, digest, encode
from core.rebuild.sessions import SessionResearch, histdata_2021


def main():
    store=MarketStore(); service=SessionResearch(store)
    prior=json.loads((store.root/'histdata-audit-4bec5e21d18fa89b1dbaaa190ccffb43d60bcb4944ca77ff398be07c75094458.json').read_text())
    reports=[]
    for instrument,a in prior['instruments'].items():
        cal=histdata_2021(instrument)
        for d in a['datasets']:
            q=service.qualify(d['dataset_id'],cal)
            assert q==service.qualify(d['dataset_id'],cal)
            r=q['longest_range']
            if q['state']=='QUALIFIED_SEGMENTS_ONLY' and r:
                start,end=datetime.fromisoformat(r['start']),datetime.fromisoformat(r['end'])
                result=service.query(q['qualification_id'],start=start,end=end)
                assert result==SessionResearch(MarketStore()).query(q['qualification_id'],start=start,end=end)
            q.update(instrument=instrument,timeframe=d['timeframe'])
            reports.append(q)
            print(encode(dict(instrument=instrument,timeframe=d['timeframe'],longest=r,
                              closures=q['expected_closures'],missing=q['unexplained_missing_bars'],
                              conflicts=len(q['calendar_conflicts']))),flush=True)
    identity=digest(reports); filename=f'session-audit-{identity}.json'
    path=store.root/filename
    if path.exists(): assert json.loads(path.read_text())==reports
    else: path.write_text(json.dumps(reports,indent=2),newline='\n')
    lines=['# P5 Session Qualification Audit','','Status: PARTIAL. P6 BLOCKED. Broker execution HARD DISABLED.',
           '',f'Full classified gap intervals: `research/p5-market-data/{filename}`.',
           'Policy: histdata-2021-saturday-core-v1; engine: p5-session-continuity-v1.',
           'Calendar certainty: PARTIAL; Saturday exemptions are explicit market inference.',
           'No calendar conflicts, duplicate ingestion or fabricated candles are permitted.',
           'Reported ranges are longest usable segments, NOT qualified multi-month histories.', '',
           '| Instrument/frame | Start UTC | End UTC | Actual/expected bars in range | Closure bars in range | Annual unknown bars | Annual closure bars |',
           '|---|---|---|---:|---:|---:|---:|']
    for q in reports:
        r=q['longest_range']
        lines.append(f'| {q["instrument"]}/{q["timeframe"]} | {r["start"]} | {r["end"]} | {r["actual_bars"]} | {r["expected_closures"]} | {q["unexplained_missing_bars"]} | {q["expected_closures"]} |')
    lines+=['','Every longest segment above has zero unexplained missing bars. None is multi-month.',
            'Annual unknown counts include unverified daily breaks, weekend edges and holidays.',
            'PROVIDER_GAP is reserved for supported provider-unavailability evidence; no such',
            'assertion is invented from absence alone. All non-exempt real gaps remain UNKNOWN_GAP.',
            'Exact expected closures/gaps, timestamps, counts, policy and dataset IDs are in the hashed JSON.', '',
            '## Exact Boundary Blockers','',
            'First ten non-exempt intervals per aggregate dataset follow; the JSON preserves ALL intervals.',
            'These examples prevent silent cross-gap qualification, not proof of corrupted provider data.','']
    for q in reports:
        if q['timeframe']=='1M': continue
        lines += [f'### {q["instrument"]} {q["timeframe"]}',f'Dataset `{q["dataset_id"]}`; qualification `{q["qualification_id"]}`.','']
        for g in [g for g in q['gaps'] if g['classification'] in {'UNKNOWN_GAP','PROVIDER_GAP'}][:10]:
            lines.append(f'- {g["start"]} to {g["end"]}: {g["classification"]}, {g["bars"]} bars.')
        lines.append('')
    lines+=['## Remaining Work','','Establish applicable daily/edge/holiday evidence, then re-assess these pinned',
            'datasets. Complete-only 4H aggregation still omits partly observed bins; changing',
            'that contract would require explicit session-aware resampling evidence, not fills.',
            'No second provider credentials, strategy, ML or broker action was requested or used.','']
    (Path(__file__).resolve().parents[1]/'knowledge/Audits/P5-SESSION-QUALIFICATION.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    print(encode(dict(report=filename,identity=identity)),flush=True)


if __name__=='__main__': main()
