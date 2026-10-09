"""P3 durable submission and conservative reconciliation; no runtime composition.

A committed STARTED marker precedes any call that could submit. SQLite serializes
the final safety check and synchronous send against local HALT/config changes.
After STARTED, recovery only observes: absence never authorizes another send.
"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext

from .execution_contracts import Attestation, BrokerSnapshot, SubmissionResult
from .ledger import canonical, hashed
from .safety import fresh
from .broker_observations import ObservationJournal
from .mt5_evidence import project_native

D = Decimal


class ExecutionEngine:
    def __init__(self, safety, broker, *, clock=None):
        self.safety, self.ledger, self.broker = safety, safety.ledger, broker
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        account = self.ledger.account
        if not account or broker.scope != account.evidence_source:
            raise ValueError('Adapter/account evidence scope mismatch')
        self.journal = ObservationJournal(account.key)
        from .source_registry import active
        with self.ledger.connect() as conn:
            if active(conn) is not None:
                raise ValueError('P4_BROKER_HARD_DISABLED')

    def _time(self):
        current = self.clock()
        if current.tzinfo is None:
            raise ValueError('Aware execution time required')
        return current.astimezone(timezone.utc)

    def _attest(self, value, current, session=None):
        a = Attestation.model_validate(value.model_dump() if isinstance(value, Attestation) else value)
        account = self.ledger.account
        fresh(a.observed_at, current, 5)
        if ((a.account_key, a.account_id, a.server, a.currency, a.scope) !=
                (account.key, account.account_id, account.server, account.currency, account.evidence_source)
                or not all((a.connected, a.trade_allowed, a.expert_allowed, a.hedging))
                or session is not None and a.session_id != session):
            raise ValueError('Unattested or mismatched demo session')
        return a

    def _event(self, conn, attempt, kind, payload):
        identity = hashed([attempt, kind, payload])
        conn.execute('INSERT INTO p3_events VALUES(?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING',
                     (identity, attempt, kind, canonical(payload), self._time().isoformat()))
        return identity

    def _since(self, conn):
        row = conn.execute('SELECT min(created_at) FROM p3_attempts').fetchone()[0]
        return datetime.fromisoformat(row) if row else self._time()

    def _snapshot(self, conn):
        from .source_registry import active
        if active(conn) is not None:
            raise ValueError('P4_BROKER_HARD_DISABLED')
        since = self._since(conn)
        try:
            value = self.broker.snapshot(since)
        finally:
            self.journal.append(conn, getattr(self.broker, 'observations', ()))
        if isinstance(value, dict) and 'native_observations' in value:
            self.journal.append(conn, value['native_observations'])
            value = project_native(conn, self.journal, value)
        snapshot = BrokerSnapshot.model_validate(value.model_dump() if isinstance(value, BrokerSnapshot) else value)
        current = self._time()
        self._attest(snapshot.attestation, current)
        fresh(snapshot.observed_at, current, 5)
        if not snapshot.complete or snapshot.history_since > since:
            raise ValueError('Incomplete reconciliation coverage')
        a = snapshot.safety.account
        if (a.account_key != self.ledger.account.key or a.currency != self.ledger.account.currency
                or not a.complete or not a.reconciled):
            raise ValueError('Incomplete account evidence')
        fresh(a.observed_at, current, 5)
        fresh(a.positions_at, current, 5)
        fresh(a.orders_at, current, 5)
        for group, key in ((snapshot.orders,'broker_order_id'), (snapshot.deals,'broker_deal_id'),
                           (snapshot.positions,'broker_position_id'),(snapshot.protective_exit_orders,'broker_order_id')):
            if len({getattr(item,key) for item in group}) != len(group):
                raise ValueError('Duplicate broker identities in snapshot')
            if any(item.observed_at > current + timedelta(seconds=2) for item in group):
                raise ValueError('Future broker evidence')
        for position in snapshot.positions:
            fresh(position.observed_at, current, 5)
        return snapshot

    def _revision(self, conn, kind, identity, current, old=None):
        if kind=='POSITION' and current.confirmed_absent:
            evidence = conn.execute('SELECT payload FROM p3_observations WHERE observation_id=? AND account_key=? AND broker_entity_type=?',
                                    (current.absence_evidence_id,self.ledger.account.key,'INVENTORY')).fetchone()
            if evidence:
                inventory=json.loads(evidence[0])['normalized_payload']
                if not inventory.get('complete') or identity in inventory['positions']:
                    raise ValueError('Contradictory native absence evidence')
                return True  # Full closing deals/quantities are checked separately.
        row = conn.execute('SELECT observation_id,state FROM p3_observation_heads WHERE account_key=? AND broker_entity_type=? AND broker_entity_id=?',
                           (self.ledger.account.key,kind,identity)).fetchone()
        if not row:
            return False
        if row['state'] != 'CURRENT' or row['observation_id'] != current.evidence_id:
            raise ValueError('Noncurrent revision used for economic projection')
        if old:
            immutable = {'DEAL':('broker_deal_id','broker_order_id','broker_position_id','symbol','direction','entry'),
                         'ORDER':('broker_order_id','correlation','magic','symbol','direction','entry_type','requested_volume','stop_loss','take_profit'),
                         'POSITION':('broker_position_id','opening_order_id','symbol','direction')}[kind]
            payload = current.model_dump(mode='json')
            if any(old[k] != payload[k] for k in immutable):
                raise ValueError('Revision changes economic identity or authorized command')
        return True

    def _fail_safe(self, conn, attempt_id, reason, evidence=None):
        # Never persist exception text from transports: it may contain secrets.
        payload = {'reason': reason, 'evidence': evidence}
        identity = self._event(conn, attempt_id, 'RECONCILIATION_REQUIRED', payload)
        conn.execute('INSERT INTO quarantine VALUES(?,?,?,?) ON CONFLICT(evidence_id) DO NOTHING',
                     (identity, reason, canonical(payload), self._time().isoformat()))
        conn.execute("UPDATE halt_state SET state='HALTED',version=version+1,reason=?,updated_at=? WHERE singleton=1",
                     (reason, self._time().isoformat()))
        # Retain full risk on contradictory evidence, including previously converted
        # risk. Do not roll back observed fills or manufacture a position close.
        conn.execute("UPDATE p2_reservations SET state='AMBIGUOUS' WHERE intent_id IN (SELECT intent_id FROM p3_attempts WHERE started_at IS NOT NULL)")
        conn.execute("UPDATE p3_positions SET lifecycle_state='RECOVERY_REQUIRED'")
        conn.execute("UPDATE p3_observation_heads SET state='AMBIGUOUS',observation_id=NULL WHERE broker_entity_type IN ('ORDER','DEAL','POSITION')")
        conn.execute("UPDATE p3_attempts SET state='SUBMISSION_AMBIGUOUS',failure=?,updated_at=? WHERE started_at IS NOT NULL",
                     (reason, self._time().isoformat()))

    def prepare(self, request_id):
        with self.ledger.transaction() as conn:
            row = conn.execute('SELECT * FROM p3_attempts WHERE execution_request_id=?', (request_id,)).fetchone()
            if row:
                return dict(row)
            request = conn.execute('SELECT * FROM p2_execution_requests WHERE execution_request_id=?', (request_id,)).fetchone()
            if not request:
                raise ValueError('P2 request required; P1 fixture requests cannot execute')
            identity = hashed([self.ledger.account.key, request_id, 'p3-attempt-v1'])
            correlation = 'nx3-' + identity[:24]
            magic = int(identity[24:39], 16)  # Positive 60-bit value; SQL collision rejects.
            stamp = self._time().isoformat()
            conn.execute("INSERT INTO p3_attempts VALUES(?,?,?,?,?,'NOT_SUBMITTED',?,NULL,?,NULL,NULL)",
                         (identity, request_id, request['intent_id'], correlation, magic, stamp, stamp))
            self._event(conn, identity, 'PREPARED', {'execution_request_id': request_id})
            return dict(conn.execute('SELECT * FROM p3_attempts WHERE attempt_id=?', (identity,)).fetchone())

    def get(self, request_id):
        with self.ledger.connect() as conn:
            row = conn.execute('SELECT * FROM p3_attempts WHERE execution_request_id=?', (request_id,)).fetchone()
            return dict(row) if row else None

    def _gate(self, conn, attempt, snapshot, *, begun=False):
        request, intent, allocation, evidence = self.safety.revalidate_reserved(
            conn, attempt['execution_request_id'], snapshot.safety, self._time(), begun=begun)
        command = dict(attempt_id=attempt['attempt_id'], execution_request_id=request['execution_request_id'],
                       intent_id=request['intent_id'], safety_decision_id=request['decision_id'],
                       account_key=request['account_key'], policy_hash=request['policy_hash'],
                       correlation=attempt['correlation'], magic=attempt['magic'],
                       entry_type=intent['entry_type'], **allocation)
        q = evidence.quotes[allocation['symbol']]
        command['base_entry'] = str(q.ask if allocation['direction']=='BUY' else q.bid)
        command['limit_entry'] = str(intent['entry']) if intent['entry_type']=='LIMIT' else None
        command['session_id'] = snapshot.attestation.session_id
        reservation = conn.execute('SELECT expires_at FROM p2_reservations WHERE intent_id=?', (request['intent_id'],)).fetchone()
        deadlines = [datetime.fromisoformat(reservation[0]), snapshot.attestation.observed_at+timedelta(seconds=5),
                     evidence.account.observed_at+timedelta(seconds=5), evidence.account.positions_at+timedelta(seconds=5),
                     evidence.account.orders_at+timedelta(seconds=5)]
        for symbol, quote in evidence.quotes.items():
            meta = evidence.instruments[symbol]
            deadlines.extend((quote.observed_at+timedelta(seconds=3), meta.observed_at+timedelta(hours=1),
                              meta.conversion_at+timedelta(seconds=10)))
        signal = json.loads(conn.execute('SELECT payload FROM signals WHERE signal_id=?', (intent['signal_id'],)).fetchone()[0])
        if signal['source_type']=='WHATSAPP_HUMAN':
            deadlines.append(datetime.fromtimestamp(signal['source_timestamp'],timezone.utc)+timedelta(seconds=600))
        command['valid_until'] = min(deadlines).isoformat()
        self._event(conn, attempt['attempt_id'], 'SUBMISSION_SAFETY_REVALIDATED',
                    {'command': command, 'evidence': evidence.model_dump(mode='json'),
                     'attestation': snapshot.attestation.model_dump(mode='json')})
        return command

    def _project(self, conn, snapshot, submitting=None):
        conn.execute('SAVEPOINT broker_projection')
        try:
            with localcontext() as ctx:
                ctx.prec = 40
                return self._reconcile(conn, snapshot, submitting=submitting)
        except BaseException:
            conn.execute('ROLLBACK TO broker_projection')
            raise
        finally:
            conn.execute('RELEASE broker_projection')

    def submit(self, request_id):
        attempt = self.prepare(request_id)
        if attempt['started_at'] is not None:
            self.reconcile()
            return self.get(request_id)
        if attempt['failure']:
            return attempt
        # Separate commit: a crash in the following transaction cannot erase STARTED.
        with self.ledger.transaction() as conn:
            attempt = conn.execute('SELECT * FROM p3_attempts WHERE execution_request_id=?', (request_id,)).fetchone()
            if attempt['state'] != 'NOT_SUBMITTED' or attempt['failure']:
                return dict(attempt)
            try:
                snapshot = self._snapshot(conn)
                self._project(conn, snapshot)
                command = self._gate(conn, attempt, snapshot)
            except Exception:
                self._fail_safe(conn, attempt['attempt_id'], 'PRE_SUBMISSION_GATE_FAILED')
                conn.execute('UPDATE p3_attempts SET failure=? WHERE attempt_id=?', ('PRE_SUBMISSION_GATE_FAILED', attempt['attempt_id']))
                return dict(conn.execute('SELECT * FROM p3_attempts WHERE attempt_id=?', (attempt['attempt_id'],)).fetchone())
            stamp = self._time().isoformat()
            conn.execute("UPDATE p2_reservations SET state='SUBMISSION_BEGUN' WHERE intent_id=?", (attempt['intent_id'],))
            conn.execute("UPDATE p3_attempts SET state='SUBMISSION_STARTED',started_at=?,updated_at=?,command=? WHERE attempt_id=?",
                         (stamp, stamp, canonical(command), attempt['attempt_id']))
            self._event(conn, attempt['attempt_id'], 'SUBMISSION_STARTED', {'command': command})
        # Only this invocation, which committed STARTED, can enter the send section.
        # Other workers/restarts see STARTED and are observation-only.
        with self.ledger.transaction() as conn:
            attempt = conn.execute('SELECT * FROM p3_attempts WHERE execution_request_id=?', (request_id,)).fetchone()
            try:
                if attempt['state'] != 'SUBMISSION_STARTED':
                    raise ValueError('Recovery invalidated submission')
                snapshot = self._snapshot(conn)
                self._project(conn, snapshot, submitting=attempt['attempt_id'])
                command = self._gate(conn, attempt, snapshot, begun=True)
                self._attest(self.broker.attest(), self._time(), command['session_id'])
                if self._time() >= datetime.fromisoformat(command['valid_until']):
                    raise ValueError('Evidence expired at send boundary')
            except Exception:
                self._fail_safe(conn, attempt['attempt_id'], 'FINAL_SUBMISSION_GATE_FAILED')
                return dict(conn.execute('SELECT * FROM p3_attempts WHERE attempt_id=?', (attempt['attempt_id'],)).fetchone())
            try:
                raw = self.broker.submit(command)
                result = SubmissionResult.model_validate(raw.model_dump() if isinstance(raw, SubmissionResult) else raw)
                self._attest(result.attestation, self._time(), command['session_id'])
                fresh(result.observed_at, self._time(), 5)
                event = self._event(conn, attempt['attempt_id'], 'BROKER_RESPONSE', result.model_dump(mode='json'))
                if result.outcome == 'ACKNOWLEDGED' and result.broker_order_id:
                    state = 'SUBMISSION_CONFIRMED'
                elif result.outcome == 'REJECTED' and not result.broker_order_id:
                    state = 'REJECTED_BY_BROKER'
                    conn.execute("UPDATE p2_reservations SET state='RELEASED',terminal_evidence_id=? WHERE intent_id=?", (event, attempt['intent_id']))
                else:
                    raise ValueError('Ambiguous broker response')
                conn.execute('UPDATE p3_attempts SET state=?,command=?,updated_at=? WHERE attempt_id=?',
                             (state, canonical(command), self._time().isoformat(), attempt['attempt_id']))
            except Exception:
                self._fail_safe(conn, attempt['attempt_id'], 'SUBMISSION_RESPONSE_AMBIGUOUS')
        self.reconcile()
        return self.get(request_id)

    def reconcile(self):
        """Read-only broker calls even while HALTED. No retry, cancel or close calls."""
        with localcontext() as ctx, self.ledger.transaction() as conn:
            ctx.prec = 40
            snapshot = None
            try:
                snapshot = self._snapshot(conn)
                result = self._project(conn, snapshot)
            except Exception:
                self._fail_safe(conn, None, 'BROKER_RECONCILIATION_MISMATCH',
                                snapshot.model_dump(mode='json') if snapshot else None)
                result = {'status': 'RECONCILIATION_REQUIRED'}
            return result

    def _reconcile(self, conn, snapshot, submitting=None):
        # Even an unchanged initial payload must not bypass a later unresolved
        # observation conflict. Check every journaled entity before projection.
        for kind,items,key in (('ORDER',snapshot.orders,'broker_order_id'),('DEAL',snapshot.deals,'broker_deal_id'),
                               ('POSITION',snapshot.positions,'broker_position_id'),('ORDER',snapshot.protective_exit_orders,'broker_order_id')):
            for item in items:
                self._revision(conn,kind,getattr(item,key),item)
        by_order, owners = {}, {}
        for order in snapshot.orders:
            attempt = conn.execute('SELECT * FROM p3_attempts WHERE correlation=? AND magic=?', (order.correlation, order.magic)).fetchone()
            if not attempt or not attempt['started_at'] or not attempt['command']:
                raise ValueError('Unknown external broker order')
            command = json.loads(attempt['command'])
            if (order.symbol, order.direction, order.entry_type, order.requested_volume, order.stop_loss, order.take_profit) != (
                    command['symbol'], command['direction'], command['entry_type'], D(command['volume']), D(command['stop']), D(command['nearest_tp'])):
                raise ValueError('Order differs from reserved command')
            if attempt['attempt_id'] == submitting:
                raise ValueError('Order already exists before this send')
            responses = conn.execute("SELECT payload FROM p3_events WHERE attempt_id=? AND kind='BROKER_RESPONSE'", (attempt['attempt_id'],)).fetchall()
            if any(json.loads(r[0])['outcome']=='REJECTED' for r in responses):
                raise ValueError('Order contradicts broker rejection')
            if any(json.loads(r[0]).get('broker_order_id') not in {None, order.broker_order_id} for r in responses):
                raise ValueError('Acknowledged order identity conflict')
            old = conn.execute('SELECT * FROM p3_orders WHERE broker_order_id=? OR attempt_id=?', (order.broker_order_id, attempt['attempt_id'])).fetchone()
            if old:
                prior = json.loads(old['payload'])
                if old['broker_order_id'] != order.broker_order_id or old['attempt_id'] != attempt['attempt_id']:
                    raise ValueError('Conflicting order identity')
                revision = self._revision(conn,'ORDER',order.broker_order_id,order,prior)
                if not revision and (order.observed_at < datetime.fromisoformat(old['observed_at']) or order.filled_volume < D(prior['filled_volume'])):
                    raise ValueError('Regressing broker order')
                if prior['status'] in {'FILLED','CANCELLED','REJECTED'} and prior['status'] != order.status:
                    raise ValueError('Terminal order changed')
            by_order[order.broker_order_id], owners[order.broker_order_id] = order, attempt
        existing_orders = {r[0] for r in conn.execute('SELECT broker_order_id FROM p3_orders')}
        if not existing_orders <= by_order.keys():
            raise ValueError('Previously observed order missing from complete history')
        position_map = {p.broker_position_id:p for p in snapshot.positions}
        volumes, position_orders, closed_volumes, exit_totals = {}, {}, {}, {}
        exits = {o.broker_order_id:o for o in snapshot.protective_exit_orders}
        if by_order.keys() & exits.keys():
            raise ValueError('Opening and closing order identity overlap')
        if not {r[0] for r in conn.execute('SELECT broker_order_id FROM p3_exit_orders')} <= exits.keys():
            raise ValueError('Missing previously observed exit')
        for close in exits.values():
            position = position_map.get(close.broker_position_id)
            order = by_order.get(position.opening_order_id) if position else None
            if (not order or order.status not in {'FILLED','CANCELLED'} or close.symbol != order.symbol
                    or close.direction == order.direction):
                raise ValueError('Protective exit lacks exact owned terminal opening order')
            old = conn.execute('SELECT payload FROM p3_exit_orders WHERE broker_order_id=?', (close.broker_order_id,)).fetchone()
            if old and json.loads(old[0]) != close.model_dump(mode='json'):
                raise ValueError('Immutable protective exit conflict')
        for deal in snapshot.deals:
            if deal.entry == 'OUT':
                close = exits.get(deal.broker_order_id)
                if (not close or (deal.broker_position_id,deal.symbol,deal.direction) !=
                        (close.broker_position_id,close.symbol,close.direction)):
                    raise ValueError('Unknown external closing deal')
                old = conn.execute('SELECT payload FROM p3_exit_deals WHERE broker_deal_id=?', (deal.broker_deal_id,)).fetchone()
                if old and json.loads(old[0]) != deal.model_dump(mode='json') and not self._revision(conn,'DEAL',deal.broker_deal_id,deal,json.loads(old[0])):
                    raise ValueError('Immutable closing deal conflict')
                if conn.execute('SELECT 1 FROM p3_deals WHERE broker_deal_id=?', (deal.broker_deal_id,)).fetchone():
                    raise ValueError('Deal identity reused across entry and exit')
                closed_volumes[deal.broker_position_id] = closed_volumes.get(deal.broker_position_id,D(0)) + deal.volume
                exit_totals[close.broker_order_id] = exit_totals.get(close.broker_order_id,D(0)) + deal.volume
                continue
            order = by_order.get(deal.broker_order_id)
            if not order or deal.entry != 'IN':
                raise ValueError('Unattributed or unsupported closing/netting deal')
            if (deal.symbol, deal.direction) != (order.symbol, order.direction):
                raise ValueError('Deal/order mismatch')
            command = json.loads(owners[order.broker_order_id]['command'])
            if (deal.price > D(command['modeled_entry']) if deal.direction=='BUY' else deal.price < D(command['modeled_entry'])):
                raise ValueError('Observed fill exceeded admitted execution allowance')
            position = position_map.get(deal.broker_position_id)
            if not position or position.opening_order_id != order.broker_order_id:
                raise ValueError('Missing exact broker position evidence')
            if position_orders.setdefault(deal.broker_position_id, order.broker_order_id) != order.broker_order_id:
                raise ValueError('Netting allocation unsupported')
            volumes[order.broker_order_id] = volumes.get(order.broker_order_id, D(0)) + deal.volume
            old = conn.execute('SELECT payload FROM p3_deals WHERE broker_deal_id=?', (deal.broker_deal_id,)).fetchone()
            if old and json.loads(old[0]) != deal.model_dump(mode='json') and not self._revision(conn,'DEAL',deal.broker_deal_id,deal,json.loads(old[0])):
                raise ValueError('Immutable deal conflict')
            if conn.execute('SELECT 1 FROM p3_exit_deals WHERE broker_deal_id=?', (deal.broker_deal_id,)).fetchone():
                raise ValueError('Deal identity reused across exit and entry')
        if not {r[0] for r in conn.execute('SELECT broker_deal_id FROM p3_deals')} <= {d.broker_deal_id for d in snapshot.deals}:
            raise ValueError('Missing previously observed deal')
        if not {r[0] for r in conn.execute('SELECT broker_deal_id FROM p3_exit_deals')} <= {d.broker_deal_id for d in snapshot.deals if d.entry=='OUT'}:
            raise ValueError('Missing previously observed closing deal')
        if any(exit_totals.get(o.broker_order_id) != o.filled_volume for o in exits.values()):
            raise ValueError('Protective order/deal quantity mismatch')
        expected_exposures = {}
        for position in snapshot.positions:
            order = by_order.get(position.opening_order_id)
            if not order or position_orders.get(position.broker_position_id) != order.broker_order_id:
                raise ValueError('Unknown external broker position')
            if ((position.symbol, position.direction, position.stop_loss, position.take_profit) !=
                    (order.symbol, order.direction, order.stop_loss, order.take_profit)
                    or position.open_volume != volumes.get(order.broker_order_id, D(0))-closed_volumes.get(position.broker_position_id,D(0))):
                raise ValueError('Position quantity or protection mismatch; no local close')
            if position.open_volume:
                expected_exposures[position.broker_position_id] = (
                    position.symbol, position.direction, position.open_volume, position.stop_loss,
                    'POSITION', owners[order.broker_order_id]['intent_id'])
        actual_exposures = {e.exposure_id:(e.symbol,e.direction,e.volume,e.stop_loss,e.kind,e.reservation_intent_id)
                            for e in snapshot.safety.account.exposures if e.kind=='POSITION'}
        if expected_exposures != actual_exposures or len(actual_exposures) != len([e for e in snapshot.safety.account.exposures if e.kind=='POSITION']):
            raise ValueError('Broker position inventory differs from safety inputs')
        # Pending orders are held in the local reservation; no optimistic release.
        # Reject additional provider exposure instead of assuming it is duplicated.
        if any(e.kind!='POSITION' for e in snapshot.safety.account.exposures):
            raise ValueError('Unresolved pending/external exposure')
        event = self._event(conn, None, 'BROKER_SNAPSHOT', snapshot.model_dump(mode='json'))
        for identity, order in by_order.items():
            attempt = owners[identity]
            total = volumes.get(identity, D(0))
            if total != order.filled_volume:
                raise ValueError('Order/deal quantity mismatch')
            payload = order.model_dump(mode='json')
            old = conn.execute('SELECT * FROM p3_orders WHERE broker_order_id=?', (identity,)).fetchone()
            if old and order.observed_at == datetime.fromisoformat(old['observed_at']) and json.loads(old['payload']) != payload and not self._revision(conn,'ORDER',identity,order,json.loads(old['payload'])):
                raise ValueError('Contradictory simultaneous order evidence')
            conn.execute('INSERT INTO p3_orders VALUES(?,?,?,?) ON CONFLICT(broker_order_id) DO UPDATE SET payload=excluded.payload,observed_at=excluded.observed_at',
                         (identity, attempt['attempt_id'], canonical(payload), order.observed_at.isoformat()))
            self.journal.link(conn,'ORDER',identity,attempt['attempt_id'])
            terminal = order.status in {'FILLED','CANCELLED','REJECTED'}
            state = {'PLACED':'SUBMISSION_CONFIRMED', 'PARTIALLY_FILLED':'PARTIALLY_FILLED',
                     'FILLED':'FILLED','CANCELLED':'CANCELLED','REJECTED':'REJECTED_BY_BROKER'}[order.status]
            reservation_state = ('CONVERTED' if total else 'RELEASED') if terminal else ('PARTIAL' if total else 'SUBMISSION_BEGUN')
            current_open = total - sum(closed_volumes.get(p.broker_position_id,D(0)) for p in snapshot.positions if p.opening_order_id==identity)
            if terminal:
                reservation_state = 'CONVERTED' if current_open else 'RELEASED'
            conn.execute('UPDATE p2_reservations SET state=?,filled_volume=?,terminal_evidence_id=? WHERE intent_id=?',
                         (reservation_state,str(current_open),event,attempt['intent_id']))
            conn.execute('UPDATE p3_attempts SET state=?,failure=NULL,updated_at=? WHERE attempt_id=?',
                         (state,self._time().isoformat(),attempt['attempt_id']))
            self._event(conn, attempt['attempt_id'], 'RESERVATION_RECONCILED',
                        {'snapshot_id':event,'state':reservation_state,'filled_volume':str(total),'current_open_volume':str(current_open)})
        for deal in snapshot.deals:
            owner = owners[deal.broker_order_id] if deal.entry=='IN' else owners[position_map[deal.broker_position_id].opening_order_id]
            self.journal.link(conn,'DEAL',deal.broker_deal_id,owner['attempt_id'])
            if deal.entry!='IN':
                continue
            conn.execute('INSERT INTO p3_deals VALUES(?,?,?,?) ON CONFLICT(broker_deal_id) DO NOTHING',
                         (deal.broker_deal_id,deal.broker_order_id,deal.broker_position_id,canonical(deal.model_dump(mode='json'))))
        for position in snapshot.positions:
            attempt = owners[position.opening_order_id]
            old = conn.execute('SELECT * FROM p3_positions WHERE broker_position_id=? OR attempt_id=?', (position.broker_position_id,attempt['attempt_id'])).fetchone()
            payload = canonical(position.model_dump(mode='json'))
            if old and (old['broker_position_id'] != position.broker_position_id or old['attempt_id'] != attempt['attempt_id']
                        or not self._revision(conn,'POSITION',position.broker_position_id,position,json.loads(old['payload'])) and
                        (position.observed_at < datetime.fromisoformat(old['observed_at'])
                        or position.observed_at == datetime.fromisoformat(old['observed_at']) and old['payload'] != payload)):
                raise ValueError('Position identity or observation conflict')
            state = 'OPEN' if position.open_volume else 'CLOSED'
            conn.execute("INSERT INTO p3_positions VALUES(?,?,?,?,?) ON CONFLICT(broker_position_id) DO UPDATE SET payload=excluded.payload,observed_at=excluded.observed_at,lifecycle_state=excluded.lifecycle_state",
                         (position.broker_position_id,attempt['attempt_id'],payload,position.observed_at.isoformat(),state))
            self.journal.link(conn,'POSITION',position.broker_position_id,attempt['attempt_id'])
        for close in exits.values():
            self.journal.link(conn,'ORDER',close.broker_order_id,owners[position_map[close.broker_position_id].opening_order_id]['attempt_id'])
            conn.execute('INSERT INTO p3_exit_orders VALUES(?,?,?) ON CONFLICT(broker_order_id) DO NOTHING',
                         (close.broker_order_id,close.broker_position_id,canonical(close.model_dump(mode='json'))))
        for deal in snapshot.deals:
            if deal.entry=='OUT':
                conn.execute('INSERT INTO p3_exit_deals VALUES(?,?,?,?) ON CONFLICT(broker_deal_id) DO NOTHING',
                             (deal.broker_deal_id,deal.broker_order_id,deal.broker_position_id,canonical(deal.model_dump(mode='json'))))
        missing = conn.execute("SELECT a.* FROM p3_attempts a LEFT JOIN p3_orders o ON o.attempt_id=a.attempt_id WHERE a.started_at IS NOT NULL AND o.attempt_id IS NULL AND a.state!='REJECTED_BY_BROKER'").fetchall()
        for attempt in missing:
            if attempt['attempt_id'] == submitting:
                continue
            self._fail_safe(conn, attempt['attempt_id'], 'SUBMISSION_NOT_FOUND_RETAIN_RISK')
        return {'status':'RECONCILIATION_REQUIRED' if any(a['attempt_id'] != submitting for a in missing) else 'RECONCILED', 'snapshot_id':event,
                'broker_verification':self.broker.scope}
