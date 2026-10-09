"""Explicit public-network smoke, separate from fixture test discovery."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from core.rebuild.histdata_provider import HistDataProvider, sync
from core.rebuild.market_data import MarketStore


class BoundedProvider(HistDataProvider):
    def __init__(self):
        self.cache = {}
        self.normalized = {}
    def download(self, instrument, year, month):
        key = (instrument, year, month)
        if key not in self.cache:
            self.cache[key] = super().download(*key)
        return self.cache[key]

    def normalize(self, raw, instrument, year, month):
        key = (hashlib.sha256(raw).hexdigest(), instrument, year, month)
        if key not in self.normalized:
            self.normalized[key] = super().normalize(raw, instrument, year, month)
        return self.normalized[key]


def main():
    store, provider = MarketStore(), BoundedProvider()
    start = datetime(2021, 1, 4, 12, tzinfo=timezone.utc)
    end = start + timedelta(hours=8)
    results = []
    for instrument in ('XAUUSD', 'XAGUSD', 'USOIL'):
        for timeframe in ('1M', '1H', '4H'):
            identity = sync(store, provider, instrument, timeframe, start, end)
            assert sync(store, provider, instrument, timeframe, start, end) == identity
            result = store.query(identity, research=False)
            manifest = result['manifest']
            reopened = MarketStore().query(identity, research=False)
            assert result == reopened
            accepted = False
            try:
                store.query(identity)
                accepted = True
            except ValueError:
                pass
            results.append(dict(dataset_id=identity, manifest=manifest, replay=True,
                                restart=True, research_query_accepted=accepted))
    report = dict(start=start.isoformat(), end=end.isoformat(), datasets=results,
                  downloads=[dict(instrument=k[0], month=f'{k[1]}-{k[2]:02d}',
                                  bytes=len(v[0]), sha256=hashlib.sha256(v[0]).hexdigest()) for k,v in provider.cache.items()],
                  broker_actions=0)
    (store.root/'smoke-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    for row in results:
        m=row['manifest']
        print(json.dumps(dict(instrument=m['instrument'], timeframe=m['timeframe'], dataset_id=row['dataset_id'],
                              count=m['bar_count'], status=m['status'], gaps=len(m['gaps']), issues=len(m['issues']),
                              replay=True, restart=True, research_query_accepted=row['research_query_accepted'])))


if __name__ == '__main__': main()
