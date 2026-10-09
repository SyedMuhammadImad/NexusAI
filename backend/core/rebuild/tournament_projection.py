"""Bounded, immutable P7 observation projection; no browser-owned gate logic."""
from datetime import datetime, timedelta
from decimal import Decimal as D, localcontext
from functools import lru_cache
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from .market_data import digest, encode
from .strategy_research import Costs, metrics
from .tournament import assess, WARNING

VERSION='p7-arena-v1'
ROOT=Path(__file__).resolve().parents[3]


def compact(m):
    return {k:m[k] for k in ('research_trade_count','resolved_barrier_denominator','outcomes','win_rate',
        'expectancy_r','total_r','max_drawdown_r','profit_factor','excluded_outcome_rate','priced_denominator')}


def checked(report):
    if digest({k:v for k,v in report.items() if k!='result_id'})!=report['result_id']:
        raise ValueError('P7 result integrity failure')
    return report


def project(result, ledger):
    checked(result)
    config=result['configuration']; start=datetime.fromisoformat(config['start'])
    end=datetime.fromisoformat(config['end']); split=datetime.fromisoformat(config['split'])
    times={start,end,split}; t=start
    while t<end:
        times.add(t); t+=timedelta(days=1)
    timeline=sorted(times)
    if len(timeline)>128: raise ValueError('Projection exceeds bounded P7 period')
    strategies={s['strategy_id']:s for s in config['catalogue'] if s['eligibility']=='TOURNAMENT_READY'}
    views={}; events=[]
    events.append(dict(at=split.isoformat(),type='OOS_START',text='OUT-OF-SAMPLE; canonical parameters remain frozen',cell_id=None))
    with localcontext() as ctx:
        ctx.prec=40
        for cell in result['cells']:
            sid=cell['strategy_id']
            if sid not in strategies: continue
            view=views.setdefault(cell['instrument']+':'+cell['timeframe'],dict(snapshots=[[] for _ in timeline],cells={}))
            view['cells'][cell['cell_id']]=cell
            reports={}
            if cell['status']!='EXCLUDED':
                for period in ('development','oos'):
                    ref=cell['replays'][period]; r=ledger.read(ref['run_id'])
                    if r['artifact_id']!=ref['artifact_id']: raise ValueError('P7 replay reference mismatch')
                    reports[period]=r
                    for trade in r['trades']:
                        events.append(dict(at=trade['entry_at'],type='TRADE_OPEN',cell_id=cell['cell_id'],
                            trade_id=trade['research_trade_id'],text=f"{strategies[sid]['name']} {cell['instrument']} {cell['timeframe']} opened {trade['signal']['direction']} research trade"))
                        at=trade.get('exit_timestamp') or trade.get('exit_interval_end') or r['configuration']['end']
                        events.append(dict(at=at,type='TRADE_OUTCOME',cell_id=cell['cell_id'],trade_id=trade['research_trade_id'],
                            outcome=trade['outcome'],r_multiple=trade.get('r_multiple'),
                            text=f"{strategies[sid]['name']} {cell['instrument']} {cell['timeframe']} {trade['outcome']} {trade.get('r_multiple') or 'unpriced'} R (research evidence)"))
            previous={}
            for index,at in enumerate(timeline):
                if not reports:
                    row=dict(cell_id=cell['cell_id'],strategy_id=sid,status='EXCLUDED',reason=cell['reason'],metrics=None,gates={})
                else:
                    closed={}; signals={}; opened=0
                    for period,r in reports.items():
                        closed[period]=[tr for tr in r['trades'] if datetime.fromisoformat(tr.get('exit_timestamp') or tr.get('exit_interval_end') or r['configuration']['end'])<=at]
                        signals[period]=[s for s in r['signals'] if datetime.fromisoformat(s['signal_timestamp'])<=at]
                        opened+=sum(datetime.fromisoformat(tr['entry_at'])<=at for tr in r['trades'])
                    dev=metrics(closed['development'],signals['development'],Costs())
                    oos=metrics(closed['oos'],signals['oos'],Costs())
                    combined=metrics(closed['development']+closed['oos'],signals['development']+signals['oos'],Costs())
                    if at==end:
                        if dev!=cell['development'] or oos!=cell['oos']: raise ValueError('Final snapshot diverges from P7 metrics')
                        status=cell['status']; gates=cell['gates']
                    else:
                        gates=assess(dev,oos,data_quality=True,leakage=True,cost_assumption=True)['gates']
                        gates=json.loads(encode(gates))
                        for name,g in gates.items():
                            if at<=split and name not in {'DATA_QUALITY','LEAKAGE','COST_ASSUMPTION'} or g['status']=='UNKNOWN' or name=='SAMPLE':
                                g['status']='PENDING'
                        status='AT_RISK' if any(g['status']=='FAIL' for g in gates.values()) else 'ACTIVE'
                    reasons=['FAILED_'+name+'_GATE' for name,g in gates.items() if g['status']=='FAIL']
                    if status=='INSUFFICIENT_EVIDENCE' and not reasons: reasons=['INSUFFICIENT_METRIC_EVIDENCE']
                    row=dict(cell_id=cell['cell_id'],strategy_id=sid,status=status,metrics=compact(combined),
                             development=compact(dev),oos=compact(oos),opened_trades=opened,open_trades=opened-len(closed['development'])-len(closed['oos']),
                             gates=gates,reasons=reasons)
                    for name,g in gates.items():
                        if name in previous and previous[name]!=g['status']:
                            events.append(dict(at=at.isoformat(),type='GATE_TRANSITION',cell_id=cell['cell_id'],
                                text=f"{strategies[sid]['name']} {name}: {previous[name]} -> {g['status']}"))
                    if at==end:
                        events.append(dict(at=at.isoformat(),type='FINAL_STATUS',cell_id=cell['cell_id'],
                            text=f"{strategies[sid]['name']} {status}: {', '.join(reasons) or 'all gates pass'}"))
                    previous={k:g['status'] for k,g in gates.items()}
                view['snapshots'][index].append(row)
        for view in views.values():
            for rows in view['snapshots']:
                rows.sort(key=lambda r:(-D(r['metrics']['total_r']) if r['metrics'] else D(0),r['strategy_id']))
    events.sort(key=lambda e:(datetime.fromisoformat(e['at']),e['type'],e.get('cell_id') or '',e.get('trade_id') or '',e['text']))
    for e in events: e['event_id']=digest(e)
    out=dict(version=VERSION,result_id=result['result_id'],run_id=result['run_id'],configuration=config,
        timeline=[t.isoformat() for t in timeline],strategies=strategies,views=views,events=events,
        final_counts=result['counts'],correlation=result['correlation'],warning=WARNING,execution='HARD_DISABLED')
    out['projection_id']=digest(out)
    return out


@lru_cache(maxsize=2)
def _load(manifest_path, stamp):
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    path=Path(manifest_path).parent/manifest['filename']
    if path.name!=manifest['filename'] or path.resolve().parent!=Path(manifest_path).resolve().parent:
        raise ValueError('Invalid projection reference')
    if path.stat().st_size>64*1024*1024: raise ValueError('Oversized projection')
    data=json.loads(path.read_text(encoding='utf-8'))
    if digest({k:v for k,v in data.items() if k!='projection_id'})!=data['projection_id'] or data['projection_id']!=manifest['projection_id']:
        raise ValueError('Projection integrity failure')
    if data['result_id']!=manifest['result_id']: raise ValueError('Result binding mismatch')
    return data


class TournamentReader:
    def __init__(self, manifest=None):
        self.manifest=Path(manifest) if manifest else ROOT/'research/p5-market-data/p7-arena-manifest.json'

    def read(self):
        data=_load(str(self.manifest),self.manifest.stat().st_mtime_ns)
        if self.manifest==ROOT/'research/p5-market-data/p7-arena-manifest.json':
            source=checked(json.loads((ROOT/'knowledge/Audits/P7-TOURNAMENT-RESULTS.json').read_text(encoding='utf-8')))
            if source['result_id']!=data['result_id']: raise ValueError('Projection is stale')
        return data


def tournament_router(access, reader=None):
    router=APIRouter(prefix='/api/core/tournament',dependencies=[Depends(access)]); reader=reader or TournamentReader()
    def load():
        try: return reader.read()
        except (OSError,ValueError,KeyError): raise HTTPException(503,'Verified tournament evidence unavailable') from None

    @router.get('/summary')
    def summary():
        d=load()
        return {k:d[k] for k in ('version','projection_id','result_id','run_id','configuration','timeline','strategies','final_counts','warning','execution')}

    @router.get('/snapshot')
    def snapshot(index:int=Query(0,ge=0,le=127),instrument:str=Query('XAGUSD',pattern='^(XAUUSD|XAGUSD|USOIL)$'),timeframe:str=Query('1H',pattern='^(1H|4H)$')):
        d=load(); key=instrument+':'+timeframe
        if index>=len(d['timeline']): raise HTTPException(422,'Snapshot outside timeline')
        rows=d['views'][key]['snapshots'][index]; at=d['timeline'][index]
        events=[e for e in d['events'] if datetime.fromisoformat(e['at'])<=datetime.fromisoformat(at)
                and (e['cell_id'] is None or e['cell_id'].endswith(':'+key))][-40:]
        curves={sid:[dict(at=d['timeline'][i],r=next(r['metrics']['total_r'] if r['metrics'] else None for r in s if r['strategy_id']==sid))
                    for i,s in enumerate(d['views'][key]['snapshots'][:index+1])] for sid in d['strategies']}
        return dict(projection_id=d['projection_id'],index=index,at=at,phase='FINAL' if index==len(d['timeline'])-1 else ('OUT_OF_SAMPLE' if datetime.fromisoformat(at)>=datetime.fromisoformat(d['configuration']['split']) else 'DEVELOPMENT'),
                    rows=rows,events=events,curves=curves,correlation=d['correlation'] if index==len(d['timeline'])-1 else None)

    @router.get('/inspector')
    def inspector(cell_id:str=Query(...,pattern='^p6-[0-9]{2}:(XAUUSD|XAGUSD|USOIL):(1H|4H)$'),index:int=Query(0,ge=0,le=127)):
        d=load(); sid,symbol,frame=cell_id.split(':'); view=d['views'][symbol+':'+frame]
        if cell_id not in view['cells'] or index>=len(d['timeline']): raise HTTPException(404,'Unknown cell/snapshot')
        row=next(r for r in view['snapshots'][index] if r['cell_id']==cell_id)
        return dict(strategy=d['strategies'][sid],state=row,datasets=d['configuration']['datasets'],cost_model=d['configuration']['cost_model'],
                    robustness=view['cells'][cell_id].get('robustness') if index==len(d['timeline'])-1 else None,
                    correlation=d['correlation'] if index==len(d['timeline'])-1 else None,warning=WARNING,
                    limitations=['NOT_INCLUDED commission','Retrospective short sample; not a fresh holdout','Research OHLC outcomes, not broker fills','WTI mapping and provider timing limitations','No account or portfolio PnL'])
    return router
