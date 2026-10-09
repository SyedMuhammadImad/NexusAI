"""Reproduce annual P5 datasets from previously downloaded, hashed public archives."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.market_data import Candle, MarketStore, resample, series
from core.rebuild.histdata_provider import HistDataProvider
from core.rebuild.research_data import ResearchData


def main():
    store=MarketStore(); view=ResearchData(store)
    sample=json.loads((store.root/'smoke-report.json').read_text())
    old=[]
    for row in sample['datasets']:
        q=view.qualify(row['dataset_id'])
        record=store.query(row['dataset_id'],research=False)
        old.append(dict(dataset_id=row['dataset_id'],instrument=record['manifest']['instrument'],
                        timeframe=record['manifest']['timeframe'],classification=q['events']))
    output=[]
    start=datetime(2021,1,1,tzinfo=timezone.utc); end=datetime(2022,1,1,tzinfo=timezone.utc)
    for instrument in ('XAUUSD','XAGUSD','USOIL'):
        prior=next(r for r in sample['datasets'] if r['manifest']['instrument']==instrument and r['manifest']['timeframe']=='1M')
        receipt=store.query(prior['dataset_id'],research=False)['provenance'][0]
        provenance=json.loads(receipt['provenance'])
        with store.connect() as c:
            bundle=c.execute('SELECT body FROM raw WHERE id=?',(receipt['raw_id'],)).fetchone()[0]
        length=int.from_bytes(bundle[:8],'big'); raw=bundle[8:8+length]
        if length!=len(raw) or len(bundle)!=length+8: raise ValueError('Expected single preserved annual response')
        native,issues=HistDataProvider().normalize(raw,instrument,2021,None)
        native=[x for x in native if start<=x.opened<end]
        native,checks,gaps=series(native,start,end,'1M')
        issues.extend(dict(x,source_timeframe='1M') for x in checks)
        if gaps: issues.append(dict(kind='SOURCE_GAPS',gaps=gaps))
        for frame in ('1H','4H'):
            bars,partial=resample(native,frame)
            identity=store.save(instrument,frame,start,end,bars,raw=bundle,provenance=provenance,issues=issues+partial)
            assert store.save(instrument,frame,start,end,bars,raw=bundle,provenance=provenance,issues=issues+partial)==identity
            q=view.qualify(identity)
            result=view.query(q['qualification_id'],allow_segments=True)
            assert view.query(q['qualification_id'],allow_segments=True)==result
            assert ResearchData(MarketStore()).query(q['qualification_id'],allow_segments=True)==result
            first=datetime.fromisoformat(result['candles'][0]['opened']); last=datetime.fromisoformat(result['candles'][-1]['closed'])
            months=sorted({x['opened'][:7] for x in result['candles']})
            output.append(dict(instrument=instrument,timeframe=frame,dataset_id=identity,qualification_id=q['qualification_id'],
                state=q['state'],requested_start=start.isoformat(),requested_end=end.isoformat(),
                first_usable=first.isoformat(),last_usable_close=last.isoformat(),months=months,
                source_bars=len(native),aggregate_bars=len(bars),usable_bars=len(result['candles']),
                excluded_bars=q['excluded_count'],segments=len(result['segments']),
                classifications={name:sum(e['classification']==name for e in q['events']) for name in sorted({e['classification'] for e in q['events']})},
                raw_sha256=hashlib.sha256(raw).hexdigest(),replay=True,restart=True))
            print(json.dumps(output[-1]),flush=True)
    report=dict(original_nine=old,annual=output,broker_actions=0)
    (store.root/'closeout-report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__': main()
