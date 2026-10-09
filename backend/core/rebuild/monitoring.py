"""Pure P9 projections of existing evidence, not a safety policy or broker adapter."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal as D
import json

from .safety import POLICY
from .safety_contracts import SafetyInputs


def _time(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)


def latest_safety(conn, current):
    row = conn.execute('SELECT e.payload FROM p2_evaluations e JOIN risk_decisions d ON d.risk_decision_id=e.decision_id ORDER BY d.timestamp DESC,d.risk_decision_id DESC LIMIT 1').fetchone()
    empty = dict(status='NOT_AVAILABLE', evidence_id=None, observed_at=None, equity=None,
                 balance=None,floating_pnl=None,free_margin=None,margin_utilization=None,
                 daily_pnl=None,weekly_pnl=None,drawdown=None,realized_pnl=None)
    if not row: return empty, {}, {}
    raw=json.loads(row[0])
    if not raw.get('evidence'): return empty, {}, {}
    try:
        data=SafetyInputs.model_validate(raw['evidence'])
    except ValueError:
        return dict(empty,status='INVALID_EVIDENCE'), {}, {}
    a=data.account
    if not (0 <= (current-a.observed_at).total_seconds() <= POLICY['account_age']):
        return dict(empty,status='STALE',evidence_id=a.evidence_id,observed_at=a.observed_at.isoformat()), {}, {}
    if not a.complete or not a.reconciled:
        return dict(empty,status='RECONCILIATION_REQUIRED',evidence_id=a.evidence_id,observed_at=a.observed_at.isoformat()), {}, {}
    portfolio=dict(empty,status='OBSERVED_P2_INPUT',evidence_id=a.evidence_id,observed_at=a.observed_at.isoformat(),
        equity=str(a.equity),balance=str(a.balance),floating_pnl=str(a.equity-a.balance),
        free_margin=str(a.equity-a.used_margin),margin_utilization=str(a.used_margin/a.equity),
        metric_basis='equity change from cash-flow-adjusted P2 baseline; not closed-trade realized PnL')
    b=conn.execute('SELECT * FROM p2_baselines WHERE account_key=?',(a.account_key,)).fetchone()
    if b and _time(b['observed_at'])==a.observed_at:
        if _time(b['day_start']).date()==current.date(): portfolio['daily_pnl']=str(a.equity-D(b['day_equity']))
        if _time(b['week_start']).isocalendar()[:2]==current.isocalendar()[:2]: portfolio['weekly_pnl']=str(a.equity-D(b['week_equity']))
        portfolio['drawdown']=str(max(D(0),1-a.equity/D(b['high_water_equity'])))
    market={}
    for symbol,q in data.quotes.items():
        m=data.instruments.get(symbol)
        market[symbol]=dict(quote_at=q.observed_at.isoformat(),spread=str(q.ask-q.bid),bid=str(q.bid),ask=str(q.ask),
            quote_state='OBSERVED' if 0 <= (current-q.observed_at).total_seconds() <= POLICY['quote_age'] else 'STALE',
            metadata_at=m.observed_at.isoformat() if m else None,
            metadata_state='OBSERVED' if m and 0 <= (current-m.observed_at).total_seconds() <= POLICY['metadata_age'] else 'UNAVAILABLE_OR_STALE',
            mapping_status='P2_INPUT_SYMBOL; not independently attested by P9',candle_at=None)
    risk=defaultdict(lambda:D(0))
    valid=(0 <= (current-a.positions_at).total_seconds() <= POLICY['positions_age'] and
           0 <= (current-a.orders_at).total_seconds() <= POLICY['orders_age'])
    seen=set()
    for e in a.exposures:
        if e.exposure_id in seen: valid=False
        seen.add(e.exposure_id)
        q,m=data.quotes.get(e.symbol),data.instruments.get(e.symbol)
        if (not q or not m or market[e.symbol]['quote_state']!='OBSERVED'
                or market[e.symbol]['metadata_state']!='OBSERVED'
                or not 0 <= (current-m.conversion_at).total_seconds() <= POLICY['conversion_age']
                or m.account_currency != a.currency):
            valid=False; continue
        if e.kind!='POSITION':
            # Pending/ambiguous amounts require reservation attribution; never count as an ordinary position.
            valid=False; continue
        price=q.bid if e.direction=='BUY' else q.ask
        distance=price-e.stop_loss if e.direction=='BUY' else e.stop_loss-price
        if distance<=0: valid=False; continue
        risk[e.symbol]+=e.volume*(distance*m.value_per_price_unit_per_lot+m.commission_per_lot)
    exposure=dict(status='OBSERVED_P2_INPUT' if valid else 'UNAVAILABLE_OR_AMBIGUOUS',
        remaining_stop_risk={s:str(v) for s,v in risk.items()} if valid else None,
        position_count=len(a.exposures),total_stop_risk=str(sum(risk.values(),D(0))) if valid else None,
        price_basis='BUY BID to SL / SELL ASK to SL; commission allowance; not a P2 approval')
    return portfolio,market,exposure


def lineage_activity(conn, begin, end):
    rows=conn.execute('''SELECT s.source_type,s.source_id,s.payload signal,i.intent_id,i.symbol,
        d.decision,d.risk_decision_id,d.timestamp FROM risk_decisions d
        JOIN order_intents i ON i.intent_id=d.intent_id JOIN signals s ON s.signal_id=i.signal_id
        WHERE julianday(d.timestamp)>=julianday(?) AND julianday(d.timestamp)<=julianday(?)''',
        (begin.isoformat(),end.isoformat())).fetchall()
    by_source=defaultdict(Counter); by_instrument=defaultdict(Counter); by_strategy=defaultdict(Counter)
    for row in rows:
        by_source[row['source_type']][row['decision']]+=1
        by_instrument[row['symbol']][row['decision']]+=1
        if row['source_type']=='NEXUSAI_STRATEGY': by_strategy[row['source_id']][row['decision']]+=1
    return dict(by_source={k:dict(v) for k,v in by_source.items()},
                by_instrument={k:dict(v) for k,v in by_instrument.items()},
                by_strategy={k:dict(v) for k,v in by_strategy.items()},
                denominator='decision events in inclusive UTC activity window; retries of same decision ID are not new decisions')


def current_risks(conn, current):
    reservations=[dict(r) for r in conn.execute("SELECT * FROM p2_reservations WHERE state IN ('RESERVED','SUBMISSION_BEGUN','AMBIGUOUS','PARTIAL')")]
    per=defaultdict(lambda:D(0)); margin=D(0)
    for r in reservations:
        per[r['symbol']]+=D(r['risk']); margin+=D(r['margin'])
    return dict(policy_limits=POLICY,reserved_risk=str(sum(per.values(),D(0))),
        reserved_margin=str(margin),reserved_by_instrument={s:str(v) for s,v in per.items()},
        reserved_metals=str(per['XAUUSDm']+per['XAGUSDm']),reserved_energy=str(per['USOILm']),
        reserved_slots=len(reservations),
        expired_retained=[r['intent_id'] for r in reservations if _time(r['expires_at'])<=current],
        basis='full retained reservation amounts; not additive with converted broker exposure without reconciliation')


def health_coverage(conn, begin, end, components):
    """Integrate evidenced intervals; missing heartbeats are unknown, never uptime."""
    result = {}
    duration = (end - begin).total_seconds()
    for component in components:
        samples = [dict(r) for r in conn.execute(
            'SELECT * FROM v1_monitor_samples WHERE component=? AND julianday(observed_at)<=julianday(?)',
            (component, end.isoformat()))]
        cuts = {begin, end}
        for sample in samples:
            for key in ('observed_at', 'valid_until'):
                point = _time(sample[key])
                if begin < point < end: cuts.add(point)
        totals = defaultdict(float)
        boundaries = sorted(cuts)
        for left, right in zip(boundaries, boundaries[1:]):
            candidates = [s for s in samples if _time(s['observed_at']) <= left]
            state = 'UNKNOWN'
            if candidates:
                latest = max(_time(s['observed_at']) for s in candidates)
                current = [s for s in candidates if _time(s['observed_at']) == latest]
                if len({s['state'] for s in current}) > 1:
                    state = 'AMBIGUOUS'
                elif all(_time(s['valid_until']) > left for s in current):
                    state = current[0]['state']
            totals[state] += (right-left).total_seconds()
        unknown = totals['UNKNOWN'] + totals['AMBIGUOUS']
        result[component] = dict(seconds=dict(totals), window_seconds=duration,
            coverage_fraction=(duration-unknown)/duration if duration else None,
            healthy_fraction=totals['HEALTHY']/duration if duration else None,
            basis='recorded heartbeat validity only; not process uptime or broker attestation')
    return result


def execution_lineage(conn):
    rows = conn.execute('''SELECT s.source_event_id,s.signal_id,s.source_type,s.source_id,
        i.intent_id,d.risk_decision_id,d.decision,r.state reservation_state,
        q.execution_request_id,a.attempt_id,a.state attempt_state
        FROM signals s LEFT JOIN order_intents i ON i.signal_id=s.signal_id
        LEFT JOIN risk_decisions d ON d.intent_id=i.intent_id
        LEFT JOIN p2_reservations r ON r.intent_id=i.intent_id AND r.decision_id=d.risk_decision_id
        LEFT JOIN p2_execution_requests q ON q.decision_id=d.risk_decision_id
        LEFT JOIN p3_attempts a ON a.execution_request_id=q.execution_request_id
        ORDER BY s.signal_id,i.intent_id,d.risk_decision_id''').fetchall()
    result = []
    for row in rows:
        item = dict(row)
        attempt = item['attempt_id']
        item['broker_order_ids'] = [r[0] for r in conn.execute(
            'SELECT broker_order_id FROM p3_orders WHERE attempt_id=? ORDER BY broker_order_id', (attempt,))]
        item['broker_deal_ids'] = [r[0] for r in conn.execute('''SELECT d.broker_deal_id FROM p3_deals d
            JOIN p3_orders o ON o.broker_order_id=d.broker_order_id WHERE o.attempt_id=? ORDER BY d.broker_deal_id''',(attempt,))]
        item['broker_position_ids'] = [r[0] for r in conn.execute(
            'SELECT broker_position_id FROM p3_positions WHERE attempt_id=? ORDER BY broker_position_id',(attempt,))]
        item['exit_deal_ids'] = [r[0] for r in conn.execute('''SELECT d.broker_deal_id FROM p3_exit_deals d
            JOIN p3_positions p ON p.broker_position_id=d.broker_position_id WHERE p.attempt_id=? ORDER BY d.broker_deal_id''',(attempt,))]
        item['observation_ids'] = [r[0] for r in conn.execute(
            'SELECT observation_id FROM p3_observation_links WHERE attempt_id=? ORDER BY observation_id',(attempt,))]
        result.append(item)
    return result


def source_counters(conn, begin, end, source_types):
    result = {s:dict(received=0,validated=0,quarantined=0,approved=0,rejected=0,
        executed=0,duplicates_blocked=0) for s in source_types}
    for row in conn.execute('''SELECT source_type,status,count(*) n FROM v1_ingress
        WHERE julianday(received_at)>=julianday(?) AND julianday(received_at)<=julianday(?) GROUP BY source_type,status''',
        (begin.isoformat(),end.isoformat())):
        c = result[row['source_type']]; c['received'] += row['n']
        if row['status'].startswith('QUARANTINED'): c['quarantined'] += row['n']
        if row['status'].startswith('REJECTED'): c['rejected'] += row['n']
        if row['status'].startswith('P2_') or row['status']=='VALID_EXECUTION_CANDIDATE': c['validated'] += row['n']
    for row in conn.execute('''SELECT s.source_type,d.decision,count(*) n FROM risk_decisions d
        JOIN order_intents i ON i.intent_id=d.intent_id JOIN signals s ON s.signal_id=i.signal_id
        WHERE julianday(d.timestamp)>=julianday(?) AND julianday(d.timestamp)<=julianday(?) GROUP BY s.source_type,d.decision''',
        (begin.isoformat(),end.isoformat())):
        key = 'approved' if row['decision']=='APPROVED' else 'rejected'
        result[row['source_type']][key] += row['n']
    for row in conn.execute("SELECT payload FROM audit_events WHERE event_type='V1_DUPLICATE_BLOCKED' AND julianday(timestamp)>=julianday(?) AND julianday(timestamp)<=julianday(?)",(begin.isoformat(),end.isoformat())):
        source = json.loads(row[0]).get('source_type')
        if source in result: result[source]['duplicates_blocked'] += 1
    # A submitted attempt is NOT an executed trade. Require an owned economic deal.
    for row in conn.execute('''SELECT s.source_type,count(DISTINCT a.attempt_id) n FROM p3_deals b
        JOIN p3_orders o ON o.broker_order_id=b.broker_order_id JOIN p3_attempts a ON a.attempt_id=o.attempt_id
        JOIN order_intents i ON i.intent_id=a.intent_id JOIN signals s ON s.signal_id=i.signal_id
        WHERE julianday(o.observed_at)>=julianday(?) AND julianday(o.observed_at)<=julianday(?) GROUP BY s.source_type''',
        (begin.isoformat(),end.isoformat())):
        result[row['source_type']]['executed'] = row['n']
    return dict(counts=result, basis='V1 intake classifications; unique P2 decisions; owned filled attempts by first order-observation time; duplicate audit events')
