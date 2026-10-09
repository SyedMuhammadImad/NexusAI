"""Measure preserved public P5 datasets without fetching data or changing qualification."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.market_data import MarketStore, digest
from core.rebuild.continuity import CoverageStore


def main():
    store=MarketStore(); service=CoverageStore(store)
    source=json.loads((store.root/'closeout-report.json').read_text())
    identities=sorted({row['dataset_id'] for group in ('original_nine','annual') for row in source[group]})
    reports=[]
    for identity in identities:
        before=store.query(identity,research=False)
        report=service.assess(identity)
        assert report==service.assess(identity)
        assert report==CoverageStore(MarketStore()).assess(identity)
        assert store.query(identity,research=False)==before
        reports.append(report)
        print(json.dumps({k:v for k,v in report.items() if k not in {'unexplained_gaps','closures','limitations'}}),flush=True)
    payload={'reports':reports,'broker_actions':0,'network_requests':0,'qualification_changes':0}
    payload['report_id']=digest(payload)
    (store.root/'continuity-report.json').write_text(json.dumps(payload,indent=2))


if __name__=='__main__': main()
