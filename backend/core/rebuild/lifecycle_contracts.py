"""P1 provenance and fixture boundary contracts, not broker authorization."""
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import Signal
from .ledger import IntentRequest

SourceType = Literal["WHATSAPP_HUMAN", "MANUAL", "NEXUSAI_STRATEGY", "HISTORICAL_WHATSAPP", "SCREENSHOT"]
Identity = Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")]
UtcTime = Annotated[AwareDatetime, Field(strict=False)]


class SourceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)
    source_event_id: Identity
    source_type: SourceType
    source_id: str = Field(min_length=1, max_length=256)
    source_message_id: str = Field(min_length=1, max_length=256)
    sender_id: str = Field(default="", max_length=256)
    raw_text: str = Field(min_length=1, max_length=16000)
    original_timestamp: str | None = Field(default=None, max_length=256)
    timezone_evidence: str | None = Field(default=None, max_length=256)
    source_time_utc: UtcTime | None = None
    received_at: UtcTime
    metadata: dict[str, str] = Field(default_factory=dict, max_length=32)

    @field_validator("source_time_utc", "received_at")
    @classmethod
    def utc(cls, value):
        if value is not None:
            if value.timestamp() <= 0:
                raise ValueError("Timestamp must be after the Unix epoch")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def evidence(self):
        if any(not v.strip() or v != v.strip() for v in (self.source_id, self.source_message_id)):
            raise ValueError("Source identities must be nonblank and unpadded")
        if self.source_time_utc is not None:
            if not self.original_timestamp or not self.original_timestamp.strip():
                raise ValueError("Normalized time requires original timestamp evidence")
            if self.source_time_utc > self.received_at:
                raise ValueError("Source timestamp cannot follow receipt")
        if any(not k.strip() or len(k) > 128 or len(v) > 4096 for k, v in self.metadata.items()):
            raise ValueError("Metadata keys/values must be bounded")
        return self


class CanonicalSignal(Signal):
    parser_version: Literal["deterministic_v2", "deterministic_v3", "deterministic_v3_p2"] = "deterministic_v3"
    entry: float | None = Field(default=None, gt=0)
    contract_version: Literal["signal.v2"] = "signal.v2"
    source_type: SourceType
    source_event_id: Identity
    entry_type: Literal["MARKET", "LIMIT"]
    requested_risk_pct: float | None = Field(default=None, gt=0, le=100)


class TradeIntent(IntentRequest):
    entry: float | None = Field(default=None, gt=0)
    contract_version: Literal["intent.v2"] = "intent.v2"
    action: Literal["OPEN"] = "OPEN"
    entry_type: Literal["MARKET", "LIMIT"]
    requested_risk_pct: float | None = Field(default=None, gt=0, le=100)
    take_profit_targets: tuple[float, ...] = Field(min_length=1, max_length=3, strict=False)

    @model_validator(mode="after")
    def targets(self):
        if self.take_profit not in self.take_profit_targets:
            raise ValueError("Selected target must be one of the requested targets")
        if self.entry is None:
            if self.entry_type != "MARKET" or any(not (self.stop_loss < p if self.direction == "BUY" else p < self.stop_loss) for p in self.take_profit_targets):
                raise ValueError("MARKET-only absent entry; valid stop/targets required")
            return self
        if any(not (self.stop_loss < self.entry < p if self.direction == "BUY" else p < self.entry < self.stop_loss)
               for p in self.take_profit_targets):
            raise ValueError("Invalid target geometry")
        return self


class SafetyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)
    safety_decision_id: Identity
    intent_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["APPROVED", "REJECTED"]
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=16, strict=False)
    explanation: str = Field(min_length=1, max_length=2000)
    policy_id: str = Field(min_length=1, max_length=128)
    policy_version: str = Field(min_length=1, max_length=128)
    decision_timestamp: UtcTime
    evidence_scope: Literal["P1_DISABLED", "FIXTURE"]
    risk_budget: float = Field(ge=0)
    approved_volume: float = Field(ge=0)

    @field_validator("decision_timestamp")
    @classmethod
    def utc(cls, value):
        if value.timestamp() <= 0:
            raise ValueError("Invalid decision timestamp")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def reasons(self):
        if any(not s.strip() or len(s) > 128 for s in self.reason_codes):
            raise ValueError("Reason codes must be nonblank and bounded")
        if any(not s.strip() for s in (self.explanation, self.policy_id, self.policy_version)):
            raise ValueError("Decision evidence cannot be blank")
        if self.decision == "APPROVED" and self.evidence_scope != "FIXTURE":
            raise ValueError("P1 cannot approve non-fixture execution")
        if self.decision == "REJECTED" and (self.risk_budget != 0 or self.approved_volume != 0):
            raise ValueError("Rejected decision cannot allocate risk or volume")
        return self


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    execution_request_id: Identity
    intent_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    safety_decision_id: Identity
