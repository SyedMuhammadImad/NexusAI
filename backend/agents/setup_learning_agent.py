"""Agent that learns outcome statistics from private provider setups."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType
from services.setup_learning_store import SetupLearningStore

logger = logging.getLogger(__name__)


class SetupLearningAgent(BaseAgent):
    """
    Passive learner for one private signal provider.

    It records what the provider sent, whether risk/execution accepted it, and
    the realized result after close. It deliberately does not change sizing.
    """

    def __init__(self, store: Optional[SetupLearningStore] = None):
        super().__init__("setup_learning_agent", "Provider Setup Learning Agent")
        self.store = store or SetupLearningStore()
        self._open_signal_by_symbol: Dict[str, str] = {}

    async def initialize(self) -> None:
        self.bus.subscribe(EventType.TRADE_SIGNAL_ACCEPTED, self.handle_event)
        self.bus.subscribe(EventType.TRADE_SIGNAL_REJECTED, self.handle_event)
        self.bus.subscribe(EventType.RISK_BREACH, self.handle_event)
        self.bus.subscribe(EventType.ORDER_REJECTED, self.handle_event)
        self.bus.subscribe(EventType.ORDER_FILLED, self.handle_event)
        self.bus.subscribe(EventType.POSITION_CLOSED, self.handle_event)
        logger.info("Provider Setup Learning Agent initialized")

    async def process_event(self, event: Event) -> None:
        payload = event.payload or {}

        if event.event_type in {EventType.TRADE_SIGNAL_ACCEPTED, EventType.TRADE_SIGNAL_REJECTED}:
            self.store.record_signal(payload)
            return

        if event.event_type == EventType.RISK_BREACH:
            signal_id = self._signal_id(payload)
            reasons = payload.get("reasons") or payload.get("rejection_reasons") or []
            self.store.record_rejection(signal_id, reasons, stage="risk")
            return

        if event.event_type == EventType.ORDER_REJECTED:
            signal_id = self._signal_id(payload)
            reason = payload.get("reason") or "order rejected"
            self.store.record_rejection(signal_id, [str(reason)], stage="execution")
            return

        if event.event_type == EventType.ORDER_FILLED:
            signal_id = self._signal_id(payload)
            if signal_id:
                symbol = payload.get("symbol")
                if symbol:
                    self._open_signal_by_symbol[str(symbol)] = signal_id
                self.store.record_fill(payload)
            return

        if event.event_type == EventType.POSITION_CLOSED:
            signal_id = self._signal_id(payload)
            symbol = payload.get("symbol")
            if not signal_id and symbol:
                signal_id = self._open_signal_by_symbol.get(str(symbol))
            if signal_id:
                self.store.record_close(signal_id, payload)
            if symbol:
                self._open_signal_by_symbol.pop(str(symbol), None)

    def learning_summary(self, recent_limit: int = 25) -> dict:
        return self.store.summary(recent_limit=recent_limit)

    def _signal_id(self, payload: dict) -> Optional[str]:
        value = payload.get("signal_id") or payload.get("source_signal_id")
        if not value:
            original = payload.get("original_request") or {}
            value = original.get("signal_id") or original.get("source_signal_id")
        if not value:
            trade = payload.get("trade") or {}
            value = trade.get("signal_id") or trade.get("source_signal_id")
        return str(value) if value else None
