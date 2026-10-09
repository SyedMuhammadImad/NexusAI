"""P8 offline research entry point; run under the documented fixture audit guard."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from core.rebuild.p8_evidence import read_inputs


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args()
    from core.rebuild.p8_research import fingerprint
    database=ROOT/'research/p5-market-data/market-data.sqlite3'
    before=fingerprint(database)
    rows,audit,start,end=read_inputs()
    if fingerprint(database)!=before: raise ValueError('Read-only input audit changed P5 evidence')
    print('P8_INPUT_AUDIT',json.dumps({k:v for k,v in audit.items() if k!='by_instrument_timeframe_strategy'},sort_keys=True),flush=True)
    if not args.audit_only:
        from core.rebuild.p8_research import run_research
        result=run_research(rows,audit,start,end)
        print('P8_RESULT',result['result_id'],flush=True)


if __name__=='__main__': main()
