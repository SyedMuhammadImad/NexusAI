"""Read-only dataset inspection; writes a public-data report in the P5 research root."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.market_data import MarketStore
from core.rebuild.research_data import ResearchData


def main():
    store=MarketStore(); view=ResearchData(store)
    report=json.loads((store.root/'closeout-report.json').read_text())
    pairs=[]; ranges=[]
    for row in report['original_nine']:
        if row['timeframe']!='1M': continue
        data=store.query(row['dataset_id'],research=False)
        bars={datetime.fromisoformat(x['opened']):x for x in data['candles']}
        for issue in data['manifest']['issues']:
            if issue['kind']!='DISJOINT_ADJACENT_PRICE_RANGES': continue
            at=datetime.fromisoformat(issue['at'])
            pair=[bars[at-timedelta(minutes=1)],bars[at]]
            pairs.append(dict(instrument=row['instrument'],at=at.isoformat(),classification='UNKNOWN',
                              reason='Adjacent minute high/low ranges do not overlap; cause not independently verified',
                              candles=pair))
    for row in report['annual']:
        identity=row['qualification_id']; all_data=view.query(identity,allow_segments=True)
        longest=max(x['count'] for x in all_data['segments'])
        queries=[]
        for a,b in [('2021-07-01','2021-07-04'),('2021-07-01','2021-10-01')]:
            start=datetime.fromisoformat(a+'T00:00:00+00:00'); end=datetime.fromisoformat(b+'T00:00:00+00:00')
            try:
                result=view.query(identity,start=start,end=end,allow_segments=True)
                assert result==view.query(identity,start=start,end=end,allow_segments=True)
                status='SEGMENTED_ACCEPTANCE'; count=len(result['candles'])
            except ValueError:
                status='REJECTED_NO_USABLE_BARS'; count=0
            try:
                view.query(identity,start=start,end=end)
                contiguous='ACCEPTED'
            except ValueError:
                contiguous='REJECTED_GAPS'
            queries.append(dict(start=a,end=b,segmented=status,count=count,contiguous=contiguous))
        ranges.append(dict(instrument=row['instrument'],timeframe=row['timeframe'],dataset_id=row['dataset_id'],
                           longest_contiguous_bars=longest,queries=queries))
    output=dict(original_disjoint_pairs=pairs,range_checks=ranges,broker_actions=0)
    (store.root/'closeout-inspection.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))


if __name__=='__main__': main()
