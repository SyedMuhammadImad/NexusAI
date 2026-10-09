"""Materialize P7 replay evidence under the guarded research-only workflow."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from core.rebuild.market_data import MarketStore, encode
from core.rebuild.strategy_research import ResearchLedger
from core.rebuild.tournament_projection import project


def main():
    result=json.loads((ROOT/'knowledge/Audits/P7-TOURNAMENT-RESULTS.json').read_text(encoding='utf-8'))
    store=MarketStore(); ledger=ResearchLedger(store)
    projection=project(result,ledger)
    if project(result,ledger)!=projection: raise ValueError('Projection is not deterministic')
    target=ROOT/'research/p5-market-data'/('p7-arena-'+projection['projection_id']+'.json')
    payload=encode(projection)
    if target.exists() and target.read_text(encoding='utf-8')!=payload: raise ValueError('Immutable projection conflict')
    if not target.exists():
        temporary=target.with_suffix('.tmp'); temporary.write_text(payload,encoding='utf-8'); temporary.replace(target)
    manifest=dict(filename=target.name,projection_id=projection['projection_id'],result_id=result['result_id'],
                  snapshots=len(projection['timeline']),events=len(projection['events']),bytes=len(payload.encode()))
    for path in (target.parent/'p7-arena-manifest.json',ROOT/'knowledge/Audits/P7-ARENA-MANIFEST.json'):
        temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n'); temp.replace(path)
    print('P7_ARENA',json.dumps(manifest),flush=True)


if __name__=='__main__': main()
