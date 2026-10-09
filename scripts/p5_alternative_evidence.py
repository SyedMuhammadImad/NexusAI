"""Publish metadata only after querying a common qualified six-series interval."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from core.rebuild.market_data import MarketStore, digest
from core.rebuild.research_reader import ResearchDatasetReader
from core.rebuild.export_research import kronos_rows

parser=argparse.ArgumentParser()
parser.add_argument('report',help='alternative-audit-<sha256>.json basename in owned research root')
args=parser.parse_args()
if not (args.report.startswith('alternative-audit-') and args.report.endswith('.json')
        and Path(args.report).name==args.report): raise ValueError('Audit basename required')
store=MarketStore()
audit=json.loads((store.root/args.report).read_text(encoding='utf-8'))
claimed=audit.pop('report_id')
if digest(audit)!=claimed: raise ValueError('Audit hash mismatch')
qualifications=[q for instrument in audit['instruments'].values() for q in instrument['qualifications']]
assert len(qualifications)==6 and all(q['state']=='QUALIFIED_WITH_KNOWN_LIMITATIONS' for q in qualifications)
intersection=[(datetime.fromisoformat(s['start']),datetime.fromisoformat(s['end'])) for s in qualifications[0]['segments']]
for q in qualifications[1:]:
    ranges=[(datetime.fromisoformat(s['start']),datetime.fromisoformat(s['end'])) for s in q['segments']]
    intersection=[(max(a,c),min(b,d)) for a,b in intersection for c,d in ranges if max(a,c)<min(b,d)]
start,end=max(intersection,key=lambda pair:((pair[1]-pair[0]).total_seconds(),-pair[0].timestamp()))
summary=dict(audit_report_id=claimed,audit_path='research/p5-market-data/'+args.report,
    attribution='EV Trading Labs',provider='EV_TRADING_LABS',upstream='Dukascopy, distributor assertion',
    acquired_start='2021-01-01T00:00:00+00:00',acquired_end_exclusive='2026-01-01T00:00:00+00:00',
    common_qualified_start=start.isoformat(),common_qualified_end_exclusive=end.isoformat(),
    common_calendar_days=(end-start).total_seconds()/86400,datasets=[],cross_provider_checks=[])
reader=ResearchDatasetReader(store)
for symbol, instrument in audit['instruments'].items():
    summary['cross_provider_checks'].append(instrument['comparison'])
    for q in instrument['qualifications']:
        view=reader.query(q['qualification_id'],start=start,end=end)
        assert view==ResearchDatasetReader(MarketStore(store.root)).query(q['qualification_id'],start=start,end=end)
        kline=kronos_rows(view,as_of=end)
        raw=next(r for r in instrument['raw_replay'] if r['dataset_id']==q['dataset_id'])
        summary['datasets'].append(dict(instrument=symbol,timeframe=view['manifest']['timeframe'],
            dataset_id=q['dataset_id'],qualification_id=q['qualification_id'],calendar_id=q['calendar_id'],
            acquisition_bar_count=q['actual_bars'],full_period_expected_bars=q['expected_bars'],
            full_period_known_closure_bars=q['known_closure_bars'],full_period_unexplained_bins=q['unexplained_bars'],
            full_period_longest_unexplained_gap_seconds=q['longest_unexplained_gap_seconds'],
            state=q['state'],qualified_common_bars=len(view['candles']),qualified_common_unexplained_bins=0,
            qualified_common_expected_bars=len(view['candles']),
            qualified_common_closed_bins=int((end-start).total_seconds()/(3600 if view['manifest']['timeframe']=='1H' else 14400))-len(view['candles']),
            kline_row_hash=kline['row_hash'],sources=raw['sources'],price_basis=q['price_basis'],
            mapping=q['mapping'],limitations=q['limitations']))
        print(symbol,view['manifest']['timeframe'],len(view['candles']),flush=True)
summary['evidence_id']=digest(summary)
target=ROOT/'knowledge'/'Audits'/'P5-ALTERNATIVE-DATA-EVIDENCE.json'
target.write_text(json.dumps(summary,indent=2,ensure_ascii=True),encoding='utf-8',newline='\n')
print('COMMON_RANGE',start.isoformat(),end.isoformat(),summary['common_calendar_days'],flush=True)
print(target,flush=True)
