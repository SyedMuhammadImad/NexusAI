"""Separate lifecycle database. Legacy records are evidence, not imported broker truth."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import Signal
from .migration_runner import migrate


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def hashed(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class IntentRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, strict=True)
    client_order_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,64}$")
    signal_id: str = Field(min_length=1)
    action: Literal["OPEN", "MODIFY", "PARTIAL_CLOSE", "CLOSE", "EMERGENCY_CLOSE", "ADOPT"]
    symbol: str = Field(min_length=1)
    direction: Literal["BUY", "SELL"]
    volume: float = Field(gt=0)
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    target_position_id: str | None = None

    @model_validator(mode="after")
    def target(self):
        if (self.action == "OPEN") != (self.target_position_id is None):
            raise ValueError("Only OPEN omits an explicit position ID")
        if self.target_position_id is not None and (not self.target_position_id.strip() or self.target_position_id != self.target_position_id.strip()):
            raise ValueError("Target position identity cannot be blank or padded")
        if self.entry is None and getattr(self, "contract_version", None) == "intent.v2" and self.entry_type == "MARKET":
            return self
        if self.entry is None or not (self.stop_loss < self.entry < self.take_profit if self.direction == "BUY" else self.take_profit < self.entry < self.stop_loss):
            raise ValueError("Invalid level geometry")
        return self


class DemoAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    account_id: str = Field(min_length=1, max_length=128)
    server: str = Field(min_length=1, max_length=128)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    mode: Literal["DEMO"] = "DEMO"
    evidence_source: Literal["FIXTURE", "MT5_DEMO"]

    @model_validator(mode="after")
    def valid_identity(self):
        if any(not value.strip() or value!=value.strip() for value in (self.account_id,self.server)):
            raise ValueError("Account and server identities cannot be blank or padded")
        return self

    @property
    def key(self):
        return hashed(self.model_dump())


class Ledger:
    def __init__(self, path: Path, *, account: DemoAccount | None = None):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            migrate(conn)
        self.account = DemoAccount.model_validate(account.model_dump()) if account else None
        if self.account:
            with self.transaction() as conn:
                bound = conn.execute("SELECT account_key FROM account_binding WHERE singleton=1").fetchone()
                if bound and bound[0] != self.account.key:
                    raise ValueError("Database belongs to a different broker account")
                if not bound:
                    populated = any(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                                    for table in ("order_intents", "broker_orders", "broker_deals", "positions"))
                    if populated:
                        raise ValueError("Unbound legacy lifecycle records require explicit reviewed migration")
                    conn.execute("INSERT INTO account_binding VALUES(1,?,?,?)", (self.account.key, canonical(self.account.model_dump()), now()))

    def _check_account(self, conn, evidence=None):
        bound = conn.execute("SELECT account_key FROM account_binding WHERE singleton=1").fetchone()
        if not self.account or not bound or bound[0] != self.account.key:
            raise ValueError("Explicit matching demo-account binding required")
        if evidence is not None and evidence.account_key != bound[0]:
            raise ValueError("Broker evidence belongs to a different account")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def save_signal(self, signal: Signal):
        from .lifecycle_contracts import CanonicalSignal

        model = CanonicalSignal if signal.contract_version == "signal.v2" else Signal
        signal = model.model_validate(signal.model_dump())
        payload = signal.model_dump(mode="json")
        with self.transaction() as conn:
            from .source_registry import active, rule_for
            if active(conn) is not None:
                from .lifecycle_contracts import SourceEvent
                event_row=conn.execute('SELECT payload FROM source_events WHERE source_event_id=?',
                                      (getattr(signal,'source_event_id',None),)).fetchone()
                if not event_row: raise ValueError('P4_CANONICAL_SOURCE_REQUIRED')
                event=SourceEvent.model_validate_json(event_row[0])
                rule_for(conn,event)
                if (event.source_time_utc is None or signal.source_timestamp!=event.source_time_utc.timestamp()
                        or signal.received_timestamp!=event.received_at.timestamp()):
                    raise ValueError('P4_SIGNAL_TIMESTAMP_LINEAGE_MISMATCH')
                if event.metadata.get('adapter_version')=='p4-v1' and signal.parser_version!='deterministic_v3_p2':
                    raise ValueError('P4_SIGNAL_PARSER_VERSION_MISMATCH')
                from services.signal_parser import SignalParser
                from services.chat_import_service import historical_parser_text
                raw=historical_parser_text(event.raw_text) if event.source_type=='HISTORICAL_WHATSAPP' else event.raw_text
                parsed=SignalParser().parse(text=raw,group_id=event.source_id,sender_id=event.sender_id,
                    message_id=event.source_message_id,message_timestamp=event.source_time_utc.timestamp() if event.source_time_utc else None,
                    received_timestamp=event.received_at.timestamp(),p2=True)
                if parsed.rejection_reasons or (signal.symbol,signal.direction,signal.entry,signal.stop_loss,list(signal.take_profit),signal.entry_type,signal.requested_risk_pct)!=(
                    parsed.instrument,parsed.direction,parsed.entry_price,parsed.stop_loss,
                    [t for t in (parsed.take_profit_1,parsed.take_profit_2,parsed.take_profit_3) if t is not None],parsed.entry_type,parsed.requested_risk_pct):
                    raise ValueError('P4_SIGNAL_MUST_MATCH_VALIDATED_SOURCE')
            existing = conn.execute("SELECT * FROM signals WHERE signal_id=? OR (source_type=? AND source_id=? AND source_message_id=?)",
                                    (signal.signal_id, signal.source_type, signal.source_id, signal.source_message_id)).fetchone()
            if existing:
                if existing["payload_hash"] != hashed(payload):
                    prior = json.loads(existing["payload"])
                    for key in ("received_timestamp", "parsed_timestamp"):
                        prior.pop(key, None)
                    comparable = {k:v for k,v in payload.items() if k not in {"received_timestamp", "parsed_timestamp"}}
                    if prior != comparable:
                        raise ValueError("Immutable signal conflict: review a new revision explicitly")
                return existing["signal_id"]
            conn.execute("INSERT INTO signals(signal_id,source_type,source_id,source_message_id,payload_hash,payload,source_timestamp,received_timestamp,parser_version,status,source_event_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (signal.signal_id, signal.source_type,
                         signal.source_id, signal.source_message_id, hashed(payload), canonical(payload),
                         signal.source_timestamp, signal.received_timestamp, signal.parser_version, signal.validation_status,
                         getattr(signal, "source_event_id", None)))
        return signal.signal_id

    def create_intent(self, request: IntentRequest):
        from .lifecycle_contracts import TradeIntent

        model = TradeIntent if getattr(request, "contract_version", None) == "intent.v2" else IntentRequest
        request = model.model_validate(request.model_dump())
        payload = request.model_dump(mode="json")
        with self.transaction() as conn:
            self._check_account(conn)
            self._reject_historical_execution(conn, request.signal_id)
            from .source_registry import check_signal
            check_signal(conn,request.signal_id)
            identity = hashed([self.account.key, request.client_order_id])
            existing = conn.execute("SELECT * FROM order_intents WHERE client_order_id=?", (request.client_order_id,)).fetchone()
            if existing:
                if existing["request_hash"] != hashed(payload):
                    raise ValueError("Client key reused with different request")
                return dict(existing)
            signal = conn.execute("SELECT payload FROM signals WHERE signal_id=?", (request.signal_id,)).fetchone()
            if not signal:
                raise ValueError("Persist signal before intent")
            signal = json.loads(signal[0])
            if isinstance(request, TradeIntent):
                if signal.get("contract_version") != "signal.v2":
                    raise ValueError("Canonical intent requires a V2 source-linked signal")
                if (request.entry_type != signal["entry_type"]
                        or list(request.take_profit_targets) != signal["take_profit"]
                        or request.requested_risk_pct != signal.get("requested_risk_pct")):
                    raise ValueError("Intent semantics must preserve the canonical signal")
            if signal["symbol"] != request.symbol or signal["direction"] != request.direction:
                raise ValueError("Intent does not match source signal")
            if request.action == "OPEN" and (request.entry != signal["entry"] or request.stop_loss != signal["stop_loss"] or request.take_profit not in signal["take_profit"]):
                raise ValueError("OPEN levels must match the immutable source signal")
            if request.target_position_id:
                position = conn.execute("SELECT * FROM positions WHERE broker_position_id=?", (request.target_position_id,)).fetchone()
                if not position or (position["symbol"],position["direction"]) != (request.symbol,request.direction):
                    raise ValueError("Target must be an explicitly owned matching broker position")
            if conn.execute("SELECT 1 FROM order_intents WHERE signal_id=? AND action=? AND coalesce(target_position_id,'')=?",
                            (request.signal_id, request.action, request.target_position_id or "")).fetchone():
                raise ValueError("Logical request already has a client key")
            conn.execute("INSERT INTO order_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (identity, request.signal_id,
                         request.client_order_id, hashed(payload), canonical(payload), request.action,
                         request.symbol, request.target_position_id, "CREATED", now(),
                         request.volume, request.entry, request.stop_loss, request.take_profit))
            self.audit(conn, "INTENT_CREATED", identity, {"client_order_id": request.client_order_id})
            return dict(conn.execute("SELECT * FROM order_intents WHERE intent_id=?", (identity,)).fetchone())

    @staticmethod
    def _reject_historical_execution(conn, signal_id):
        if conn.execute("SELECT 1 FROM signals WHERE signal_id=? AND source_event_id IS NOT NULL AND source_type IN ('HISTORICAL_WHATSAPP','SCREENSHOT')", (signal_id,)).fetchone():
            raise ValueError("Historical sources cannot enter the execution lifecycle")

    @staticmethod
    def audit(conn, event_type, intent_id, payload):
        conn.execute("INSERT INTO audit_events(event_id,event_type,intent_id,payload,timestamp) VALUES(?,?,?,?,?)",
                     (str(uuid.uuid4()), event_type, intent_id, canonical(payload), now()))

    def halt(self, reason: str):
        if not reason.strip():
            raise ValueError("Halt reason required")
        with self.transaction() as conn:
            conn.execute("UPDATE halt_state SET state='HALTED',version=version+1,reason=?,updated_at=? WHERE singleton=1", (reason, now()))
            self.audit(conn, "HALTED", None, {"reason": reason})
        return self.status()

    def status(self):
        with self.connect() as conn:
            state = dict(conn.execute("SELECT * FROM halt_state WHERE singleton=1").fetchone())
            binding = conn.execute("SELECT account_key FROM account_binding WHERE singleton=1").fetchone()
            counts = {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                      for table in ("signals", "order_intents", "risk_decisions", "broker_orders", "broker_deals", "positions", "trade_outcomes", "quarantine")}
        return {"halt": state, "counts": counts, "execution_enabled": False, "account_bound": bool(binding),
                "broker_provenance": "UNAVAILABLE", "qualification": "NOT_QUALIFIED"}

    def record_order(self, evidence: "BrokerOrder"):
        evidence = BrokerOrder.model_validate(evidence.model_dump())
        with self.transaction() as conn:
            self._check_account(conn, evidence)
            intent = conn.execute("SELECT * FROM order_intents WHERE client_order_id=?", (evidence.client_order_id,)).fetchone()
            if not intent:
                raise ValueError("Unknown client key: no symbol fallback permitted")
            if Decimal(str(evidence.requested_volume)) != Decimal(str(intent["requested_volume"])):
                raise ValueError("Order volume differs from durable intent")
            if conn.execute("SELECT 1 FROM order_observations WHERE observation_hash=?", (hashed(evidence.model_dump()),)).fetchone():
                return dict(conn.execute("SELECT * FROM broker_orders WHERE broker_order_id=?", (evidence.broker_order_id,)).fetchone())
            existing = conn.execute("SELECT * FROM broker_orders WHERE broker_order_id=? OR client_order_id=?",
                                    (evidence.broker_order_id, evidence.client_order_id)).fetchone()
            if existing:
                stable = ("broker_order_id", "client_order_id", "requested_volume")
                if any(existing[k] != getattr(evidence, k) for k in stable):
                    raise ValueError("Broker order identity conflict")
                if evidence.timestamp < existing["timestamp"]:
                    return dict(existing)
                if evidence.timestamp == existing["timestamp"] and any(existing[k] != getattr(evidence,k) for k in ("retcode","status","filled_volume")):
                    raise ValueError("Conflicting broker observations at same timestamp")
                if evidence.filled_volume < existing["filled_volume"]:
                    raise ValueError("Filled volume cannot regress")
                if existing["status"] in {"FILLED", "CANCELLED", "REJECTED"} and evidence.status != existing["status"]:
                    raise ValueError("Terminal order cannot reopen")
                conn.execute("UPDATE broker_orders SET filled_volume=?,status=?,retcode=?,timestamp=? WHERE broker_order_id=?",
                             (evidence.filled_volume, evidence.status, evidence.retcode, evidence.timestamp, evidence.broker_order_id))
            else:
                conn.execute("INSERT INTO broker_orders VALUES(?,?,?,?,?,?,?,?)", (evidence.broker_order_id, intent["intent_id"],
                             evidence.client_order_id, evidence.retcode, evidence.requested_volume,
                             evidence.filled_volume, evidence.status, evidence.timestamp))
            conn.execute("INSERT INTO order_observations VALUES(?,?,?)", (hashed(evidence.model_dump()), evidence.broker_order_id, canonical(evidence.model_dump())))
            conn.execute("UPDATE order_intents SET state=? WHERE intent_id=?", (evidence.status,intent["intent_id"]))
            self.audit(conn, "BROKER_ORDER_OBSERVED", intent["intent_id"], evidence.model_dump())
        return evidence.model_dump()

    def record_deal(self, evidence: "BrokerDeal"):
        evidence = BrokerDeal.model_validate(evidence.model_dump())
        payload = evidence.model_dump()
        with self.transaction() as conn:
            self._check_account(conn, evidence)
            existing = conn.execute("SELECT payload_hash FROM broker_deals WHERE broker_deal_id=?", (evidence.broker_deal_id,)).fetchone()
            if existing:
                if existing[0] != hashed(payload):
                    raise ValueError("Immutable broker deal conflict")
                return "DUPLICATE"
            prior = conn.execute("SELECT payload FROM quarantine WHERE evidence_id=?", ("deal-" + evidence.broker_deal_id,)).fetchone()
            if prior and prior[0] != canonical(payload):
                raise ValueError("Quarantined deal conflict")
            order = conn.execute("SELECT * FROM broker_orders WHERE broker_order_id=?", (evidence.broker_order_id,)).fetchone()
            if not order:
                key = "deal-" + evidence.broker_deal_id
                prior = conn.execute("SELECT payload FROM quarantine WHERE evidence_id=?", (key,)).fetchone()
                if prior and prior[0] != canonical(payload):
                    raise ValueError("Quarantined deal conflict")
                conn.execute("INSERT INTO quarantine VALUES(?,?,?,?) ON CONFLICT(evidence_id) DO NOTHING",
                             (key, "UNKNOWN_BROKER_ORDER", canonical(payload), now()))
                return "QUARANTINED"
            intent = conn.execute("SELECT * FROM order_intents WHERE intent_id=?", (order["intent_id"],)).fetchone()
            request = json.loads(intent["request"])
            if evidence.deal_type == "OUT" and intent["target_position_id"] != evidence.broker_position_id:
                raise ValueError("Close deal lacks exact owned position identity")
            if evidence.deal_type == "OUT" and intent["action"] not in {"CLOSE","PARTIAL_CLOSE","EMERGENCY_CLOSE"}:
                raise ValueError("Close deal cannot belong to modification/adoption")
            if evidence.deal_type == "IN" and intent["action"] != "OPEN":
                raise ValueError("Entry deal does not belong to an open intent")
            filled = sum((Decimal(str(r[0])) for r in conn.execute("SELECT volume FROM broker_deals WHERE broker_order_id=?", (evidence.broker_order_id,))), Decimal(0))
            if filled + Decimal(str(evidence.volume)) > Decimal(str(order["requested_volume"])):
                raise ValueError("Deals exceed requested order volume")
            if evidence.deal_type == "IN":
                position = conn.execute("SELECT * FROM positions WHERE broker_position_id=?", (evidence.broker_position_id,)).fetchone()
                if position and position["originating_intent"] != intent["intent_id"]:
                    raise ValueError("Netting/multiple origin position requires explicit allocation; unsupported")
                other_position = conn.execute("SELECT 1 FROM positions WHERE originating_intent=? AND broker_position_id<>?", (intent["intent_id"],evidence.broker_position_id)).fetchone()
                if other_position:
                    raise ValueError("One OPEN intent cannot claim a second broker position")
                conn.execute("INSERT INTO positions VALUES(?,?,?,?,?,?) ON CONFLICT(broker_position_id) DO NOTHING",
                             (evidence.broker_position_id, intent["intent_id"], request["symbol"], request["direction"], 0, "RECOVERY_REQUIRED"))
            elif not conn.execute("SELECT 1 FROM positions WHERE broker_position_id=?", (evidence.broker_position_id,)).fetchone():
                raise ValueError("Close deal requires an owned position")
            if evidence.deal_type == "OUT":
                origin = conn.execute("SELECT i.requested_volume FROM positions p JOIN order_intents i ON i.intent_id=p.originating_intent WHERE p.broker_position_id=?", (evidence.broker_position_id,)).fetchone()
                closed = sum((Decimal(str(r[0])) for r in conn.execute("SELECT volume FROM broker_deals WHERE broker_position_id=? AND deal_type='OUT'", (evidence.broker_position_id,))), Decimal(0))
                if closed + Decimal(str(evidence.volume)) > Decimal(str(origin[0])):
                    raise ValueError("Close deals exceed originating intent volume")
            columns = ("broker_deal_id", "broker_order_id", "broker_position_id", "deal_type", "volume", "price",
                       "profit", "commission", "swap", "fee", "timestamp")
            conn.execute("INSERT INTO broker_deals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (*(payload[key] for key in columns), hashed(payload)))
            conn.execute("DELETE FROM quarantine WHERE evidence_id=?", ("deal-" + evidence.broker_deal_id,))
            self.audit(conn, "BROKER_DEAL_OBSERVED", intent["intent_id"], {"broker_deal_id": evidence.broker_deal_id})
        return "RECORDED"

    def record_position(self, evidence: "BrokerPosition"):
        evidence = BrokerPosition.model_validate(evidence.model_dump())
        with self.transaction() as conn:
            self._check_account(conn, evidence)
            intent = conn.execute("SELECT * FROM order_intents WHERE client_order_id=? AND action='OPEN'", (evidence.originating_client_order_id,)).fetchone()
            if not intent:
                raise ValueError("Position lacks explicit originating OPEN intent")
            request = json.loads(intent["request"])
            if (request["symbol"], request["direction"]) != (evidence.symbol, evidence.direction):
                raise ValueError("Position conflicts with originating intent")
            existing = conn.execute("SELECT * FROM positions WHERE broker_position_id=?", (evidence.broker_position_id,)).fetchone()
            if existing and existing["originating_intent"] != intent["intent_id"]:
                raise ValueError("Position ownership conflict")
            if existing and existing["lifecycle_state"] == "CLOSED":
                raise ValueError("Closed position cannot be reopened by snapshot ingestion")
            if conn.execute("SELECT 1 FROM positions WHERE originating_intent=? AND broker_position_id<>?", (intent["intent_id"],evidence.broker_position_id)).fetchone():
                raise ValueError("One OPEN intent cannot claim a second broker position")
            if evidence.open_volume > request["volume"]:
                raise ValueError("Position exceeds originating intent volume")
            prior = conn.execute("SELECT * FROM position_observations WHERE observation_id=?", (evidence.observation_id,)).fetchone()
            if prior:
                if prior["payload_hash"] != hashed(evidence.model_dump()):
                    raise ValueError("Position observation identity conflict")
                return "DUPLICATE"
            latest = conn.execute("SELECT * FROM position_observations WHERE broker_position_id=? ORDER BY source_timestamp DESC LIMIT 1", (evidence.broker_position_id,)).fetchone()
            if latest and latest["source_timestamp"] == evidence.timestamp and latest["open_volume"] != evidence.open_volume:
                raise ValueError("Conflicting position snapshots at same timestamp")
            conn.execute("INSERT INTO positions VALUES(?,?,?,?,?,?) ON CONFLICT(broker_position_id) DO NOTHING",
                         (evidence.broker_position_id, intent["intent_id"], evidence.symbol, evidence.direction, 0, "RECOVERY_REQUIRED"))
            conn.execute("INSERT INTO position_observations VALUES(?,?,?,?,?)", (evidence.observation_id,evidence.broker_position_id,
                         evidence.open_volume,evidence.timestamp,hashed(evidence.model_dump())))
            if not latest or latest["source_timestamp"] < evidence.timestamp:
                # Zero volume is not authoritative closure. Phase 5 must prove final outcomes.
                conn.execute("UPDATE positions SET open_volume=?,lifecycle_state=? WHERE broker_position_id=?",
                             (evidence.open_volume,"OPEN" if evidence.open_volume > 0 else "RECOVERY_REQUIRED",evidence.broker_position_id))
            self.audit(conn,"BROKER_POSITION_OBSERVED",intent["intent_id"],{"observation_id":evidence.observation_id})
        return "RECORDED"

    def replay_quarantine(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT payload FROM quarantine WHERE reason='UNKNOWN_BROKER_ORDER' ORDER BY evidence_id").fetchall()
        results = []
        for row in rows:
            evidence = BrokerDeal.model_validate(json.loads(row[0]))
            results.append(self.record_deal(evidence))
        return results

    def deal_lineage(self):
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("""SELECT d.broker_deal_id,d.broker_order_id,d.broker_position_id,
                i.intent_id,i.signal_id,i.client_order_id,i.target_position_id,
                p.originating_intent AS position_originating_intent, origin.signal_id AS position_signal_id FROM broker_deals d
                JOIN broker_orders o ON o.broker_order_id=d.broker_order_id
                JOIN order_intents i ON i.intent_id=o.intent_id
                JOIN positions p ON p.broker_position_id=d.broker_position_id
                JOIN order_intents origin ON origin.intent_id=p.originating_intent ORDER BY d.timestamp,d.broker_deal_id""")]


class BrokerOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)
    account_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    broker_order_id: str = Field(min_length=1)
    client_order_id: str = Field(min_length=8)
    retcode: int
    requested_volume: float = Field(gt=0)
    filled_volume: float = Field(ge=0)
    status: Literal["PLACED", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED"]
    timestamp: float = Field(gt=0)

    @model_validator(mode="after")
    def quantities(self):
        if self.filled_volume > self.requested_volume:
            raise ValueError("Overfill")
        if self.status == "FILLED" and self.filled_volume != self.requested_volume:
            raise ValueError("Partial fill cannot be reported FILLED")
        if self.status == "PARTIALLY_FILLED" and not 0 < self.filled_volume < self.requested_volume:
            raise ValueError("Invalid partial fill quantity")
        if self.status in {"PLACED", "REJECTED"} and self.filled_volume != 0:
            raise ValueError("Unfilled order state cannot contain fills")
        return self


class BrokerDeal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)
    account_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    broker_deal_id: str = Field(min_length=1)
    broker_order_id: str = Field(min_length=1)
    broker_position_id: str = Field(min_length=1)
    deal_type: Literal["IN", "OUT"]
    volume: float = Field(gt=0)
    price: float = Field(gt=0)
    profit: float
    commission: float
    swap: float
    fee: float
    timestamp: float = Field(gt=0)


class BrokerPosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)
    account_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    observation_id: str = Field(min_length=1, max_length=256)
    broker_position_id: str = Field(min_length=1, max_length=128)
    originating_client_order_id: str = Field(min_length=8, max_length=64)
    symbol: str = Field(min_length=1)
    direction: Literal["BUY", "SELL"]
    open_volume: float = Field(ge=0)
    timestamp: float = Field(gt=0)
