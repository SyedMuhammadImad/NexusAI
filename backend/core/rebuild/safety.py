"""ADR-010 deterministic admission. No broker submission or credential loading."""
import json
import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException, ROUND_CEILING, ROUND_FLOOR, localcontext

from pydantic import ValidationError

from .ledger import canonical, hashed, now
from .safety_contracts import SafetyConfiguration, SafetyInputs

D = Decimal
VERSION = "P2-DEMO-1.0"
POLICY = dict(version=VERSION, default_risk="0.0025", trade="0.005", instrument="0.0075",
              portfolio="0.015", metals="0.01", energy="0.0075", margin="0.25",
              instrument_notional="1.5", portfolio_notional="3", slots=3,
              daily="0.02", weekly="0.04", drawdown="0.08", rr="1.5",
              spread="0.10", slippage="0.05", deviation="0.05", ttl=60,
              quote_age=3, account_age=5, positions_age=5, orders_age=5,
              conversion_age=10, metadata_age=3600, future_skew=2,
              semantics="ADR-010-C01-C03;equity-margin;current-stop-risk;decimal;no-dispatch")


class Veto(ValueError):
    pass


def number(value):
    if isinstance(value, bool):
        raise Veto("INVALID_NUMBER")
    try:
        result = D(str(value))
    except Exception as exc:
        raise Veto("INVALID_NUMBER") from exc
    if not result.is_finite() or result <= 0:
        raise Veto("INVALID_NUMBER")
    return result


def fresh(stamp, current, seconds):
    age = (current - stamp).total_seconds()
    if age > seconds or age < -POLICY["future_skew"]:
        raise Veto("STALE_OR_FUTURE_EVIDENCE")


class SafetyEngine:
    def __init__(self, ledger, configuration: SafetyConfiguration, *, configuration_revision="1"):
        self.ledger = ledger
        self.config = SafetyConfiguration.model_validate(configuration.model_dump())
        self.configuration = self.config.model_dump(mode="json")
        for key in ("authorized_sources", "instruments", "restricted", "qualified_strategy_sources"):
            self.configuration[key] = sorted(self.configuration[key])
        if not configuration_revision.isdecimal() or int(configuration_revision) < 1:
            raise ValueError("Positive configuration revision required")
        self.version = VERSION + "/config-" + configuration_revision
        self.policy_hash = hashed([POLICY, self.configuration, self.version])
        with ledger.transaction() as conn:
            prior = conn.execute("SELECT * FROM p2_policy WHERE singleton=1").fetchone()
            if prior is None:
                conn.execute("INSERT INTO p2_policy VALUES(1,?,?,?)", (self.version, self.policy_hash, canonical(self.configuration)))
            elif prior["policy_hash"] != self.policy_hash:
                raise ValueError("Policy/configuration mismatch; explicit versioned policy activation required")

    def activate_configuration(self, configuration, *, revision, operator_id, reason):
        """Versioned control-plane configuration; numerical ADR-010 policy is fixed."""
        if not operator_id.strip() or not reason.strip() or not revision.isdecimal():
            raise ValueError("Explicit operator/revision/reason required")
        config = SafetyConfiguration.model_validate(configuration.model_dump())
        document = config.model_dump(mode="json")
        for key in ("authorized_sources", "instruments", "restricted", "qualified_strategy_sources"):
            document[key] = sorted(document[key])
        version = VERSION + "/config-" + revision
        digest = hashed([POLICY, document, version])
        with self.ledger.transaction() as conn:
            old = conn.execute("SELECT * FROM p2_policy WHERE singleton=1").fetchone()
            if old["policy_hash"] != self.policy_hash or int(revision) <= int(old["version"].rsplit('-',1)[1]):
                raise ValueError("Stale or non-increasing configuration revision")
            conn.execute("UPDATE p2_policy SET version=?,policy_hash=?,configuration=? WHERE singleton=1", (version,digest,canonical(document)))
            # Only proved unsubmitted work may relinquish capacity for re-evaluation.
            conn.execute("UPDATE p2_reservations SET state='RELEASED',terminal_evidence_id='UNSUBMITTED_POLICY_SUPERSEDED' WHERE state='RESERVED'")
            self.ledger.audit(conn,"P2_CONFIGURATION_ACTIVATED",None,dict(operator_id=operator_id,reason=reason,
                              previous=dict(old),version=version,policy_hash=digest,configuration=document))
        return SafetyEngine(self.ledger, config, configuration_revision=revision)

    def _symbol(self, symbol):
        symbol = self.config.aliases.get(symbol, symbol)
        if symbol not in self.config.instruments or symbol in self.config.restricted:
            raise Veto("INSTRUMENT_RESTRICTED")
        return symbol

    def _market(self, inputs, symbol, current):
        try:
            quote, instrument = inputs.quotes[symbol], inputs.instruments[symbol]
        except KeyError as exc:
            raise Veto("MISSING_MARKET_EVIDENCE") from exc
        if instrument.symbol != symbol or instrument.account_currency != inputs.account.currency:
            raise Veto("INSTRUMENT_CURRENCY_MISMATCH")
        if not instrument.tradable or not instrument.market_available:
            raise Veto("MARKET_UNAVAILABLE")
        fresh(quote.observed_at, current, 3)
        fresh(instrument.observed_at, current, 3600)
        fresh(instrument.conversion_at, current, 10)
        return quote, instrument

    def _baselines(self, conn, account, current):
        day = current.replace(hour=0, minute=0, second=0, microsecond=0)
        week = day - timedelta(days=day.weekday())
        if account.day_start != day or account.week_start != week:
            raise Veto("INVALID_PERIOD_BASELINE")
        previous = conn.execute("SELECT * FROM p2_baselines WHERE account_key=?", (account.account_key,)).fetchone()
        high = account.high_water_equity
        if previous:
            if account.observed_at < datetime.fromisoformat(previous["observed_at"]):
                raise Veto("ACCOUNT_SNAPSHOT_REGRESSION")
            flow = account.cash_flow_total - D(previous["cash_flow_total"])
            for period in ("day", "week"):
                if getattr(account, period + "_start") == datetime.fromisoformat(previous[period + "_start"]):
                    expected = D(previous[period + "_equity"]) + flow
                    if getattr(account, period + "_equity") != expected:
                        raise Veto("CONTRADICTORY_CASH_FLOW_BASELINE")
            high = max(high, D(previous["high_water_equity"]) + flow)
        high = max(high, account.equity)
        if min(account.day_equity, account.week_equity, high) <= 0:
            raise Veto("INVALID_CASH_FLOW_BASELINE")
        conn.execute("INSERT INTO p2_baselines VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(account_key) DO UPDATE SET observed_at=excluded.observed_at,cash_flow_total=excluded.cash_flow_total,day_start=excluded.day_start,week_start=excluded.week_start,day_equity=excluded.day_equity,week_equity=excluded.week_equity,high_water_equity=excluded.high_water_equity",
                     (account.account_key, account.observed_at.isoformat(), str(account.cash_flow_total),
                      day.isoformat(), week.isoformat(), str(account.day_equity), str(account.week_equity), str(high)))
        if account.equity <= high * D("0.92"):
            conn.execute("UPDATE halt_state SET state='HALTED',version=version+1,reason='P2_MAX_DRAWDOWN',updated_at=? WHERE singleton=1", (current.isoformat(),))
            raise Veto("MAX_DRAWDOWN_HALT")
        if account.equity <= account.day_equity * D("0.98"):
            raise Veto("DAILY_LOSS")
        if account.equity <= account.week_equity * D("0.96"):
            raise Veto("WEEKLY_LOSS")

    def _calculate(self, conn, intent, signal, inputs, current, *, reserved_intent=None, fixed_volume=None):
        account = inputs.account
        self.ledger._check_account(conn, account)
        if (account.account_key != self.config.approved_account_key or account.currency != self.ledger.account.currency
                or not account.complete or not account.reconciled or not account.cash_flow_evidence_id.strip()):
            raise Veto("ACCOUNT_NOT_ELIGIBLE_OR_RECONCILED")
        fresh(account.observed_at, current, 5)
        fresh(account.positions_at, current, 5)
        fresh(account.orders_at, current, 5)
        self._baselines(conn, account, current)
        source = signal["source_type"]
        if source not in {"MANUAL", "WHATSAPP_HUMAN", "NEXUSAI_STRATEGY"}:
            raise Veto("SOURCE_EXECUTION_INELIGIBLE")
        if signal["source_id"] not in self.config.authorized_sources:
            raise Veto("SOURCE_UNAUTHORIZED")
        if source == "NEXUSAI_STRATEGY" and signal["source_id"] not in self.config.qualified_strategy_sources:
            raise Veto("STRATEGY_NOT_QUALIFIED")
        from .source_registry import check_signal
        p4 = check_signal(conn, signal['signal_id'], current=current)
        if source == "WHATSAPP_HUMAN" and not p4:
            source_time = datetime.fromtimestamp(signal["source_timestamp"], timezone.utc)
            if source_time > current or (current - source_time).total_seconds() > 600:
                raise Veto("SOURCE_EXPIRED_OR_FUTURE")
        if intent.get("action") != "OPEN" or intent.get("direction") not in {"BUY", "SELL"}:
            raise Veto("UNKNOWN_ACTION")
        symbol = self._symbol(intent["symbol"])
        quote, meta = self._market(inputs, symbol, current)
        buy = intent["direction"] == "BUY"
        side = quote.ask if buy else quote.bid
        stop = number(intent["stop_loss"])
        targets = [number(t) for t in intent["take_profit_targets"]]
        if not targets:
            raise Veto("TP_REQUIRED")
        if intent["entry_type"] == "MARKET":
            base = side
        elif intent["entry_type"] == "LIMIT":
            base = number(intent.get("entry"))
            if (buy and base > quote.ask) or (not buy and base < quote.bid):
                raise Veto("CONTRADICTORY_LIMIT")
        else:
            raise Veto("UNKNOWN_ORDER_TYPE")
        distance = abs(side - stop)
        if distance <= 0 or not (stop < base if buy else stop > base):
            raise Veto("INVALID_GEOMETRY")
        if quote.ask - quote.bid > distance * D("0.10"):
            raise Veto("SPREAD_LIMIT")
        if intent["entry_type"] == "LIMIT" and abs(side - base) > distance * D("0.05"):
            raise Veto("QUOTE_DEVIATION")
        # LIMIT geometry remains at the explicit limit; its friction is monetary.
        adverse = distance * D("0.05")
        modeled = base + adverse if buy else base - adverse
        if intent["entry_type"] == "LIMIT":
            modeled = base
        mode = ROUND_CEILING if buy else ROUND_FLOOR
        entry = (modeled / meta.tick_size).to_integral_value(rounding=mode) * meta.tick_size
        rounded_stop = (stop / meta.tick_size).to_integral_value(rounding=ROUND_FLOOR if buy else ROUND_CEILING) * meta.tick_size
        target = min(targets) if buy else max(targets)
        target = (target / meta.tick_size).to_integral_value(rounding=ROUND_FLOOR if buy else ROUND_CEILING) * meta.tick_size
        if not (0 < rounded_stop < entry < target if buy else 0 < target < entry < rounded_stop):
            raise Veto("INVALID_GEOMETRY")
        if any(not (entry < t if buy else entry > t) for t in targets):
            raise Veto("INVALID_TARGET_GEOMETRY")
        friction = meta.commission_per_lot
        if intent["entry_type"] == "LIMIT":
            friction += adverse * meta.value_per_price_unit_per_lot
        loss = abs(entry - rounded_stop) * meta.value_per_price_unit_per_lot + friction
        reward = abs(target - entry) * meta.value_per_price_unit_per_lot - friction
        if reward < D("1.50") * loss:
            raise Veto("MINIMUM_R")
        capital = min(account.equity, account.balance)
        requested = intent.get("requested_risk_pct")
        fraction = D("0.0025") if requested is None else number(requested) / 100
        if fraction > D("0.005"):
            raise Veto("PER_TRADE_RISK")
        budget = capital * fraction
        volume = (budget / loss / meta.volume_step).to_integral_value(rounding=ROUND_FLOOR) * meta.volume_step
        volume = min(volume, (meta.volume_max / meta.volume_step).to_integral_value(rounding=ROUND_FLOOR) * meta.volume_step)
        if volume < meta.volume_min:
            raise Veto("BELOW_MINIMUM_VOLUME")
        if fixed_volume is not None:
            fixed_volume = number(fixed_volume)
            if fixed_volume > volume or fixed_volume < meta.volume_min or fixed_volume % meta.volume_step:
                raise Veto("RESERVED_VOLUME_NO_LONGER_SAFE")
            volume = fixed_volume
        risk, notional, margin = loss * volume, entry * meta.notional_per_price_unit_per_lot * volume, meta.margin_per_lot * volume
        if not all(math.isfinite(float(v)) for v in (risk, volume)):
            raise Veto("UNSUPPORTED_LEGACY_MIRROR_REPRESENTATION")
        totals = {s: [D(0), D(0)] for s in self.config.instruments}
        slots, pending_margin = 0, D(0)
        seen = set()
        represented = {}
        for exposure in account.exposures:
            if exposure.exposure_id in seen:
                raise Veto("DUPLICATE_EXPOSURE_EVIDENCE")
            seen.add(exposure.exposure_id)
            instrument = self._symbol(exposure.symbol)
            q, m = self._market(inputs, instrument, current)
            if instrument == symbol:
                raise Veto("SAME_INSTRUMENT_EXPOSURE")
            if exposure.reservation_intent_id:
                # Reconciliation must explicitly convert local reservations first.
                local = conn.execute("SELECT * FROM p2_reservations WHERE intent_id=?", (exposure.reservation_intent_id,)).fetchone()
                if (not local or exposure.kind != "POSITION" or local["symbol"] != instrument or
                        local["direction"] != exposure.direction):
                    raise Veto("RESERVATION_POSITION_IDENTITY_MISMATCH")
                if local["state"] not in {"PARTIAL", "CONVERTED", "RELEASED"}:
                    raise Veto("RESERVATION_RECONCILIATION_REQUIRED")
                represented[exposure.reservation_intent_id] = represented.get(exposure.reservation_intent_id, D(0)) + exposure.volume
            mark = q.bid if exposure.direction == "BUY" else q.ask
            if exposure.kind != "POSITION":
                if exposure.entry is None:
                    raise Veto("PENDING_ENTRY_REQUIRED")
                mark = exposure.entry
            if not (mark > exposure.stop_loss if exposure.direction == "BUY" else mark < exposure.stop_loss):
                raise Veto("STOP_RECONCILIATION_AMBIGUITY")
            remaining = (abs(mark - exposure.stop_loss) * m.value_per_price_unit_per_lot + m.commission_per_lot) * exposure.volume
            totals[instrument][0] += remaining
            totals[instrument][1] += mark * m.notional_per_price_unit_per_lot * exposure.volume
            slots += 1
        for reservation in conn.execute("SELECT * FROM p2_reservations WHERE state!='RELEASED'"):
            if reservation["intent_id"] == reserved_intent:
                continue
            instrument = reservation["symbol"]
            filled = D(reservation["filled_volume"])
            if filled and represented.get(reservation["intent_id"]) != filled:
                raise Veto("FILLED_EXPOSURE_RECONCILIATION_REQUIRED")
            if reservation["state"] == "CONVERTED":
                continue
            if instrument == symbol:
                raise Veto("SAME_INSTRUMENT_RESERVATION")
            if instrument not in totals:
                raise Veto("UNSUPPORTED_RESERVED_EXPOSURE")
            fraction = (D(reservation["volume"]) - filled) / D(reservation["volume"])
            if reservation["state"] == "AMBIGUOUS":
                fraction = D(1)
            totals[instrument][0] += D(reservation["risk"]) * fraction
            totals[instrument][1] += D(reservation["notional"]) * fraction
            pending_margin += D(reservation["margin"]) * fraction
            slots += 0 if filled else 1
        totals[symbol][0] += risk
        totals[symbol][1] += notional
        if slots + 1 > 3:
            raise Veto("POSITION_LIMIT")
        if account.used_margin + pending_margin + margin > account.equity * D("0.25"):
            raise Veto("MARGIN_LIMIT")
        if any(r > capital * D("0.0075") or n > capital * D("1.5") for r, n in totals.values()):
            raise Veto("INSTRUMENT_EXPOSURE")
        if sum(r for r, n in totals.values()) > capital * D("0.015") or sum(n for r, n in totals.values()) > capital * 3:
            raise Veto("PORTFOLIO_EXPOSURE")
        metals = sum(totals.get(s, [D(0)])[0] for s in ("XAUUSDm", "XAGUSDm"))
        if metals > capital * D("0.01") or totals.get("USOILm", [D(0)])[0] > capital * D("0.0075"):
            raise Veto("CORRELATION_LIMIT")
        return dict(symbol=symbol, direction=intent["direction"], risk=str(risk), notional=str(notional),
                    margin=str(margin), volume=str(volume), modeled_entry=str(entry), stop=str(rounded_stop),
                    nearest_tp=str(target), loss_per_lot=str(loss), reward_per_lot=str(reward))

    def revalidate_reserved(self, conn, request_id, inputs, current, *, begun=False):
        """P3 submission gate, inside the caller's serialized ledger transaction.

        Caller must commit a drawdown HALT even when this raises Veto. The exact
        reserved volume is checked, never resized or authorized by legacy mirrors.
        """
        request = conn.execute("SELECT * FROM p2_execution_requests WHERE execution_request_id=?", (request_id,)).fetchone()
        if not request:
            raise Veto("P2_REQUEST_REQUIRED")
        reservation = conn.execute("SELECT * FROM p2_reservations WHERE intent_id=?", (request['intent_id'],)).fetchone()
        decision = conn.execute("SELECT * FROM risk_decisions WHERE risk_decision_id=?", (request['decision_id'],)).fetchone()
        halt = conn.execute("SELECT * FROM halt_state WHERE singleton=1").fetchone()
        policy = conn.execute("SELECT policy_hash FROM p2_policy WHERE singleton=1").fetchone()[0]
        if halt['state'] != 'ACTIVE' or halt['version'] != decision['state_version']:
            raise Veto('HALTED_OR_INVALIDATED')
        if not reservation or reservation['decision_id'] != request['decision_id']:
            raise Veto('RESERVATION_REQUIRED')
        if reservation['state'] != ('SUBMISSION_BEGUN' if begun else 'RESERVED') or D(reservation['filled_volume']):
            raise Veto('RESERVATION_NOT_UNUSED')
        if current >= datetime.fromisoformat(reservation['expires_at']):
            raise Veto('APPROVAL_EXPIRED')
        if not policy == request['policy_hash'] == reservation['policy_hash'] == self.policy_hash:
            raise Veto('POLICY_VERSION_MISMATCH')
        if decision['decision'] != 'APPROVED' or decision['evidence_scope'] != 'P2_NON_EXECUTING':
            raise Veto('P2_APPROVAL_REQUIRED')
        if conn.execute("SELECT 1 FROM risk_decisions WHERE intent_id=? AND decision='REJECTED'", (request['intent_id'],)).fetchone():
            raise Veto('FINAL_VETO')
        row = conn.execute('SELECT * FROM order_intents WHERE intent_id=?', (request['intent_id'],)).fetchone()
        intent = json.loads(row['request'])
        signal = json.loads(conn.execute('SELECT payload FROM signals WHERE signal_id=?', (row['signal_id'],)).fetchone()[0])
        evidence = SafetyInputs.model_validate(inputs.model_dump() if isinstance(inputs, SafetyInputs) else inputs)
        with localcontext() as ctx:
            ctx.prec = 40
            allocation = self._calculate(conn, intent, signal, evidence, current,
                                         reserved_intent=request['intent_id'], fixed_volume=reservation['volume'])
            original = json.loads(decision['payload'])['allocation']
            if any(D(allocation[k]) > D(reservation[k]) for k in ('risk','notional','margin')):
                raise Veto('RESERVATION_INSUFFICIENT')
            if any(allocation[k] != original[k] for k in ('stop','nearest_tp','symbol','direction')):
                raise Veto('PROTECTIVE_LEVEL_CHANGE')
        return dict(request), intent, allocation, evidence

    def evaluate(self, intent_id, decision_id, inputs, *, current=None):
        if not isinstance(decision_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", decision_id):
            raise ValueError("Bounded canonical decision identity required")
        current = current or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Aware evaluation time required")
        current = current.astimezone(timezone.utc)
        with localcontext() as ctx, self.ledger.transaction() as conn:
            ctx.prec = 40
            row = conn.execute("SELECT * FROM order_intents WHERE intent_id=?", (intent_id,)).fetchone()
            if not row:
                raise KeyError("Unknown intent")
            previous = conn.execute("SELECT * FROM p2_evaluations WHERE decision_id=?", (decision_id,)).fetchone()
            if previous:
                if previous["intent_id"] != intent_id:
                    raise ValueError("Decision identity conflict")
                return json.loads(previous["payload"])
            intent = json.loads(row["request"])
            signal = json.loads(conn.execute("SELECT payload FROM signals WHERE signal_id=?", (row["signal_id"],)).fetchone()[0])
            result, evidence = {}, {}
            try:
                halt = conn.execute("SELECT * FROM halt_state WHERE singleton=1").fetchone()
                if halt["state"] != "ACTIVE":
                    raise Veto("HALTED")
                policy = conn.execute("SELECT policy_hash FROM p2_policy WHERE singleton=1").fetchone()[0]
                if policy != self.policy_hash:
                    raise Veto("POLICY_VERSION_MISMATCH")
                if conn.execute("SELECT 1 FROM risk_decisions WHERE intent_id=? AND decision='REJECTED'", (intent_id,)).fetchone():
                    raise Veto("FINAL_VETO")
                if conn.execute("SELECT 1 FROM p2_reservations WHERE intent_id=? AND state!='RELEASED'", (intent_id,)).fetchone():
                    raise Veto("EXISTING_RESERVATION")
                inputs = SafetyInputs.model_validate(inputs.model_dump() if isinstance(inputs, SafetyInputs) else inputs)
                evidence = inputs.model_dump(mode="json")
                result = self._calculate(conn, intent, signal, inputs, current)
                reason = "APPROVED"
            except (ValueError, ValidationError, KeyError, DecimalException, OverflowError, TypeError) as exc:
                reason = str(exc) if isinstance(exc, Veto) else "INVALID_OR_MISSING_EVIDENCE"
                result = {}
            verdict = "APPROVED" if result else "REJECTED"
            halt_version = conn.execute("SELECT version FROM halt_state WHERE singleton=1").fetchone()[0]
            payload = dict(decision_id=decision_id, intent_id=intent_id, decision=verdict, reason=reason,
                           policy_version=self.version, base_policy_version=VERSION, policy_hash=self.policy_hash, evaluated_at=current.isoformat(),
                           evidence=evidence, allocation=result, execution_enabled=False)
            source_policy=conn.execute('SELECT revision,payload_hash FROM p4_source_configuration ORDER BY revision DESC LIMIT 1').fetchone()
            if source_policy:
                payload['source_policy']=dict(source_policy)
            conn.execute("INSERT INTO risk_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (decision_id, intent_id, verdict, canonical([reason]), float(result.get("risk", 0)),
                          float(result.get("volume", 0)), halt_version, current.isoformat(), reason,
                          "p2-safety", self.version, "P2_NON_EXECUTING", canonical(payload), hashed(payload)))
            conn.execute("INSERT INTO p2_evaluations VALUES(?,?,?,?,?)",
                         (decision_id, intent_id, self.policy_hash, hashed(evidence), canonical(payload)))
            if result:
                conn.execute("INSERT INTO p2_reservations(intent_id,decision_id,symbol,direction,risk,notional,margin,volume,expires_at,policy_hash,state) VALUES(?,?,?,?,?,?,?,?,?,?,'RESERVED') ON CONFLICT(intent_id) DO UPDATE SET decision_id=excluded.decision_id,risk=excluded.risk,notional=excluded.notional,margin=excluded.margin,volume=excluded.volume,expires_at=excluded.expires_at,policy_hash=excluded.policy_hash,state='RESERVED',filled_volume='0',terminal_evidence_id=NULL",
                             (intent_id, decision_id, result["symbol"], result["direction"], result["risk"], result["notional"],
                              result["margin"], result["volume"], (current + timedelta(seconds=60)).isoformat(), self.policy_hash))
            self.ledger.audit(conn, "P2_SAFETY_DECISION", intent_id, {"decision_id": decision_id, "decision": verdict})
            return payload

    def reset_halt(self, inputs, *, operator_id, reason, current=None):
        """Trusted control-plane operation; no automatic resume and no HTTP unlock."""
        if not operator_id.strip() or not reason.strip():
            raise ValueError("Explicit operator identity and reset reason required")
        current = current or datetime.now(timezone.utc)
        evidence = SafetyInputs.model_validate(inputs)
        with self.ledger.transaction() as conn:
            self.ledger._check_account(conn, evidence.account)
            if (evidence.account.account_key != self.config.approved_account_key or
                    not evidence.account.reconciled or not evidence.account.complete):
                raise ValueError("Reconciled approved account required")
            for timestamp in (evidence.account.observed_at, evidence.account.positions_at, evidence.account.orders_at):
                fresh(timestamp, current, 5)
            if conn.execute("SELECT 1 FROM p2_reservations WHERE state IN ('SUBMISSION_BEGUN','AMBIGUOUS','PARTIAL')").fetchone():
                raise ValueError("Outstanding submission reconciliation required")
            self._baselines(conn, evidence.account, current)
            conn.execute("UPDATE halt_state SET state='ACTIVE',version=version+1,reason=?,updated_at=? WHERE singleton=1", (reason, current.isoformat()))
            self.ledger.audit(conn, "P2_OPERATOR_RESET", None, {"operator_id": operator_id, "reason": reason, "evidence_id": evidence.account.evidence_id})

    def eligible_request(self, intent_id, decision_id, execution_request_id=None, *, current=None):
        current = current or datetime.now(timezone.utc)
        if execution_request_id is not None and not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", execution_request_id):
            raise ValueError("Bounded canonical request identity required")
        with self.ledger.transaction() as conn:
            self.ledger._check_account(conn)
            reservation = conn.execute("SELECT * FROM p2_reservations WHERE intent_id=? AND decision_id=?", (intent_id, decision_id)).fetchone()
            if not reservation or reservation["state"] != "RESERVED" or current >= datetime.fromisoformat(reservation["expires_at"]):
                raise ValueError("No current unsubmitted reservation")
            decision = conn.execute("SELECT * FROM risk_decisions WHERE risk_decision_id=?", (decision_id,)).fetchone()
            halt = conn.execute("SELECT * FROM halt_state WHERE singleton=1").fetchone()
            policy = conn.execute("SELECT policy_hash FROM p2_policy WHERE singleton=1").fetchone()[0]
            if halt["state"] != "ACTIVE" or halt["version"] != decision["state_version"] or policy != reservation["policy_hash"] or policy != self.policy_hash:
                raise ValueError("HALT or policy version invalidated approval")
            if conn.execute("SELECT 1 FROM risk_decisions WHERE intent_id=? AND decision='REJECTED'", (intent_id,)).fetchone():
                raise ValueError("Final veto invalidated request eligibility")
            # Approval TTL is not a substitute for individual evidence freshness.
            payload = json.loads(decision["payload"])
            source_policy=conn.execute('SELECT revision,payload_hash FROM p4_source_configuration ORDER BY revision DESC LIMIT 1').fetchone()
            if source_policy and payload.get('source_policy')!=dict(source_policy):
                raise ValueError('Source policy revision invalidated approval')
            from .source_registry import check_signal
            parent=conn.execute('SELECT signal_id FROM order_intents WHERE intent_id=?',(intent_id,)).fetchone()
            check_signal(conn,parent[0],current=current)
            evidence = SafetyInputs.model_validate(payload["evidence"])
            fresh(evidence.account.observed_at, current, 5)
            fresh(evidence.account.positions_at, current, 5)
            fresh(evidence.account.orders_at, current, 5)
            for symbol in evidence.quotes:
                self._market(evidence, symbol, current)
            identity = execution_request_id or hashed([intent_id, decision_id, "p2-request"])
            prior = conn.execute("SELECT * FROM p2_execution_requests WHERE execution_request_id=? OR decision_id=?", (identity, decision_id)).fetchone()
            if prior:
                if (prior["execution_request_id"], prior["intent_id"], prior["decision_id"]) != (identity,intent_id,decision_id):
                    raise ValueError("Execution request identity conflict")
                return dict(prior)
            conn.execute("INSERT INTO p2_execution_requests VALUES(?,?,?,?,?,'ELIGIBLE_NOT_SUBMITTED',?)",
                         (identity, intent_id, decision_id, self.ledger.account.key, policy, current.isoformat()))
            return dict(conn.execute("SELECT * FROM p2_execution_requests WHERE execution_request_id=?", (identity,)).fetchone())

    def expire(self, *, current=None):
        current = current or datetime.now(timezone.utc)
        with self.ledger.transaction() as conn:
            rows = conn.execute("SELECT intent_id,expires_at FROM p2_reservations WHERE state='RESERVED'").fetchall()
            released = [r["intent_id"] for r in rows if current >= datetime.fromisoformat(r["expires_at"])]
            for identity in released:
                conn.execute("UPDATE p2_reservations SET state='RELEASED',terminal_evidence_id='PROVEN_NOT_SUBMITTED_TTL' WHERE intent_id=?", (identity,))
                self.ledger.audit(conn, "P2_RESERVATION_EXPIRED", identity, {})
            return released

    def observe_reservation(self, intent_id, *, state, filled_volume, evidence_id, terminal=False):
        """Fixture-safe reconciliation contract only; never sends broker actions."""
        if not self.ledger.account or self.ledger.account.evidence_source != "FIXTURE":
            raise ValueError("P2 observation simulation requires FIXTURE account; P3 attestation is unavailable")
        if state not in {"SUBMISSION_BEGUN", "AMBIGUOUS", "PARTIAL", "CONVERTED", "RELEASED"} or not evidence_id.strip():
            raise ValueError("Explicit reconciliation evidence required")
        filled = D(str(filled_volume))
        if not filled.is_finite() or filled < 0:
            raise ValueError("Invalid fill amount")
        with self.ledger.transaction() as conn:
            payload = dict(intent_id=intent_id, state=state, filled_volume=str(filled), evidence_id=evidence_id, terminal=terminal)
            prior = conn.execute("SELECT payload_hash FROM p2_reservation_events WHERE evidence_id=?", (evidence_id,)).fetchone()
            if prior:
                if prior[0] != hashed(payload):
                    raise ValueError("Reservation observation conflict")
                return
            row = conn.execute("SELECT * FROM p2_reservations WHERE intent_id=?", (intent_id,)).fetchone()
            if not row or row["state"] in {"RELEASED", "CONVERTED"} or filled < D(row["filled_volume"]) or filled > D(row["volume"]):
                raise ValueError("Invalid reservation transition")
            if state == "PARTIAL" and not 0 < filled < D(row["volume"]):
                raise ValueError("Partial fill must leave a remainder")
            if state == "CONVERTED" and filled <= 0:
                raise ValueError("Conversion requires a fill; terminal evidence releases any unfilled remainder")
            if state in {"RELEASED", "CONVERTED"} and terminal is not True:
                raise ValueError("Terminal reconciliation evidence required")
            if state == "SUBMISSION_BEGUN" and (row["state"] != "RESERVED" or filled != 0):
                raise ValueError("Submission cannot restart")
            if state == "RELEASED" and filled:
                raise ValueError("Filled exposure must be reconciled, not released")
            conn.execute("UPDATE p2_reservations SET state=?,filled_volume=?,terminal_evidence_id=? WHERE intent_id=?",
                         (state, str(filled), evidence_id, intent_id))
            conn.execute("INSERT INTO p2_reservation_events VALUES(?,?,?,?)", (evidence_id, intent_id, canonical(payload), hashed(payload)))
            self.ledger.audit(conn, "P2_RESERVATION_OBSERVATION", intent_id, {"state": state, "filled_volume": str(filled), "evidence_id": evidence_id})
