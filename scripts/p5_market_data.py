"""Bounded public research-data sync; no application/operator startup."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from core.rebuild.histdata_provider import HistDataProvider, sync
from core.rebuild.market_data import MarketStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--instrument', choices=['XAUUSD', 'XAGUSD', 'USOIL'], required=True)
    parser.add_argument('--timeframe', choices=['1M', '1H', '4H'], required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--parent')
    args = parser.parse_args()
    store = MarketStore()
    identity = sync(store, HistDataProvider(), args.instrument, args.timeframe,
                    datetime.fromisoformat(args.start), datetime.fromisoformat(args.end), parent=args.parent)
    result = store.query(identity, research=False)
    print(json.dumps({'dataset_id': identity, 'manifest': result['manifest']}, indent=2))


if __name__ == '__main__':
    main()
