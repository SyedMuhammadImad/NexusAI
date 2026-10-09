"""Descriptive comparison of independent same-instrument hourly provider series."""
from datetime import datetime, timedelta
from statistics import correlation, median


def compare(left,right):
    a,b=left['manifest'],right['manifest']
    if a['instrument']!=b['instrument'] or a['timeframe']!=b['timeframe'] or a['provider']==b['provider']:
        raise ValueError('Distinct comparable providers required')
    if a['timeframe']!='1H': raise ValueError('Hourly comparison only')
    def values(data):
        return {datetime.fromisoformat(c['opened']):float(c['close']) for c in data['candles']}
    x,y=values(left),values(right); times=sorted(x.keys() & y.keys())
    if len(times)<3: raise ValueError('Insufficient paired observations')
    offsets=[(x[t]-y[t])/y[t] for t in times]
    returns=[(x[t]/x[t-timedelta(hours=1)]-1,y[t]/y[t-timedelta(hours=1)]-1)
             for t in times if t-timedelta(hours=1) in x and t-timedelta(hours=1) in y]
    def corr(xs,ys):
        return correlation(xs,ys) if len(xs)>1 and len(set(xs))>1 and len(set(ys))>1 else None
    ranked=sorted(zip(times,offsets),key=lambda v:abs(v[1]),reverse=True)
    lag_diagnostics={}
    for season, months in (('JAN_FEB_DEC',{1,2,12}),('APR_OCT',set(range(4,11)))):
        lag_diagnostics[season]={}
        for lag in (-2,-1,0,1,2):
            pairs=[]
            delta=timedelta(hours=lag); hour=timedelta(hours=1)
            for t in x:
                s=t+delta
                if t.month in months and t-hour in x and s in y and s-hour in y:
                    pairs.append((x[t]/x[t-hour]-1,y[s]/y[s-hour]-1))
            lag_diagnostics[season][str(lag)]=dict(pairs=len(pairs),
                correlation=corr([p[0] for p in pairs],[p[1] for p in pairs]))
    return dict(left_dataset=left['dataset_id'],right_dataset=right['dataset_id'],
        left_provider=a['provider'],right_provider=b['provider'],instrument=a['instrument'],
        paired_bars=len(times),first=times[0].isoformat(),last=times[-1].isoformat(),price_basis='BID_CLOSE',
        price_correlation=corr([x[t] for t in times],[y[t] for t in times]),
        hourly_return_pairs=len(returns),hourly_return_correlation=corr([r[0] for r in returns],[r[1] for r in returns]),
        median_relative_offset=median(offsets),median_absolute_relative_offset=median(abs(v) for v in offsets),
        largest_offsets=[dict(at=t.isoformat(),relative_offset=v,left=x[t],right=y[t]) for t,v in ranked[:10]],
        diagnostic_histdata_timestamp_offset_hours=lag_diagnostics,
        equivalent_contract_proven=False,data_modified=False)
