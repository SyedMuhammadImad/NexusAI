"""Offline annual raw audit/rebuild; only the dedicated P5 research store is used."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.histdata_audit import inventory
from core.rebuild.market_data import MarketStore, series, resample, digest, encode
from core.rebuild.research_data import ResearchData
from core.rebuild.continuity import CoverageStore


def main():
    store=MarketStore(); view=ResearchData(store); coverage=CoverageStore(store)
    sample=json.loads((store.root/'smoke-report.json').read_text())
    start=datetime(2021,1,1,tzinfo=timezone.utc); end=datetime(2022,1,1,tzinfo=timezone.utc)
    report=dict(instruments={},broker_actions=0,synthetic_observations=0,
                closure_status='UNPROVEN: no provider-specific 2021 session calendar applied')
    for instrument in ('XAUUSD','XAGUSD','USOIL'):
        prior=next(r for r in sample['datasets'] if r['manifest']['instrument']==instrument and r['manifest']['timeframe']=='1M')
        receipt=store.query(prior['dataset_id'],research=False)['provenance'][0]
        provenance=json.loads(receipt['provenance'])
        with store.connect() as c:
            bundle=c.execute('SELECT body FROM raw WHERE id=?',(receipt['raw_id'],)).fetchone()[0]
        length=int.from_bytes(bundle[:8],'big'); raw=bundle[8:]
        if length!=len(raw): raise ValueError('Expected one annual response')
        audit,native,issues=inventory(raw,instrument,2021)
        audit['outside_UTC_year']=sum(not start<=x.opened<end for x in native)
        native,checks,gaps=series([x for x in native if start<=x.opened<end],start,end,'1M')
        audit['canonical_M1']=len(native)
        audit['series_issue_counts']=dict(Counter(x['kind'] for x in checks))
        audit['duplicate_evidence']=[x for x in checks if x['kind'] in {'IDENTICAL_DUPLICATE','CONFLICTING_DUPLICATE','OUT_OF_ORDER'}]
        audit['datasets']=[]
        source_issues=issues+[dict(x,source_timeframe='1M') for x in checks]
        if gaps: source_issues.append(dict(kind='SOURCE_GAPS',gaps=gaps))
        for frame in ('1M','1H','4H'):
            bars,partial=(native,[]) if frame=='1M' else resample(native,frame)
            p=dict(provenance,rebuild='histdata-validity-audit-v2')
            identity=store.save(instrument,frame,start,end,bars,raw=bundle,provenance=p,issues=source_issues+partial)
            assert identity==store.save(instrument,frame,start,end,bars,raw=bundle,provenance=p,issues=source_issues+partial)
            q=view.qualify(identity)
            result=view.query(q['qualification_id'],allow_segments=True)
            assert result==ResearchData(MarketStore()).query(q['qualification_id'],allow_segments=True)
            metrics=[]
            for month in range(13):
                a=start if month==0 else datetime(2021,month,1,tzinfo=timezone.utc)
                b=end if month in (0,12) else datetime(2021,month+1,1,tzinfo=timezone.utc)
                m=coverage.assess(identity,start=a,end=b)
                # No calendar guess is promoted to an expected closure.
                m['calendar_status']='UNPROVEN; missing includes normal closures'
                metrics.append(m)
            item=dict(dataset_id=identity,qualification_id=q['qualification_id'],timeframe=frame,
                      aggregate_bars=len(bars),usable_bars=q['usable_count'],excluded_bars=q['excluded_count'],
                      incomplete_resample_bins=len(partial),state=q['state'],replay=True,restart=True,metrics=metrics)
            audit['datasets'].append(item)
            print(encode(dict(instrument=instrument,timeframe=frame,raw_rows=audit['raw_rows'],
                              bars=len(bars),usable=q['usable_count'],excluded=q['excluded_count'])),flush=True)
        report['instruments'][instrument]=audit
    identity=digest(report)
    path=store.root/f'histdata-audit-{identity}.json'
    if path.exists():
        assert json.loads(path.read_text())==report
    else:
        path.write_text(json.dumps(report,indent=2))
    print(encode(dict(report=str(path),sha256=identity)),flush=True)


if __name__=='__main__': main()
