"""V1 operator proposals/controls and P9 read-only projections. No broker imports.

Native activation is deliberately unavailable until P3 operator qualification.
Monitoring consumes persisted evidence; it never calls the execution engine.
"""
from collections import Counter
from datetime import datetime, timezone
import json

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .ledger import canonical, hashed
from .lifecycle_contracts import TradeIntent
from .research_strategies import catalogue
from .source_ingestion import SourceSubmission

COMPONENTS = ('api', 'database', 'event_processing', 'mt5', 'account_binding',
              'market_data', 'p2', 'execution', 'reconciliation', 'whatsapp',
              'strategy_scheduler', 'monitoring')
SOURCE_TYPES = ('MANUAL', 'WHATSAPP_HUMAN', 'NEXUSAI_STRATEGY',
                'HISTORICAL_WHATSAPP', 'SCREENSHOT')
CONTROL_KEYS = ('manual', 'whatsapp', 'automated')
STRATEGY_IDS = ('p6-01', 'p6-02', 'p6-04', 'p6-05', 'p6-07')


def stamp(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('Aware timestamp required')
    return value.astimezone(timezone.utc)


class ControlCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    command_id: str = Field(pattern=r'^[A-Za-z0-9._:-]{8,128}$')
    expected_revision: int = Field(ge=0, strict=True)
    manual: StrictBool
    whatsapp: StrictBool
    automated: StrictBool


class DeploymentCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    strategy_id: str
    instrument: str
    timeframe: str
    enabled: StrictBool = False


class Operations:
    def __init__(self, ledger, *, sources=None, safety=None, provider=None, clock=None, research_projection=None):
        self.ledger, self.sources, self.safety, self.provider = ledger, sources, safety, provider
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        if research_projection is None:
            from .p8_projection import projection
            research_projection = projection if not ledger.account or ledger.account.evidence_source!='FIXTURE' else (
                lambda: dict(status='NOT_AVAILABLE',scope='RESEARCH_ONLY',ml_filter='DISABLED',
                             human_imitation='INSUFFICIENT_DATA',kronos='NOT_RUN',execution_eligible=False))
        self.research_projection = research_projection

    def _time(self):
        return stamp(self.clock()).isoformat()

    @staticmethod
    def _controls(conn):
        row = conn.execute('SELECT * FROM v1_control_events ORDER BY revision DESC LIMIT 1').fetchone()
        return dict(revision=row['revision'], **json.loads(row['payload'])) if row else dict(
            revision=0, manual=False, whatsapp=False, automated=False)

    def controls(self):
        with self.ledger.connect() as conn:
            result = self._controls(conn)
            halt = dict(conn.execute('SELECT * FROM halt_state WHERE singleton=1').fetchone())
        return dict(result, halt=halt, mode='HALTED' if halt['state'] != 'ACTIVE' else 'RESEARCH',
                    broker_execution='HARD_DISABLED', live_locked=True,
                    operator_qualification='NOT_PROVEN', execution_enabled=False)

    def set_controls(self, command):
        c = ControlCommand.model_validate(command.model_dump())
        payload = {k: getattr(c, k) for k in CONTROL_KEYS}
        with self.ledger.transaction() as conn:
            old = conn.execute('SELECT * FROM v1_control_events WHERE command_id=?', (c.command_id,)).fetchone()
            if old:
                if old['payload_hash'] != hashed(payload): raise ValueError('CONTROL_REPLAY_CONFLICT')
                return dict(revision=old['revision'], **json.loads(old['payload']))
            current = self._controls(conn)
            if current['revision'] != c.expected_revision: raise ValueError('CONTROL_REVISION_CONFLICT')
            if any(payload.values()): raise ValueError('P3_OPERATOR_QUALIFICATION_REQUIRED')
            revision = current['revision'] + 1
            conn.execute('INSERT INTO v1_control_events VALUES(?,?,?,?,?)',
                         (revision, c.command_id, self._time(), canonical(payload), hashed(payload)))
            self.ledger.audit(conn, 'V1_CONTROLS_RECORDED', None, dict(revision=revision, **payload))
            return dict(revision=revision, **payload)

    def deploy(self, command):
        c = DeploymentCommand.model_validate(command.model_dump())
        available = {s.strategy_id: s for s in catalogue() if s.strategy_id in STRATEGY_IDS}
        if c.strategy_id not in available: raise ValueError('STRATEGY_NOT_IN_V1_SUBSET')
        strategy = available[c.strategy_id]
        if c.instrument not in {'XAUUSD', 'XAGUSD', 'USOIL'} or c.timeframe not in {'1H', '4H'}:
            raise ValueError('INVALID_RESEARCH_DEPLOYMENT_MAPPING')
        if c.enabled: raise ValueError('P3_OPERATOR_QUALIFICATION_REQUIRED')
        identity = hashed(['v1-deployment', c.strategy_id, strategy.version, c.instrument, c.timeframe])
        with self.ledger.transaction() as conn:
            row = conn.execute('SELECT * FROM v1_deployments WHERE deployment_id=?', (identity,)).fetchone()
            if row: return dict(row)
            time = self._time()
            conn.execute('INSERT INTO v1_deployments VALUES(?,?,?,?,?,0,?,?,?)',
                         (identity, c.strategy_id, strategy.version, c.instrument, c.timeframe, 'DEMO_ONLY', time, time))
            conn.execute('INSERT INTO v1_deployment_events VALUES(?,?,?,?)',
                         (hashed([identity, 'created']), identity, time, canonical(c.model_dump())))
            return dict(conn.execute('SELECT * FROM v1_deployments WHERE deployment_id=?', (identity,)).fetchone())

    def ingest(self, submission):
        """Retryable source->P2 checkpoints. Never submits, invents lots, or authorizes a source."""
        s = SourceSubmission.model_validate(submission.model_dump())
        if s.source_type not in {'MANUAL', 'WHATSAPP_HUMAN'}:
            raise ValueError('USE_EXISTING_RESEARCH_SOURCE_BOUNDARY')
        identity = hashed(['v1-ingress', s.source_type, s.source_id, s.message_id])
        input_hash = hashed(s.model_dump(mode='json'))
        with self.ledger.transaction() as conn:
            old = conn.execute('SELECT * FROM v1_ingress WHERE ingress_id=?', (identity,)).fetchone()
            if old and old['input_hash'] != input_hash: raise ValueError('INGRESS_REPLAY_CONFLICT')
            if old and old['status'] != 'PENDING':
                self.ledger.audit(conn, 'V1_DUPLICATE_BLOCKED', None, dict(ingress_id=identity, source_type=s.source_type))
                return dict(json.loads(old['payload']), duplicate=True)
            if not old:
                conn.execute('INSERT INTO v1_ingress VALUES(?,?,?,?,?,?,?)',
                             (identity, input_hash, s.source_type, s.source_id, self._time(), 'PENDING', '{}'))
        result = dict(ingress_id=identity, source_type=s.source_type, execution_enabled=False,
                      broker_execution='HARD_DISABLED', status='REJECTED_UNAUTHORIZED_SOURCE')
        if self.sources is None:
            return self._finish(identity, dict(result, reason='SOURCE_CONFIGURATION_REQUIRED'))
        try:
            source = self.sources.ingest(s)
        except ValueError:
            return self._finish(identity, dict(result, reason='SOURCE_VALIDATION_OR_AUTHORIZATION_FAILED'))
        result.update(source_event_id=source['source_event_id'], signal_id=source['signal_id'])
        if source['status'] != 'VALIDATED':
            return self._finish(identity, dict(result, status='QUARANTINED_AMBIGUOUS', reason=source.get('reason')))
        if source['execution_eligibility'] != 'P2_ONLY':
            return self._finish(identity, dict(result, status='REJECTED_EXPIRED', reason=source.get('reason')))
        if self.safety is None or self.ledger.account is None:
            return self._finish(identity, dict(result, status='VALID_EXECUTION_CANDIDATE', reason='P2_ACCOUNT_NOT_CONFIGURED'))
        with self.ledger.connect() as conn:
            signal = json.loads(conn.execute('SELECT payload FROM signals WHERE signal_id=?', (source['signal_id'],)).fetchone()[0])
        targets = tuple(signal['take_profit'])
        intent = TradeIntent(client_order_id=identity, signal_id=source['signal_id'], symbol=signal['symbol'],
            direction=signal['direction'], entry=signal.get('entry'), entry_type=signal['entry_type'],
            stop_loss=signal['stop_loss'], take_profit=min(targets) if signal['direction']=='BUY' else max(targets),
            take_profit_targets=targets, requested_risk_pct=signal.get('requested_risk_pct'),
            volume=1.0)  # Legacy intent mirror only; P2 independently allocates actual volume.
        saved = self.sources.lifecycle.create_intent(intent)
        intent_id = saved['intent_id']
        try:
            inputs = self.provider(intent_id) if self.provider else None
        except Exception:
            inputs = None
        decision = self.safety.evaluate(intent_id, hashed([identity, 'decision']), inputs, current=self.clock())
        result.update(intent_id=intent_id, decision_id=decision['decision_id'],
                      reason=decision['reason'], allocation=decision['allocation'],
                      status='P2_APPROVED_NOT_SUBMITTED' if decision['decision']=='APPROVED' else 'P2_REJECTED')
        if decision['decision'] == 'APPROVED':
            try:
                request = self.safety.eligible_request(intent_id, decision['decision_id'], hashed([identity, 'request']), current=self.clock())
                result['execution_request_id'] = request['execution_request_id']
            except ValueError:
                result.update(status='P2_REVALIDATION_REQUIRED', reason='REQUEST_ELIGIBILITY_CHANGED')
        return self._finish(identity, result)

    def _finish(self, identity, result):
        with self.ledger.transaction() as conn:
            row = conn.execute('SELECT status,payload FROM v1_ingress WHERE ingress_id=?', (identity,)).fetchone()
            if row['status'] != 'PENDING': return dict(json.loads(row['payload']), duplicate=True)
            conn.execute('UPDATE v1_ingress SET status=?,payload=? WHERE ingress_id=?',
                         (result['status'], canonical(result), identity))
            self.ledger.audit(conn, 'V1_INGRESS_CLASSIFIED', result.get('intent_id'),
                              dict(ingress_id=identity, status=result['status'], source_type=result['source_type']))
        return result

    def record_health(self, *, component, state, observed_at, valid_until, evidence_id):
        """Trusted worker API, not HTTP intake. No arbitrary metric/secret payload."""
        if component not in COMPONENTS or state not in {'HEALTHY','DEGRADED','DISCONNECTED','HALTED','ERROR'}:
            raise ValueError('Invalid component/state')
        observed, until, current = stamp(observed_at), stamp(valid_until), stamp(self.clock())
        if observed > current or until <= observed or not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError('Invalid health evidence')
        payload = dict(component=component, state=state, observed_at=observed.isoformat(),
                       valid_until=until.isoformat(), evidence_ref=hashed(evidence_id))
        identity = hashed(payload)
        with self.ledger.transaction() as conn:
            conn.execute('INSERT OR IGNORE INTO v1_monitor_samples VALUES(?,?,?,?,?,?,?)',
                         (identity, component, payload['observed_at'], payload['valid_until'], state, canonical(payload), hashed(payload)))
            if state in {'ERROR','DISCONNECTED','HALTED','DEGRADED'}:
                severity = 'CRITICAL' if state in {'ERROR','HALTED'} else 'WARNING'
                conn.execute('INSERT OR IGNORE INTO v1_alerts VALUES(?,?,?,?,?,?,NULL)',
                             (identity, state, severity, component, identity, payload['observed_at']))
        return identity

    def acknowledge(self, alert_id, command_id):
        if not isinstance(command_id, str) or not 8 <= len(command_id) <= 128:
            raise ValueError('Invalid acknowledgment identity')
        with self.ledger.transaction() as conn:
            if not conn.execute('SELECT 1 FROM v1_alerts WHERE alert_id=?', (alert_id,)).fetchone(): raise KeyError('Unknown alert')
            prior = conn.execute('SELECT alert_id FROM v1_alert_ack WHERE command_id=?', (command_id,)).fetchone()
            if prior and prior[0] != alert_id: raise ValueError('ACK_REPLAY_CONFLICT')
            conn.execute('INSERT OR IGNORE INTO v1_alert_ack VALUES(?,?,?)', (command_id, alert_id, self._time()))
        return dict(alert_id=alert_id, acknowledged=True, economic_state_changed=False)

    def report(self, *, as_of=None, start=None):
        """One consistent read transaction; unavailable evidence is never a zero account."""
        end = stamp(as_of or self.clock())
        begin = stamp(start) if start else end.replace(hour=0,minute=0,second=0,microsecond=0)
        if begin > end or end > stamp(self.clock()): raise ValueError('Invalid report window')
        with self.ledger.connect() as conn:
            conn.execute('BEGIN')
            report = self._project(conn, begin, end)
            conn.rollback()
        return dict(report, report_id=hashed(report))

    def _project(self, conn, begin, end):
        current = stamp(self.clock())
        def rows(sql, args=()): return [dict(r) for r in conn.execute(sql, args)]
        # Current economic tables are explicitly a current snapshot, not an as-of ledger replay.
        halt = dict(conn.execute('SELECT * FROM halt_state WHERE singleton=1').fetchone())
        controls = self._controls(conn)
        policy = conn.execute('SELECT version,policy_hash FROM p2_policy WHERE singleton=1').fetchone()
        health = []
        for component in COMPONENTS:
            sample = conn.execute('SELECT * FROM v1_monitor_samples WHERE component=? AND observed_at<=? ORDER BY observed_at DESC,sample_id DESC LIMIT 1',
                (component, current.isoformat())).fetchone()
            health.append(dict(component=component, state=(sample['state'] if stamp(sample['valid_until']) >= current else 'STALE') if sample else 'NOT_AVAILABLE',
                observed_at=sample['observed_at'] if sample else None, evidence_id=sample['sample_id'] if sample else None))
        ingress = rows('SELECT ingress_id,source_type,received_at,status,payload FROM v1_ingress WHERE received_at>=? AND received_at<=? ORDER BY received_at,ingress_id', (begin.isoformat(), end.isoformat()))
        source_counts = {s:dict(received=0, statuses={}) for s in SOURCE_TYPES}
        for item in ingress:
            info = source_counts[item['source_type']]
            info['received'] += 1
            info['statuses'][item['status']] = info['statuses'].get(item['status'],0)+1
        # Legacy/P4 source events are counted separately, not double-counted as ingress messages.
        canonical_counts = {r['source_type']:r['n'] for r in rows('SELECT source_type,count(*) n FROM source_events WHERE julianday(created_at)>=julianday(?) AND julianday(created_at)<=julianday(?) GROUP BY source_type', (begin.isoformat(),end.isoformat()))}
        for s in source_counts: source_counts[s]['canonical_sources'] = canonical_counts.get(s,0)
        decisions = rows('SELECT decision,reason_codes,timestamp,intent_id,risk_decision_id FROM risk_decisions WHERE julianday(timestamp)>=julianday(?) AND julianday(timestamp)<=julianday(?) ORDER BY timestamp,risk_decision_id', (begin.isoformat(),end.isoformat()))
        reasons = Counter(reason for d in decisions if d['decision']=='REJECTED' for reason in json.loads(d['reason_codes']))
        reservations = rows('SELECT * FROM p2_reservations ORDER BY intent_id')
        attempts = rows('SELECT attempt_id,execution_request_id,intent_id,state,created_at,started_at,updated_at FROM p3_attempts ORDER BY created_at,attempt_id')
        positions = rows('SELECT broker_position_id,attempt_id,lifecycle_state,observed_at,payload FROM p3_positions ORDER BY broker_position_id')
        heads = rows('SELECT broker_entity_type,broker_entity_id,observation_id,state FROM p3_observation_heads ORDER BY broker_entity_type,broker_entity_id')
        ambiguity = [r for r in attempts if r['state']=='SUBMISSION_AMBIGUOUS']
        alerts = rows('SELECT a.*, EXISTS(SELECT 1 FROM v1_alert_ack k WHERE k.alert_id=a.alert_id) acknowledged FROM v1_alerts a WHERE observed_at<=? ORDER BY observed_at DESC,alert_id LIMIT 200', (end.isoformat(),))
        if halt['state'] != 'ACTIVE':
            alerts.insert(0, dict(alert_id='persistent-halt', kind='HALT_ACTIVE',severity='CRITICAL',source='p2',acknowledged=False,observed_at=halt['updated_at'],resolved_at=None))
        deployments = rows('SELECT * FROM v1_deployments ORDER BY strategy_id,instrument,timeframe')
        from .strategy_observer import scheduler_projection
        for d in deployments:
            d.update(qualification='UNQUALIFIED_AUTOMATION', research_status='RESEARCH_EVIDENCE_INSUFFICIENT',
                     last_evaluated_at=None,last_signal_id=None,execution_status='HARD_DISABLED')
            d.update(scheduler_projection(conn,d['deployment_id']))
        account = dict(status='NOT_AVAILABLE', balance=None,equity=None,floating_pnl=None,realized_pnl=None,
                       free_margin=None,margin_utilization=None,daily_pnl=None,weekly_pnl=None,drawdown=None)
        baselines = rows('SELECT observed_at,day_start,week_start,day_equity,week_equity,high_water_equity FROM p2_baselines')
        broker = {}
        for name in ('orders','deals','exit_orders','exit_deals'):
            broker[name] = rows(f'SELECT * FROM p3_{name}')
            for item in broker[name]:
                value = json.loads(item.pop('payload'))
                # No raw/native references, comments or credentials in public export.
                item['evidence'] = {k:v for k,v in value.items() if k in {'symbol','direction','status','volume','filled_volume','requested_volume','price','profit','commission','swap','fee','entry','observed_at','evidence_id'}}
        for item in positions:
            value = json.loads(item.pop('payload'))
            item['evidence'] = {k:v for k,v in value.items() if k in {'symbol','direction','open_volume','stop_loss','take_profit','confirmed_absent','observed_at'}}
        inventory = {s:dict(mapping_status='NOT_ATTESTED',quote_at=None,candle_at=None,spread=None) for s in ('XAUUSD','XAGUSD','USOIL')}
        from .monitoring import latest_safety, lineage_activity, current_risks, health_coverage, execution_lineage, source_counters
        account, observed_market, exposure = latest_safety(conn, current)
        inventory.update(observed_market)
        activity = lineage_activity(conn, begin, end)
        risk_totals = current_risks(conn, current)
        for component in health:
            if component['component'] in {'api','database','monitoring'}:
                component.update(state='HEALTHY',observed_at=current.isoformat(),evidence_id='current-read-transaction')
        from .source_registry import active
        config = active(conn)
        manual_sources = [r.source_id for r in config.sources if r.enabled and r.source_type=='MANUAL'] if config else []
        events = rows('SELECT event_type,timestamp,intent_id FROM audit_events WHERE julianday(timestamp)>=julianday(?) AND julianday(timestamp)<=julianday(?) ORDER BY timestamp,sequence', (begin.isoformat(),end.isoformat()))
        return dict(schema='v1-evidence-v1',snapshot_at=current.isoformat(),scope='FIXTURE' if self.ledger.account and self.ledger.account.evidence_source=='FIXTURE' else 'NON_OPERATIONAL',
            window=dict(start=begin.isoformat(),end=end.isoformat(),inclusive=True),
            snapshot_semantics='CURRENT_ECONOMIC_STATE; window applies to activity only',
            account_reference=self.ledger.account.key if self.ledger.account else None,
            broker_execution='HARD_DISABLED',live_locked=True,operator_qualification='NOT_PROVEN',
            manual_sources=manual_sources,
            strategy_catalogue=[dict(strategy_id=s.strategy_id,name=s.name,version=s.version) for s in catalogue() if s.strategy_id in STRATEGY_IDS],
            controls=controls,halt=halt,health=health,sources=source_counts,
            recent_ingress=[{**json.loads(i['payload']), 'ingress_id':i['ingress_id'],'received_at':i['received_at']} for i in ingress[-100:]],
            safety=dict(policy=dict(policy) if policy else None,decisions=decisions[-100:],rejection_reasons=dict(reasons),
                        reservations=reservations,recorded_baselines=baselines,current_exposure=exposure,**risk_totals),
            execution=dict(attempts=attempts,positions=positions,**broker,latency_status='NOT_AVAILABLE',
                           lineage=execution_lineage(conn)),
            reconciliation=dict(status='AMBIGUOUS' if ambiguity else 'NOT_ATTESTED',ambiguous_attempts=ambiguity,
                                observation_heads=heads,observation_count=conn.execute('SELECT count(*) FROM p3_observations').fetchone()[0]),
            portfolio=account,instruments=inventory,deployments=deployments,alerts=alerts,activity=activity,
            health_coverage=health_coverage(conn,begin,end,COMPONENTS),
            source_metrics=source_counters(conn,begin,end,SOURCE_TYPES),
            p8=self.research_projection(),
            p10=dict(status='DEFERRED_FORWARD_QUALIFICATION',events=events,performance_status='NOT_AVAILABLE'),
            limitations=['OPERATOR_NOT_QUALIFIED','NO_CURRENT_BROKER_VALUATION','NO_LIVE_TRANSPORT_OR_SCHEDULER',
                         'CURRENT_SNAPSHOT_NOT_HISTORICAL_REPLAY','NO_FORWARD_PERFORMANCE_CLAIM'])
