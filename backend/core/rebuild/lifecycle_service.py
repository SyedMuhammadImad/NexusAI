"""Exact-ID P1 persistence. No broker adapter, order dispatch, or risk engine."""
import hashlib
import json
from datetime import datetime, timezone

from services.signal_parser import PARSER_VERSION, SignalParser
from services.chat_import_service import historical_parser_text

from .ledger import Ledger, canonical, hashed, now
from .lifecycle_contracts import CanonicalSignal, ExecutionRequest, SafetyDecision, SourceEvent, TradeIntent


class LifecycleService:
    def __init__(self, ledger: Ledger, *, fixture_mode=False, p2=False):
        if fixture_mode and (not ledger.account or ledger.account.evidence_source != "FIXTURE"):
            raise ValueError("Fixture boundary requires an explicit FIXTURE account")
        self.ledger = ledger
        self.fixture_mode = fixture_mode
        self.p2 = p2

    def save_source(self, event: SourceEvent):
        event = SourceEvent.model_validate(event.model_dump())
        payload = event.model_dump(mode="json")
        with self.ledger.transaction() as conn:
            from .source_registry import rule_for
            rule_for(conn,event)
            previous = conn.execute("SELECT * FROM source_events WHERE source_event_id=? OR (source_type=? AND source_id=? AND source_message_id=?)",
                                    (event.source_event_id, event.source_type, event.source_id, event.source_message_id)).fetchone()
            if previous:
                original = json.loads(previous["payload"])
                # A retry does not rejuvenate the first receipt or overwrite evidence.
                if {k: v for k, v in original.items() if k != "received_at"} != {k: v for k, v in payload.items() if k != "received_at"}:
                    raise ValueError("Immutable source event conflict; explicit revision required")
                return dict(previous)
            conn.execute("INSERT INTO source_events VALUES(?,?,?,?,?,?,?,?,?)",
                         (event.source_event_id, event.source_type, event.source_id, event.source_message_id,
                          hashlib.sha256(event.raw_text.encode()).hexdigest(), canonical(payload), hashed(payload),
                          "RECEIVED" if event.source_time_utc else "TIME_UNRESOLVED", now()))
            self.ledger.audit(conn, "SOURCE_EVENT_RECORDED", None, {"source_event_id": event.source_event_id})
            return dict(conn.execute("SELECT * FROM source_events WHERE source_event_id=?", (event.source_event_id,)).fetchone())

    def validate_source(self, source_event_id: str):
        with self.ledger.connect() as conn:
            row = conn.execute("SELECT payload FROM source_events WHERE source_event_id=?", (source_event_id,)).fetchone()
        if not row:
            raise KeyError("Unknown source event")
        event = SourceEvent.model_validate_json(row[0])
        if event.source_time_utc is None:
            raise ValueError("Unresolved timestamp evidence cannot produce a validated signal")
        text = historical_parser_text(event.raw_text) if event.source_type == "HISTORICAL_WHATSAPP" else event.raw_text
        parsed = SignalParser().parse(text=text, group_id=event.source_id, sender_id=event.sender_id,
                                      message_id=event.source_message_id, message_timestamp=event.source_time_utc.timestamp(),
                                      received_timestamp=event.received_at.timestamp(), p2=self.p2)
        if parsed.rejection_reasons:
            raise ValueError(", ".join(parsed.rejection_reasons))
        signal = CanonicalSignal(
            signal_id=hashed([event.source_event_id, "signal.v2", parsed.parser_version]), parser_version=parsed.parser_version,
            source_event_id=event.source_event_id, source_type=event.source_type,
            source_id=event.source_id, source_message_id=event.source_message_id,
            source_timestamp=event.source_time_utc.timestamp(), received_timestamp=event.received_at.timestamp(),
            parsed_timestamp=datetime.now(timezone.utc).timestamp(), symbol=parsed.instrument,
            direction=parsed.direction, entry=parsed.entry_price, stop_loss=parsed.stop_loss,
            take_profit=tuple(t for t in (parsed.take_profit_1, parsed.take_profit_2, parsed.take_profit_3) if t is not None),
            raw_source_hash=hashlib.sha256(event.raw_text.encode()).hexdigest(),
            entry_type=parsed.entry_type, requested_risk_pct=parsed.requested_risk_pct)
        signal_id = self.ledger.save_signal(signal)
        with self.ledger.connect() as conn:
            return json.loads(conn.execute("SELECT payload FROM signals WHERE signal_id=?", (signal_id,)).fetchone()[0])

    def create_intent(self, request: TradeIntent):
        request = TradeIntent.model_validate(request.model_dump())
        return self.ledger.create_intent(request)

    def record_decision(self, decision: SafetyDecision):
        decision = SafetyDecision.model_validate(decision.model_dump())
        if decision.evidence_scope == "FIXTURE":
            if not self.fixture_mode or decision.policy_id != "p1-fixture" or decision.policy_version != "1":
                raise ValueError("Only the explicitly scoped P1 fixture boundary may record fixture decisions")
        elif decision.policy_id != "p1-disabled" or decision.policy_version != "1":
            raise ValueError("P1 default is the disabled policy, not the P2 safety engine")
        payload = decision.model_dump(mode="json")
        with self.ledger.transaction() as conn:
            self.ledger._check_account(conn)
            parent = conn.execute("SELECT signal_id FROM order_intents WHERE intent_id=?", (decision.intent_id,)).fetchone()
            if parent and decision.decision == "APPROVED":
                self.ledger._reject_historical_execution(conn, parent[0])
            previous = conn.execute("SELECT * FROM risk_decisions WHERE risk_decision_id=?", (decision.safety_decision_id,)).fetchone()
            if previous:
                if previous["payload_hash"] != hashed(payload):
                    prior = json.loads(previous["payload"]) if previous["payload"] else {}
                    same_rejection = (decision.evidence_scope == "P1_DISABLED" and
                                      {k: v for k, v in prior.items() if k != "decision_timestamp"} ==
                                      {k: v for k, v in payload.items() if k != "decision_timestamp"})
                    if not same_rejection:
                        raise ValueError("Safety decision identity conflict")
                return dict(previous)
            intent = conn.execute("SELECT * FROM order_intents WHERE intent_id=?", (decision.intent_id,)).fetchone()
            if not intent or json.loads(intent["request"]).get("contract_version") != "intent.v2":
                raise ValueError("Decision requires an exact canonical intent")
            if decision.decision_timestamp < datetime.fromisoformat(intent["created_at"]):
                raise ValueError("Decision cannot predate intent creation")
            if decision.decision_timestamp > datetime.now(timezone.utc):
                raise ValueError("Decision timestamp cannot be in the future")
            if decision.decision == "APPROVED":
                if conn.execute("SELECT 1 FROM risk_decisions WHERE intent_id=? AND decision='REJECTED'", (decision.intent_id,)).fetchone():
                    raise ValueError("A rejected intent cannot be overridden")
                if decision.approved_volume != intent["requested_volume"]:
                    raise ValueError("Fixture approved volume must match the proposed intent")
            version = conn.execute("SELECT version FROM halt_state WHERE singleton=1").fetchone()[0]
            conn.execute("INSERT INTO risk_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (decision.safety_decision_id, decision.intent_id, decision.decision,
                          canonical(decision.reason_codes), decision.risk_budget, decision.approved_volume,
                          version, decision.decision_timestamp.isoformat(), decision.explanation,
                          decision.policy_id, decision.policy_version, decision.evidence_scope, canonical(payload), hashed(payload)))
            self.ledger.audit(conn, "P1_SAFETY_DECISION_RECORDED", decision.intent_id,
                              {"safety_decision_id": decision.safety_decision_id, "scope": decision.evidence_scope})
            return dict(conn.execute("SELECT * FROM risk_decisions WHERE risk_decision_id=?", (decision.safety_decision_id,)).fetchone())

    def reject_intent(self, intent_id: str, decision_id: str):
        with self.ledger.connect() as conn:
            previous = conn.execute("SELECT payload FROM risk_decisions WHERE risk_decision_id=?", (decision_id,)).fetchone()
        if previous:
            decision = SafetyDecision.model_validate_json(previous[0])
            if decision.intent_id != intent_id or decision.evidence_scope != "P1_DISABLED":
                raise ValueError("Decision id belongs to another intent or policy")
        else:
            decision = SafetyDecision(safety_decision_id=decision_id, intent_id=intent_id, decision="REJECTED",
                                      reason_codes=("P1_EXECUTION_DISABLED",), explanation="P1 has no qualified safety engine or execution path",
                                      policy_id="p1-disabled", policy_version="1", decision_timestamp=datetime.now(timezone.utc),
                                      evidence_scope="P1_DISABLED", risk_budget=0., approved_volume=0.)
        return self.record_decision(decision)

    def create_execution_request(self, request: ExecutionRequest):
        request = ExecutionRequest.model_validate(request.model_dump())
        if not self.fixture_mode:
            raise ValueError("P1 execution requests are fixture-only; default application remains disabled")
        payload = request.model_dump()
        with self.ledger.transaction() as conn:
            self.ledger._check_account(conn)
            parent = conn.execute("SELECT signal_id FROM order_intents WHERE intent_id=?", (request.intent_id,)).fetchone()
            if parent:
                self.ledger._reject_historical_execution(conn, parent[0])
            decision = conn.execute("SELECT * FROM risk_decisions WHERE risk_decision_id=? AND intent_id=?",
                                    (request.safety_decision_id, request.intent_id)).fetchone()
            if not decision or decision["decision"] != "APPROVED" or decision["evidence_scope"] != "FIXTURE":
                raise ValueError("Exact approved fixture safety decision required")
            if conn.execute("SELECT 1 FROM risk_decisions WHERE intent_id=? AND decision='REJECTED'", (request.intent_id,)).fetchone():
                raise ValueError("Rejected intent cannot produce an execution request")
            previous = conn.execute("SELECT * FROM execution_requests WHERE execution_request_id=? OR intent_id=?",
                                    (request.execution_request_id, request.intent_id)).fetchone()
            if previous:
                if previous["payload_hash"] != hashed(payload):
                    raise ValueError("Execution request identity conflict")
                return dict(previous)
            intent = conn.execute("SELECT * FROM order_intents WHERE intent_id=?", (request.intent_id,)).fetchone()
            conn.execute("INSERT INTO execution_requests VALUES(?,?,?,?,?,?,?,?,?)",
                         (request.execution_request_id, request.intent_id, request.safety_decision_id,
                          intent["client_order_id"], self.ledger.account.key, "RECORDED_NOT_SUBMITTED", "FIXTURE", hashed(payload), now()))
            self.ledger.audit(conn, "FIXTURE_EXECUTION_REQUEST_RECORDED", request.intent_id,
                              {"execution_request_id": request.execution_request_id, "execution_enabled": False})
            return dict(conn.execute("SELECT * FROM execution_requests WHERE execution_request_id=?", (request.execution_request_id,)).fetchone())

    def trace(self, source_event_id: str):
        with self.ledger.connect() as conn:
            # One read snapshot prevents mixing states from concurrent writers.
            conn.execute("BEGIN")
            source = conn.execute("SELECT * FROM source_events WHERE source_event_id=?", (source_event_id,)).fetchone()
            if not source:
                raise KeyError("Unknown source event")
            signals = conn.execute("SELECT * FROM signals WHERE source_event_id=?", (source_event_id,)).fetchall()
            intents = conn.execute("SELECT i.* FROM order_intents i JOIN signals s ON s.signal_id=i.signal_id WHERE s.source_event_id=? ORDER BY i.created_at,i.intent_id", (source_event_id,)).fetchall()
            paths = []
            for intent in intents:
                def rows(sql):
                    return [dict(r) for r in conn.execute(sql, (intent["intent_id"],))]
                paths.append({"intent": dict(intent),
                              "safety_decisions": rows("SELECT * FROM risk_decisions WHERE intent_id=? ORDER BY timestamp,risk_decision_id"),
                              "execution_requests": rows("SELECT * FROM execution_requests WHERE intent_id=?"),
                              "p2_execution_requests": rows("SELECT * FROM p2_execution_requests WHERE intent_id=?"),
                              "p2_reservations": rows("SELECT * FROM p2_reservations WHERE intent_id=?"),
                              "p3_attempts": rows("SELECT * FROM p3_attempts WHERE intent_id=?"),
                              "p3_observations": rows("SELECT o.*,l.attempt_id FROM p3_observations o JOIN p3_observation_links l ON l.observation_id=o.observation_id JOIN p3_attempts a ON a.attempt_id=l.attempt_id WHERE a.intent_id=? ORDER BY o.observed_at,o.observation_id"),
                              "p3_observation_heads": rows("SELECT h.* FROM p3_observation_heads h JOIN p3_observation_links l ON l.observation_id=h.observation_id JOIN p3_attempts a ON a.attempt_id=l.attempt_id WHERE a.intent_id=?"),
                              "p3_events": rows("SELECT e.* FROM p3_events e JOIN p3_attempts a ON a.attempt_id=e.attempt_id WHERE a.intent_id=? ORDER BY e.created_at,e.event_id"),
                              "p3_orders": rows("SELECT o.* FROM p3_orders o JOIN p3_attempts a ON a.attempt_id=o.attempt_id WHERE a.intent_id=?"),
                              "p3_deals": rows("SELECT d.* FROM p3_deals d JOIN p3_orders o ON o.broker_order_id=d.broker_order_id JOIN p3_attempts a ON a.attempt_id=o.attempt_id WHERE a.intent_id=?"),
                              "p3_positions": rows("SELECT p.* FROM p3_positions p JOIN p3_attempts a ON a.attempt_id=p.attempt_id WHERE a.intent_id=?"),
                              "p3_exit_orders": rows("SELECT o.* FROM p3_exit_orders o JOIN p3_positions p ON p.broker_position_id=o.broker_position_id JOIN p3_attempts a ON a.attempt_id=p.attempt_id WHERE a.intent_id=?"),
                              "p3_exit_deals": rows("SELECT d.* FROM p3_exit_deals d JOIN p3_positions p ON p.broker_position_id=d.broker_position_id JOIN p3_attempts a ON a.attempt_id=p.attempt_id WHERE a.intent_id=?"),
                              "broker_orders": rows("SELECT * FROM broker_orders WHERE intent_id=?"),
                              "broker_deals": rows("SELECT d.* FROM broker_deals d JOIN broker_orders o ON o.broker_order_id=d.broker_order_id WHERE o.intent_id=?"),
                              "positions": rows("SELECT * FROM positions WHERE originating_intent=?"),
                              "outcomes": rows("SELECT t.* FROM trade_outcomes t JOIN positions p ON p.broker_position_id=t.position_id WHERE p.originating_intent=?")})
            historical = conn.execute("SELECT * FROM historical_links WHERE source_event_id=? ORDER BY import_id,message_id", (source_event_id,)).fetchall()
            return {"source_event": dict(source), "signals": [dict(s) for s in signals], "lifecycles": paths,
                    "historical_links": [dict(r) for r in historical],
                    "execution_enabled": False, "broker_provenance": "UNAVAILABLE", "qualification": "NOT_QUALIFIED"}
