"""Read-only P8 inputs. P5/P6/P7 evidence is never initialized or rewritten."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

from .market_data import digest, Candle, VALIDATOR
from .research_strategies import Features
from .export_research import VERSION as QUALIFIER_VERSION, trusted
from .evtl_provider import VERSION as NORMALIZER

ROOT = Path(__file__).resolve().parents[3]
LABEL_POLICY = 'p8-resolved-win-loss-v1'
NUMERIC = ('rsi14', 'rsi2', 'adx', 'di_difference', 'stochastic', 'williams',
           'cci', 'atr_fraction', 'ema20_distance', 'ema50_distance',
           'macd_fraction', 'spread_fraction', 'signal_reward_r', 'hour', 'weekday')
CATEGORIES = ('instrument', 'timeframe', 'direction', 'family', 'strategy_id')
SCHEMA = dict(version='p8-signal-features-v1', numeric=list(NUMERIC), categories=list(CATEGORIES),
    types={'numeric': 'finite float or missing', 'category': 'string'},
    transforms='ATR/MACD/spread divided by signal-time reference; EMA distance/reference',
    missing='train-only median plus missing indicators; all-missing columns retained',
    encoding='train-only standard scaling and one-hot; unseen categories ignored',
    available_at='closed signal bar; never next-bar realized entry', execution_eligible=False)
SCHEMA_ID = digest(SCHEMA)


def stamp(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None: raise ValueError('Unqualified timezone')
    return t.astimezone(timezone.utc)


def verify(value, key):
    if digest({k:v for k,v in value.items() if k != key}) != value[key]:
        raise ValueError('Evidence identity mismatch: '+key)
    return value


def finite(value):
    if value is None: return None
    if isinstance(value,bool): raise ValueError('Boolean is not a numeric feature')
    n = float(value)
    if not math.isfinite(n): raise ValueError('Non-finite feature')
    return n


def features(signal, bar):
    t = stamp(signal['signal_timestamp'])
    if bar.closed != t or (bar.instrument, bar.timeframe) != (signal['instrument'], signal['timeframe']):
        raise ValueError('Signal/bar identity or availability mismatch')
    if signal.get('context_closed_at') and stamp(signal['context_closed_at']) > t:
        raise ValueError('Future context')
    f = signal['features']; base = finite(signal['entry_reference'])
    if base <= 0: raise ValueError('Invalid reference')
    stop=finite(signal['stop_loss']); target=finite(signal['take_profit']); direction=signal['direction']
    if direction not in {'BUY','SELL'} or stop is None or target is None or stop<=0 or target<=0:
        raise ValueError('Invalid research direction/levels')
    if not (stop<base<target if direction=='BUY' else target<base<stop):
        raise ValueError('Invalid intended geometry')
    row = {k:finite(f.get(k)) for k in NUMERIC[:7]}
    row.update(atr_fraction=finite(f.get('atr'))/base if f.get('atr') is not None else None,
        ema20_distance=(base-finite(f['ema20']))/base if f.get('ema20') is not None else None,
        ema50_distance=(base-finite(f['ema50']))/base if f.get('ema50') is not None else None,
        macd_fraction=finite(f['macd'])/base if f.get('macd') is not None else None,
        spread_fraction=float(bar.ask_ohlc['close']-bar.close)/base,
        signal_reward_r=abs(finite(signal['take_profit'])-base)/abs(base-finite(signal['stop_loss'])),
        hour=t.hour, weekday=t.weekday())
    row.update({k:str(signal[k]) for k in CATEGORIES})
    validate_features(row)
    return row


def validate_features(row):
    if set(row) != set(NUMERIC+CATEGORIES): raise ValueError('Feature schema mismatch')
    for k in NUMERIC:
        if row[k] is not None and not isinstance(row[k],(int,float)):
            raise ValueError('Numeric feature type mismatch')
        finite(row[k])
    if any(not isinstance(row[k],str) or not row[k] for k in CATEGORIES):
        raise ValueError('Invalid category')


def folds(rows, start, end):
    """Expanding elapsed-time windows. Equality at resolution cutoff is allowed."""
    if end <= start: raise ValueError('Invalid range')
    seconds = (end-start).total_seconds()
    boundaries = [start.timestamp()+int(seconds*p/14400)*14400 for p in (.4,.6,.8,1)]
    boundaries[-1] = end.timestamp()
    output=[]
    for i,(a,b) in enumerate(zip(boundaries,boundaries[1:])):
        cutoff=datetime.fromtimestamp(a,timezone.utc); stop=datetime.fromtimestamp(b,timezone.utc)
        train=[r for r in rows if stamp(r['signal_at'])<cutoff and stamp(r['resolved_at'])<=cutoff]
        test=[r for r in rows if cutoff<=stamp(r['signal_at'])<stop and stamp(r['resolved_at'])<=stop]
        crossing=sum(stamp(r['signal_at'])<cutoff<stamp(r['resolved_at']) for r in rows)
        output.append(dict(fold=i,cutoff=cutoff.isoformat(),end=stop.isoformat(),
                           train=train,test=test,crossing_excluded=crossing))
    return output


def read_inputs():
    index=verify(json.loads((ROOT/'knowledge/Audits/P7-TOURNAMENT-RESULTS.json').read_text()),'result_id')
    if digest(index['configuration']) != index['run_id']: raise ValueError('P7 configuration changed')
    path=ROOT/'research/p5-market-data/market-data.sqlite3'
    if any(p.is_symlink() or p.is_junction() for p in [path,*path.parents]):
        raise ValueError('Linked evidence forbidden')
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    try:
        runs={}
        for cell in index['cells']:
            for part in ('development','oos'):
                ref=cell.get('replays',{}).get(part)
                if not ref: continue
                run=json.loads(c.execute('SELECT payload FROM p6_runs WHERE id=?',(ref['run_id'],)).fetchone()[0])
                verify(run,'artifact_id')
                if run['artifact_id']!=ref['artifact_id'] or digest(run['configuration'])!=run['run_id']:
                    raise ValueError('Pinned research run changed')
                runs[run['run_id']]=run
        bar_maps={}; snapshots={}; qualifications={}; rows=[]; outcomes=Counter(); by_group=defaultdict(Counter)
        for run in runs.values():
            data=run['configuration']['data']; dataset=data['dataset_id']; qid=data['qualification_id']
            if data['fixture']: raise ValueError('Fixture research cannot qualify')
            if qid not in qualifications:
                q=json.loads(c.execute('SELECT payload FROM p5_export_qualification WHERE id=?',(qid,)).fetchone()[0])
                if (digest(q)!=qid or q['dataset_id']!=dataset or q['state']!='QUALIFIED_WITH_KNOWN_LIMITATIONS'
                    or q['version']!=QUALIFIER_VERSION):
                    raise ValueError('Unqualified dataset')
                qualifications[qid]=q
            q=qualifications[qid]; a=stamp(data['start']); b=stamp(data['end'])
            if not any(stamp(s['start'])<=a<b<=stamp(s['end']) for s in q['segments']):
                raise ValueError('Unqualified research interval')
            key=(dataset,data['start'],data['end'])
            if key not in bar_maps:
                m=json.loads(c.execute('SELECT manifest FROM datasets WHERE id=?',(dataset,)).fetchone()[0])
                if (digest(m)!=dataset or not m['real_data'] or m['provider']!='EV_TRADING_LABS'
                    or m['normalization']!=NORMALIZER or m['validation']!=VALIDATOR
                    or m['price_basis']!='BID_WITH_SEPARATE_ASK_OHLC'):
                    raise ValueError('Dataset identity/basis mismatch')
                receipts=[dict(r) for r in c.execute('SELECT raw_id,ingested_at,provenance FROM receipts WHERE dataset=? ORDER BY id',(dataset,))]
                if not receipts or digest(dict(manifest=m,qualification=q,receipts=receipts))!=data['provenance_hash']:
                    raise ValueError('Provenance mismatch')
                if not trusted(dict(manifest=m,provenance=receipts)):
                    raise ValueError('Untrusted or synthetic provenance')
                payloads=[json.loads(r[0]) for r in c.execute(
                    'SELECT payload FROM bars WHERE dataset=? AND opened>=? AND opened<? ORDER BY opened',key)]
                if digest(payloads)!=data['rows_hash']: raise ValueError('Pinned bar range changed')
                bars=[Candle.model_validate(p) for p in payloads]
                bar_maps[key]={bar.closed:bar for bar in bars}
                builder=Features()
                snapshots[key]={bar.closed:{k:str(v) for k,v in builder.push(bar).features.items()} for bar in bars}
            for t in run['trades']:
                outcomes[t['outcome']]+=1
                s=t['signal']; group=f"{s['instrument']}:{s['timeframe']}:{s['strategy_id']}"
                by_group[group][t['outcome']]+=1
                if t['outcome'] not in {'WIN','LOSS'}: continue
                if digest(dict(run_id=run['run_id'],signal_id=s['signal_id'])) != t['research_trade_id']:
                    raise ValueError('Trade lineage mismatch')
                resolved=t.get('exit_timestamp') or t.get('exit_interval_end')
                if not resolved or not t.get('evidence_hash'): raise ValueError('Outcome missing evidence')
                if stamp(resolved)<stamp(s['signal_timestamp']): raise ValueError('Resolution before signal')
                bar=bar_maps[key].get(stamp(s['signal_timestamp']))
                if bar is None: raise ValueError('Feature bar missing')
                if (s['dataset_id']!=dataset or s['qualification_id']!=qid or s['provider']!=bar.provider
                    or s['execution_eligible'] is not False): raise ValueError('Signal source lineage mismatch')
                if s['features']!=snapshots[key][bar.closed]:
                    raise ValueError('Signal features do not match causal closed-bar reconstruction')
                if digest({k:v for k,v in s.items() if k not in {'signal_id','disposition'}})!=s['signal_id']:
                    raise ValueError('Signal content identity mismatch')
                rows.append(dict(id=t['research_trade_id'],signal_id=s['signal_id'],run_id=run['run_id'],
                    dataset_id=dataset,qualification_id=qid,strategy_version=s['strategy_version'],
                    signal_at=s['signal_timestamp'],resolved_at=resolved,
                    resolution_basis='EXACT' if t.get('exit_timestamp') else 'CONSERVATIVE_INTERVAL_END',
                    feature_available_at=s['signal_timestamp'],outcome=t['outcome'],label=int(t['outcome']=='WIN'),
                    label_policy=LABEL_POLICY,evidence_hash=t['evidence_hash'],r_multiple=finite(t['r_multiple']),
                    features=features(s,bar),schema_id=SCHEMA_ID))
        rows.sort(key=lambda r:(r['signal_at'],r['id']))
        if len({r['id'] for r in rows})!=len(rows): raise ValueError('Duplicate economic research label')
        split=index['configuration']['split']
        # Range comes from pinned P5 evidence, not a selected profitable subperiod.
        p5=verify(json.loads((ROOT/'knowledge/Audits/P5-ALTERNATIVE-DATA-EVIDENCE.json').read_text()),'evidence_id')
        audit=dict(total_trades=sum(outcomes.values()),outcomes=dict(outcomes),labels=len(rows),
            runs=len(runs),class_balance=dict(Counter(str(r['label']) for r in rows)),
            by_instrument_timeframe_strategy={k:dict(v) for k,v in sorted(by_group.items())},
            by_family=dict(Counter(r['features']['family'] for r in rows)),
            by_month=dict(Counter(r['signal_at'][:7] for r in rows)),
            p7_result_id=index['result_id'],p5_evidence_id=p5['evidence_id'],rows_hash=digest(rows),
            dataset_ids=sorted({r['dataset_id'] for r in rows}),
            warning='SHORT_SAMPLE_RESEARCH_ONLY; reused P7 window; overlapping strategy observations not independent')
        return rows,audit,stamp(p5['common_qualified_start']),stamp(p5['common_qualified_end_exclusive'])
    finally: c.close()
