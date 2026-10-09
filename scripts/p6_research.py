"""Offline P6 fixed-parameter study. Run only through knowledge/TESTING.md guard."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from core.rebuild.market_data import MarketStore, digest, encode
from core.rebuild.research_reader import ResearchDatasetReader
from core.rebuild.research_strategies import catalogue
from core.rebuild.strategy_research import ResearchData, ResearchLedger, replay


def main():
    evidence = json.loads((ROOT/'knowledge/Audits/P5-ALTERNATIVE-DATA-EVIDENCE.json').read_text(encoding='utf-8'))
    claimed = evidence.pop('evidence_id')
    if digest(evidence) != claimed:
        raise ValueError('P5 evidence identity mismatch')
    start = datetime.fromisoformat(evidence['common_qualified_start'])
    end = datetime.fromisoformat(evidence['common_qualified_end_exclusive'])
    split = datetime.fromisoformat('2025-10-15T00:00:00+00:00')
    store = MarketStore()
    reader, ledger = ResearchDatasetReader(store), ResearchLedger(store)
    loaded = {}
    for item in evidence['datasets']:
        loaded[item['instrument'],item['timeframe']] = ResearchData.load(reader,item['qualification_id'],
            dataset_id=item['dataset_id'],start=start,end=end)
    runs, identical = [], 0
    for (symbol,timeframe), data in loaded.items():
        lower = loaded[symbol,'1H'] if timeframe == '4H' else None
        for strategy in catalogue():
            for period, a, b in (('IN_SAMPLE',start,split),('OUT_OF_SAMPLE',split,end)):
                result = replay(data,strategy,start=a,end=b,lower=lower)
                # Recompute, not just re-read an already saved result.
                repeated = replay(data,strategy,start=a,end=b,lower=lower)
                if result != repeated: raise ValueError('Nondeterministic replay')
                ledger.save(result)
                if ResearchLedger(MarketStore()).read(result['run_id']) != result:
                    raise ValueError('Restart/read mismatch')
                identical += 1
                eligibility = strategy.eligibility if timeframe in strategy.timeframes else 'INSUFFICIENT_DATA'
                runs.append(dict(run_id=result['run_id'],artifact_id=result['artifact_id'], strategy_id=strategy.strategy_id,
                                 instrument=symbol,timeframe=timeframe,period=period,eligibility=eligibility,
                                 metrics=result['metrics']))
        print('P6_REPLAY',symbol,timeframe,'COMPLETE',flush=True)
    summary = dict(version='p6-study-v1', p5_evidence_id=claimed, start=start.isoformat(),split=split.isoformat(),end=end.isoformat(),
                   datasets=[d.identity() for d in loaded.values()], catalogue=[asdict(s) for s in catalogue()],
                   deterministic_replays=identical, runs=runs, broker_execution='HARD_DISABLED',
                   tuning='NONE; one versioned parameter set, no selection or profitability qualification',
                   limitations=['Commission excluded because unknown','Not account PnL','Short retrospective qualified sample',
                                'WTI proxy mapping limitation','P7 ranking/minimum sample policy remains ADR-006 deferred'])
    summary['report_id'] = digest(summary)
    target = ROOT/'knowledge/Audits/P6-RESEARCH-RESULTS.json'
    target.write_text(json.dumps(summary,indent=2,ensure_ascii=True),encoding='utf-8',newline='\n')
    print('REPORT',summary['report_id'],flush=True)
    print('RUNS',len(runs),'TRADES',sum(r['metrics']['research_trade_count'] for r in runs),flush=True)
    print('ELIGIBILITY',dict(Counter(s.eligibility for s in catalogue())),flush=True)


if __name__ == '__main__':
    main()
