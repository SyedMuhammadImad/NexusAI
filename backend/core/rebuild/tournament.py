"""P7 research-only tournament. Frozen P6 rules; no broker or lifecycle imports."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D, localcontext
from itertools import combinations
import json

from .market_data import digest, encode
from .research_strategies import catalogue
from .strategy_research import Costs, ENGINE, ResearchLedger, fixture_store, metrics, replay

WARNING = 'SHORT_SAMPLE_RESEARCH_ONLY'
TOURNAMENT_ENGINE = 'p7-tournament-v1'
POLICY = dict(version='P7-RESEARCH-1.0', development_fraction='0.70', split_alignment_seconds=14400,
    resolved_total_min=50, resolved_oos_min=20, expectancy_strict_min='0', pf_min='1.20',
    win_rate_min='0.35', drawdown_max_r='10', exclusion_max='0.10', pf_degradation_max='0.50',
    correlation_absolute_min='0.80', slippage='0.05', stress_slippage='0.10',
    commission='NOT_INCLUDED', sample_denominator='WIN+LOSS+BREAKEVEN',
    metrics_basis='P6 priced outcomes including TIMEOUT', execution='HARD_DISABLED', warning=WARNING,
    split_method='ELAPSED_UTC_FLOOR_4H', no_parameter_tuning=True)
POLICY_HASH = digest(POLICY)


def split_at(start, end, fraction=D('.70')):
    if start.tzinfo is None or end.tzinfo is None or not start < end or not 0 < fraction < 1:
        raise ValueError('Invalid chronological split')
    target = D(str(start.timestamp())) + D(str((end-start).total_seconds()))*fraction
    result = datetime.fromtimestamp(int(target//14400)*14400, timezone.utc)
    if not start < result < end: raise ValueError('Range too short for aligned split')
    return result


def finite(value):
    if value is None or isinstance(value,bool): return None
    try: value = D(str(value))
    except Exception: return None
    return value if value.is_finite() else None


def assess(dev, oos, *, data_quality, leakage, cost_assumption):
    gates = {}
    def record(key, passed, evidence):
        gates[key] = dict(status='UNKNOWN' if passed is None else ('PASS' if passed else 'FAIL'), evidence=evidence)
    for row in (dev, oos):
        count = row.get('resolved_barrier_denominator')
        if type(count) is not int or count < 0:
            raise ValueError('Invalid resolved sample count')
    total = dev['resolved_barrier_denominator']+oos['resolved_barrier_denominator']
    record('SAMPLE',total>=50 and oos['resolved_barrier_denominator']>=20,
           dict(total=total,oos=oos['resolved_barrier_denominator'],required=[50,20]))
    for name,key,op,limit in (
        ('EXPECTANCY','expectancy_r',lambda a,b:a>b,D(0)),
        ('PROFIT_FACTOR','profit_factor',lambda a,b:a>=b,D('1.20')),
        ('WIN_RATE','win_rate',lambda a,b:a>=b,D('.35')),
        ('DRAWDOWN','max_drawdown_r',lambda a,b:a<=b,D(10)),
        ('AMBIGUITY','excluded_outcome_rate',lambda a,b:a<=b,D('.10')),
    ):
        v=finite(oos.get(key))
        if v is not None and (key in {'profit_factor','max_drawdown_r'} and v<0
            or key in {'win_rate','excluded_outcome_rate'} and not 0<=v<=1):
            raise ValueError('Invalid metric range')
        record(name,op(v,limit) if v is not None else None,dict(value=oos.get(key),threshold=str(limit)))
    a,b=finite(dev.get('expectancy_r')),finite(oos.get('expectancy_r'))
    p,q=finite(dev.get('profit_factor')),finite(oos.get('profit_factor'))
    drop=(p-q)/p if p is not None and p>0 and q is not None else None
    degraded=a is not None and a>0 and b is not None and b<=0
    record('DEGRADATION',None if a is None or b is None else not(degraded or drop is not None and drop>D('.5')),
           dict(development_expectancy=dev.get('expectancy_r'),oos_expectancy=oos.get('expectancy_r'),
                pf_relative_drop=str(drop) if drop is not None else None,
                pf_check='APPLICABLE' if drop is not None else 'NOT_APPLICABLE'))
    for key, value in [('DATA_QUALITY',data_quality),('LEAKAGE',leakage),('COST_ASSUMPTION',cost_assumption)]:
        record(key,value is True,dict(verified=value is True))
    if any(gates[k]['status']!='PASS' for k in ('DATA_QUALITY','LEAKAGE','COST_ASSUMPTION')):
        status='REJECTED'
    elif gates['SAMPLE']['status']!='PASS' or any(g['status']=='UNKNOWN' for g in gates.values()):
        status='INSUFFICIENT_EVIDENCE'
    elif any(g['status']=='FAIL' for g in gates.values()): status='REJECTED'
    else: status='RESEARCH_QUALIFIED'
    return dict(status=status,gates=gates,warning=WARNING,execution_eligible=False)


def validate_replay(report, data, strategy, start, end, costs, lower):
    c=report['configuration']
    frozen=json.loads(encode(asdict(strategy)))
    if (digest({k:v for k,v in report.items() if k!='artifact_id'})!=report['artifact_id']
        or digest(c)!=report['run_id'] or c['strategy']!=frozen or c['data']!=data.identity()
        or c['start']!=start.isoformat() or c['end']!=end.isoformat() or c['engine']!=ENGINE
        or c['costs']!=costs.payload() or c['execution']!='HARD_DISABLED'
        or c['context'] is not None or c['lower']!=(lower.identity() if lower else None)):
        raise ValueError('P6 replay identity/configuration mismatch')
    if report['metrics']!=metrics(report['trades'],report['signals'],costs):
        raise ValueError('P6 metric evidence mismatch')
    for t in report['trades']:
        if (t['run_id']!=report['run_id'] or t['broker_observed'] or t['dataset_id']!=data.dataset_id
            or t['research_trade_id']!=digest(dict(run_id=report['run_id'],signal_id=t['signal']['signal_id']))):
            raise ValueError('Trade provenance mismatch')
        if not start<=datetime.fromisoformat(t['entry_at'])<end:
            raise ValueError('Entry outside split')
        if not start<=datetime.fromisoformat(t['signal']['signal_timestamp'])<=datetime.fromisoformat(t['entry_at']):
            raise ValueError('Entry before signal')
        if t.get('exit_interval_end') and datetime.fromisoformat(t['exit_interval_end'])>end:
            raise ValueError('Label crosses split')
    return True


def removal_metrics(report, best):
    rows=report['trades']
    candidates=[(i,D(t['r_multiple'])) for i,t in enumerate(rows) if t.get('r_multiple') is not None]
    if not candidates: return dict(status='INSUFFICIENT_EVIDENCE',removed_trade_id=None)
    index=(max if best else min)(candidates,key=lambda pair:(pair[1],-pair[0] if best else pair[0]))[0]
    return dict(status='MEASURED',removed_trade_id=rows[index]['research_trade_id'],
                metrics=metrics(rows[:index]+rows[index+1:],report['signals'],Costs()))


def daily_returns(report, observed_days=None):
    c=report['configuration']; start=datetime.fromisoformat(c['start']); end=datetime.fromisoformat(c['end'])
    days={}; stamp=start.date()
    while stamp<=end.date():
        if observed_days is None or stamp.isoformat() in observed_days:
            days[stamp.isoformat()]=D(0)
        stamp+=timedelta(days=1)
    for t in report['trades']:
        if t.get('r_multiple') is None:
            a=datetime.fromisoformat(t['entry_at']).date()
            b=datetime.fromisoformat(t.get('exit_interval_end') or c['end']).date()
            while a<=b:
                if a.isoformat() in days: days[a.isoformat()]=None
                a+=timedelta(days=1)
    for t in report['trades']:
        if t.get('r_multiple') is not None:
            day=datetime.fromisoformat(t.get('exit_timestamp') or t['exit_interval_end']).date().isoformat()
            if day in days and days[day] is not None: days[day]+=D(t['r_multiple'])
    return days


def correlation(vectors):
    pairs=[]; edges={key:set() for key in vectors}
    for left,right in combinations(sorted(vectors),2):
        days=sorted(d for d in vectors[left].keys() & vectors[right].keys()
                    if vectors[left][d] is not None and vectors[right][d] is not None)
        x=[vectors[left][d] for d in days]; y=[vectors[right][d] for d in days]
        r=None
        if len(days)>=2:
            a=sum(x)/len(x); b=sum(y)/len(y)
            vx=sum((v-a)**2 for v in x); vy=sum((v-b)**2 for v in y)
            if vx>0 and vy>0: r=sum((v-a)*(w-b) for v,w in zip(x,y))/(vx*vy).sqrt()
        high=r is not None and abs(r)>=D('.80')
        if high: edges[left].add(right); edges[right].add(left)
        pairs.append(dict(left=left,right=right,common_days=len(days),pearson=str(r) if r is not None else None,
                          status='MEASURED' if r is not None else 'INSUFFICIENT_EVIDENCE',highly_correlated=high))
    clusters=[]; seen=set()
    for key in sorted(edges):
        if key in seen: continue
        stack=[key]; group=[]
        while stack:
            node=stack.pop()
            if node in seen: continue
            seen.add(node); group.append(node); stack.extend(sorted(edges[node]-seen))
        if len(group)>1: clusters.append(sorted(group))
    status = 'MEASURED' if any(p['status']=='MEASURED' for p in pairs) else ('INSUFFICIENT_EVIDENCE' if pairs else 'NOT_APPLICABLE_NO_QUALIFIED_PAIR')
    return dict(status=status,pairs=pairs,clusters=clusters,
                warning=WARNING,basis='UTC daily realized R; unresolved holding dates excluded; not marked-to-market portfolio returns')


def run_tournament(datasets, ledger):
    """All input views must already have passed ResearchData.load; fixtures stay labelled."""
    if digest(POLICY) != POLICY_HASH: raise ValueError('Locked policy changed')
    if set(datasets)!={(s,t) for s in ('XAUUSD','XAGUSD','USOIL') for t in ('1H','4H')}:
        raise ValueError('Exact six qualified views required')
    start,end=next(iter(datasets.values())).start,next(iter(datasets.values())).end
    if any(d.start!=start or d.end!=end for d in datasets.values()): raise ValueError('Inconsistent study range')
    fixture=all(d.fixture for d in datasets.values())
    if any(d.fixture!=fixture for d in datasets.values()): raise ValueError('Mixed fixture/real study')
    if any((d.bars[0].instrument,d.bars[0].timeframe)!=key for key,d in datasets.items()):
        raise ValueError('Dataset key/identity mismatch')
    split=split_at(start,end); middle=split_at(split,end,D('.5'))
    with localcontext() as ctx:
        ctx.prec=40
        fraction=str(D(str((split-start).total_seconds()))/D(str((end-start).total_seconds())))
    config=dict(tournament_engine=TOURNAMENT_ENGINE,policy=dict(POLICY),policy_hash=digest(POLICY),datasets=[datasets[k].identity() for k in sorted(datasets)],
                catalogue=[asdict(s) for s in catalogue()],engine=ENGINE,start=start.isoformat(),end=end.isoformat(),
                split=split.isoformat(),nominal_development_fraction='.70',
                actual_development_fraction=fraction,
                oos_robustness_split=middle.isoformat(),cost_model=Costs().payload(),
                evidence_scope='FIXTURE' if fixture else 'REAL_QUALIFIED')
    identity=digest(config); cells=[]; vectors={}; replays=0
    with localcontext() as ctx:
        ctx.prec=40
        for key in sorted(datasets):
            data=datasets[key]; lower=datasets[key[0],'1H'] if key[1]=='4H' else None
            for strategy in catalogue():
                cell=dict(strategy_id=strategy.strategy_id,strategy_version=strategy.version,
                          instrument=key[0],timeframe=key[1],cell_id=':'.join((strategy.strategy_id,*key)))
                if strategy.eligibility!='TOURNAMENT_READY' or key[1] not in strategy.timeframes or key[0] not in strategy.instruments:
                    cells.append(dict(cell,status='EXCLUDED',reason=strategy.eligibility if strategy.eligibility!='TOURNAMENT_READY' else 'UNSUPPORTED_TIMEFRAME',warning=WARNING))
                    continue
                reports={}
                for name,a,b,cost in (
                    ('development',start,split,Costs()),('oos',split,end,Costs()),
                    ('early_oos',split,middle,Costs()),('late_oos',middle,end,Costs()),
                    ('cost_stress',split,end,Costs('0.10')),
                ):
                    r=replay(data,strategy,start=a,end=b,costs=cost,lower=lower)
                    validate_replay(r,data,strategy,a,b,cost,lower)
                    if r!=replay(data,strategy,start=a,end=b,costs=cost,lower=lower):
                        raise ValueError('Non-reproducible replay')
                    ledger.save(r)
                    if ledger.read(r['run_id'])!=r: raise ValueError('Stored replay mismatch')
                    reports[name]=r; replays+=1
                d,o=reports['development'],reports['oos']
                verdict=assess(d['metrics'],o['metrics'],data_quality=True,leakage=True,cost_assumption=True)
                cell.update(verdict,development=d['metrics'],oos=o['metrics'],
                    replays={k:dict(run_id=v['run_id'],artifact_id=v['artifact_id']) for k,v in reports.items()},
                    robustness=dict(early_oos=reports['early_oos']['metrics'],late_oos=reports['late_oos']['metrics'],
                                    cost_stress=reports['cost_stress']['metrics'],
                                    remove_best=removal_metrics(o,True),remove_worst=removal_metrics(o,False)))
                cells.append(cell)
                if verdict['status']=='RESEARCH_QUALIFIED':
                    observed={b.opened.date().isoformat() for b in data.bars if split<=b.opened<end}
                    observed.update(b.closed.date().isoformat() for b in data.bars if split<b.closed<=end)
                    vectors[cell['cell_id']]=daily_returns(o,observed)
            print('P7_SERIES_COMPLETE',*key,flush=True)
        counted=Counter(c['status'] for c in cells)
        counts={k:counted[k] for k in ('RESEARCH_QUALIFIED','REJECTED','INSUFFICIENT_EVIDENCE','EXCLUDED')}
        qualified=sorted((c for c in cells if c['status']=='RESEARCH_QUALIFIED'),
                         key=lambda c:(-D(c['oos']['expectancy_r']),-D(c['oos']['profit_factor']),c['cell_id']))
        by_strategy={s.strategy_id:dict(Counter(c['status'] for c in cells if c['strategy_id']==s.strategy_id)) for s in catalogue()}
        result=dict(run_id=identity,configuration=config,cells=cells,counts=counts,
                    by_strategy_cell_counts=by_strategy,aggregation='Counts only; no pooled sample rescue or shared-capital PnL',
                    ranked_qualified_cells=[c['cell_id'] for c in qualified],correlation=correlation(vectors),
                    result='RESEARCH_QUALIFIED_CELLS_PRESENT' if qualified else 'NO_STRATEGY_RESEARCH_QUALIFIED',
                    verified_replays=replays,warning=WARNING,broker_execution='HARD_DISABLED')
        result['result_id']=digest(result)
        return json.loads(encode(result))


def save_tournament(store, result):
    if digest({k:v for k,v in result.items() if k!='result_id'})!=result['result_id'] or digest(result['configuration'])!=result['run_id']:
        raise ValueError('Tournament identity mismatch')
    if digest(POLICY)!=POLICY_HASH or result['configuration']['policy_hash']!=POLICY_HASH or result['configuration']['policy']!=POLICY:
        raise ValueError('Wrong tournament policy')
    if not fixture_store(store) and result['configuration']['evidence_scope']!='REAL_QUALIFIED':
        raise ValueError('Fixture tournament cannot enter real store')
    with store.connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS p7_runs(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS p7_no_update BEFORE UPDATE ON p7_runs BEGIN SELECT RAISE(ABORT,'Immutable P7'); END;
        CREATE TRIGGER IF NOT EXISTS p7_no_delete BEFORE DELETE ON p7_runs BEGIN SELECT RAISE(ABORT,'Immutable P7'); END;
        INSERT OR IGNORE INTO p5_schema VALUES(8);''')
        c.execute('BEGIN IMMEDIATE')
        payload=encode(result); old=c.execute('SELECT payload FROM p7_runs WHERE id=?',(result['run_id'],)).fetchone()
        if old and old[0]!=payload: raise ValueError('Tournament replay conflict')
        c.execute('INSERT OR IGNORE INTO p7_runs VALUES(?,?)',(result['run_id'],payload))
    return result['result_id']
