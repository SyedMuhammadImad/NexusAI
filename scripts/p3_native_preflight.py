"""Default: metadata only. --attest: explicit operator-only read connection, never send."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.native_operator import operator_file_preflight, native_readonly_preflight

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--attest',action='store_true')
    args=parser.parse_args()
    report=native_readonly_preflight() if args.attest else operator_file_preflight()
    print(json.dumps(report,sort_keys=True))
    raise SystemExit(0 if report['status']=='PASS' else 2)
