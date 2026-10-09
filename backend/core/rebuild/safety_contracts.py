"""Credential-free P2 inputs. Evidence is injected, never fetched from a broker."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    evidence_id: str = Field(min_length=1)
    observed_at: AwareDatetime


class Quote(Evidence):
    bid: Positive
    ask: Positive

    @model_validator(mode="after")
    def ordered(self):
        if self.ask < self.bid:
            raise ValueError("Crossed quote")
        return self


class Instrument(Evidence):
    symbol: str
    account_currency: str
    calculation: Literal["LINEAR_ACCOUNT_CURRENCY"]
    tick_size: Positive
    value_per_price_unit_per_lot: Positive
    notional_per_price_unit_per_lot: Positive
    margin_per_lot: Positive
    commission_per_lot: Nonnegative
    conversion_at: AwareDatetime
    volume_min: Positive
    volume_max: Positive
    volume_step: Positive
    tradable: StrictBool
    market_available: StrictBool

    @model_validator(mode="after")
    def volumes(self):
        if self.volume_min > self.volume_max:
            raise ValueError("Invalid broker volume bounds")
        return self


class Exposure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    exposure_id: str = Field(min_length=1)
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: Positive
    stop_loss: Positive
    kind: Literal["POSITION", "PENDING", "AMBIGUOUS"]
    entry: Positive | None = None
    reservation_intent_id: str | None = None


class AccountSnapshot(Evidence):
    account_key: str
    currency: str
    mode: Literal["DEMO"]
    equity: Positive
    balance: Positive
    used_margin: Nonnegative
    positions_at: AwareDatetime
    orders_at: AwareDatetime
    complete: StrictBool
    reconciled: StrictBool
    cash_flow_evidence_id: str = Field(min_length=1)
    cash_flow_total: Decimal = Field(allow_inf_nan=False)
    day_start: AwareDatetime
    week_start: AwareDatetime
    day_equity: Positive
    week_equity: Positive
    high_water_equity: Positive
    exposures: tuple[Exposure, ...] = ()


class SafetyInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    account: AccountSnapshot
    quotes: dict[str, Quote]
    instruments: dict[str, Instrument]


class SafetyConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    approved_account_key: str
    authorized_sources: frozenset[str]
    instruments: frozenset[str] = frozenset({"XAUUSDm", "XAGUSDm", "USOILm"})
    aliases: dict[str, str] = Field(default_factory=dict)
    restricted: frozenset[str] = frozenset()
    qualified_strategy_sources: frozenset[str] = frozenset()

    @model_validator(mode="after")
    def allowed(self):
        allowed = {"XAUUSDm", "XAGUSDm", "USOILm"}
        if not self.instruments <= allowed or not set(self.aliases.values()) <= self.instruments:
            raise ValueError("Configuration cannot expand ADR-010 allowlist")
        return self
