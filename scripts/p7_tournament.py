"""Offline, pinned P7 tournament. Invoke through the TESTING.md audit guard."""
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from core.rebuild.market_data import MarketStore, digest
from core.rebuild.research_reader import ResearchDatasetReader
from core.rebuild.strategy_research import ResearchData, ResearchLedger
from core.rebuild.tournament import run_tournament, save_tournament


def main():
    evidence=json.loads((ROOT/'knowledge/Audits/P5-ALTERNATIVE-DATA-EVIDENCE.json').read_text(encoding='utf-8'))
    claimed=evidence.pop('evidence_id')
    if digest(evidence)!=claimed: raise ValueError('P5 evidence identity mismatch')
    start=datetime.fromisoformat(evidence['common_qualified_start'])
    end=datetime.fromisoformat(evidence['common_qualified_end_exclusive'])
    if (start.isoformat(),end.isoformat())!=('2025-09-02T00:00:00+00:00','2025-11-27T20:00:00+00:00'):
        raise ValueError('Unapproved study period')
    store=MarketStore(); reader=ResearchDatasetReader(store)
    loaded={(r['instrument'],r['timeframe']):ResearchData.load(reader,r['qualification_id'],
        dataset_id=r['dataset_id'],start=start,end=end) for r in evidence['datasets']}
    result=run_tournament(loaded,ResearchLedger(store))
    save_tournament(store,result)
    save_tournament(store,result)
    with MarketStore().connect() as c:
        persisted=json.loads(c.execute('SELECT payload FROM p7_runs WHERE id=?',(result['run_id'],)).fetchone()[0])
        if persisted!=result: raise ValueError('Tournament restart verification failed')
    target=ROOT/'knowledge/Audits/P7-TOURNAMENT-RESULTS.json'
    temporary=target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result,indent=2,ensure_ascii=True)+'\n',encoding='utf-8',newline='\n')
    temporary.replace(target)
    print('P7_RESULT',result['result_id'],flush=True)
    print('COUNTS',result['counts'],'REPLAYS',result['verified_replays'],flush=True)
    print('SPLIT',result['configuration']['split'],flush=True)


if __name__=='__main__': main()
