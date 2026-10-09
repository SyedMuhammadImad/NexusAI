"""Normalized broker evidence. Construction is not proof of a live broker session."""
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from .safety_contracts import Evidence, Positive, Nonnegative, SafetyInputs


class Attestation(Evidence):
    account_key: str
    account_id: str
    server: str
    currency: str
    mode: Literal['DEMO']
    scope: Literal['FIXTURE', 'MT5_DEMO']
    session_id: str = Field(min_length=1)
    connected: StrictBool
    trade_allowed: StrictBool
    expert_allowed: StrictBool
    hedging: StrictBool


class OrderObservation(Evidence):
    broker_order_id: str = Field(min_length=1)
    correlation: str = Field(min_length=1)
    magic: StrictInt
    symbol: str
    direction: Literal['BUY', 'SELL']
    entry_type: Literal['MARKET', 'LIMIT']
    requested_volume: Positive
    filled_volume: Nonnegative
    stop_loss: Positive
    take_profit: Positive
    status: Literal['PLACED', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED', 'REJECTED']

    @model_validator(mode='after')
    def quantities(self):
        if self.filled_volume > self.requested_volume:
            raise ValueError('Overfill')
        if self.status == 'FILLED' and self.filled_volume != self.requested_volume:
            raise ValueError('Incomplete FILLED order')
        if self.status == 'PARTIALLY_FILLED' and not 0 < self.filled_volume < self.requested_volume:
            raise ValueError('Invalid partial fill')
        if self.status in {'PLACED', 'REJECTED'} and self.filled_volume:
            raise ValueError('Unfilled status with fills')
        return self


class DealObservation(Evidence):
    broker_deal_id: str = Field(min_length=1)
    broker_order_id: str = Field(min_length=1)
    broker_position_id: str = Field(min_length=1)
    symbol: str
    direction: Literal['BUY', 'SELL']
    entry: Literal['IN', 'OUT', 'INOUT', 'OUT_BY']
    volume: Positive
    price: Positive
    profit: Decimal = Field(allow_inf_nan=False)
    commission: Decimal = Field(allow_inf_nan=False)
    swap: Decimal = Field(allow_inf_nan=False)
    fee: Decimal = Field(allow_inf_nan=False)


class PositionObservation(Evidence):
    broker_position_id: str = Field(min_length=1)
    opening_order_id: str = Field(min_length=1)
    symbol: str
    direction: Literal['BUY', 'SELL']
    open_volume: Nonnegative
    stop_loss: Positive
    take_profit: Positive
    confirmed_absent: StrictBool = False
    absence_evidence_id: str | None = None

    @model_validator(mode='after')
    def absence(self):
        if self.open_volume == 0 and (not self.confirmed_absent or not self.absence_evidence_id):
            raise ValueError('Zero position requires explicit complete-inventory absence evidence')
        if self.open_volume and self.confirmed_absent:
            raise ValueError('Open position cannot be absent')
        return self


class ProtectiveExitOrder(Evidence):
    broker_order_id: str = Field(min_length=1)
    broker_position_id: str = Field(min_length=1)
    symbol: str
    direction: Literal['BUY', 'SELL']
    reason: Literal['SL', 'TP']
    requested_volume: Positive
    filled_volume: Positive
    status: Literal['FILLED']

    @model_validator(mode='after')
    def filled(self):
        if self.requested_volume != self.filled_volume:
            raise ValueError('Incomplete protective close remains ambiguous')
        return self


class BrokerSnapshot(Evidence):
    attestation: Attestation
    history_since: AwareDatetime
    complete: StrictBool
    orders: tuple[OrderObservation, ...]
    deals: tuple[DealObservation, ...]
    positions: tuple[PositionObservation, ...]
    safety: SafetyInputs
    protective_exit_orders: tuple[ProtectiveExitOrder, ...] = ()


class SubmissionResult(Evidence):
    attestation: Attestation
    outcome: Literal['ACKNOWLEDGED', 'REJECTED', 'AMBIGUOUS']
    broker_order_id: str | None = None
    retcode: StrictInt | None = None


class BrokerAdapter(Protocol):
    """An injected, account-bound session. Never loads credentials or logs in."""
    scope: Literal['FIXTURE', 'MT5_DEMO']

    def attest(self) -> Attestation: ...
    def snapshot(self, since: AwareDatetime) -> BrokerSnapshot: ...
    def submit(self, command: dict) -> SubmissionResult: ...
