"""Immutable source contracts; parser timestamps are supplied, never rejuvenated."""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.signal_parser import SignalParser, PARSER_VERSION


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, strict=True)
    contract_version: Literal["signal.v1"] = "signal.v1"
    signal_id: str = Field(min_length=1)
    source_type: Literal["HISTORICAL_CHAT", "SCREENSHOT", "STRATEGY", "WHATSAPP"]
    source_id: str = Field(min_length=1)
    source_message_id: str = Field(min_length=1)
    source_timestamp: float = Field(gt=0)
    received_timestamp: float = Field(gt=0)
    parsed_timestamp: float = Field(gt=0)
    symbol: str = Field(min_length=1)
    direction: Literal["BUY", "SELL"]
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: tuple[float, ...] = Field(min_length=1, max_length=3)
    timeframe: Literal["M1", "M5", "M15", "M30", "H1", "H4", "D1"] | None = None
    parser_version: Literal["deterministic_v2", "deterministic_v3"] = PARSER_VERSION
    raw_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    validation_status: Literal["VALID"] = "VALID"

    @model_validator(mode="after")
    def validate_contract(self):
        for value in (self.signal_id, self.source_id, self.source_message_id):
            if not value.strip() or value != value.strip() or len(value) > 256:
                raise ValueError("Source identities must be nonblank, bounded and unpadded")
        allowed = {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD", "USOIL"}
        if self.contract_version == "signal.v2":
            allowed.add("XAGUSD")
        if self.symbol.removesuffix("m") not in allowed:
            raise ValueError("Unsupported symbol")
        if not self.source_timestamp <= self.received_timestamp <= self.parsed_timestamp:
            raise ValueError("Source, received and parsed timestamps must be ordered")
        if self.entry is None and self.contract_version == "signal.v2" and self.entry_type == "MARKET":
            if any(t <= 0 or not (self.stop_loss < t if self.direction == "BUY" else t < self.stop_loss) for t in self.take_profit):
                raise ValueError("Invalid stop/target geometry")
            return self
        if self.entry is None or any(t <= 0 or not (self.stop_loss < self.entry < t if self.direction == "BUY" else t < self.entry < self.stop_loss) for t in self.take_profit):
            raise ValueError("Invalid SL/entry/TP geometry")
        return self


def parse_source(*, text: str, source_type: str, source_id: str, source_message_id: str,
                 source_timestamp: float, received_timestamp: float, parsed_timestamp: float,
                 sender_id: str = "", timeframe: str | None = None) -> Signal:
    parsed = SignalParser().parse(text=text, group_id=source_id, sender_id=sender_id,
                                  message_id=source_message_id, message_timestamp=source_timestamp,
                                  received_timestamp=received_timestamp)
    if parsed.rejection_reasons:
        raise ValueError(", ".join(parsed.rejection_reasons))
    return Signal(signal_id=hashlib.sha256(f"{source_type}:{parsed.signal_id}".encode()).hexdigest(),
                  source_type=source_type, source_id=source_id, source_message_id=source_message_id,
                  source_timestamp=source_timestamp, received_timestamp=received_timestamp,
                  parsed_timestamp=parsed_timestamp, symbol=parsed.instrument, direction=parsed.direction,
                  entry=parsed.entry_price, stop_loss=parsed.stop_loss,
                  take_profit=tuple(t for t in (parsed.take_profit_1, parsed.take_profit_2, parsed.take_profit_3) if t is not None),
                  timeframe=timeframe, raw_source_hash=hashlib.sha256(text.encode()).hexdigest())
