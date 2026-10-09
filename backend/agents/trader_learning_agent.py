"""Observation-only trader imitation learner for private provider signals."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType
from services.signal_parser import ParsedTradeSignal
from services.trader_learning_store import TraderLearningStore

logger = logging.getLogger(__name__)


class TraderLearningAgent(BaseAgent):
    """
    Learns from a private trader's setups without copying or executing trades.

    Execution remains image upload -> risk agent -> execution agent. This agent
    only records market context, signal outcomes, and shadow readiness.
    """

    def __init__(self, store: Optional[TraderLearningStore] = None):
        super().__init__("trader_learning_agent", "Trader Learning / Imitation Agent")
        self.store = store or TraderLearningStore()
        self._market_snapshots: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=500))
        self._open_signal_by_symbol: Dict[str, str] = {}

    async def initialize(self) -> None:
        self.bus.subscribe(EventType.MARKET_DATA_UPDATE, self.handle_event)
        self.bus.subscribe(EventType.TRADE_SIGNAL_ACCEPTED, self.handle_event)
        self.bus.subscribe(EventType.TRADE_SIGNAL_REJECTED, self.handle_event)
        self.bus.subscribe(EventType.ORDER_REQUESTED, self.handle_event)
        self.bus.subscribe(EventType.ORDER_FILLED, self.handle_event)
        self.bus.subscribe(EventType.ORDER_REJECTED, self.handle_event)
        self.bus.subscribe(EventType.POSITION_MODIFIED, self.handle_event)
        self.bus.subscribe(EventType.POSITION_CLOSED, self.handle_event)
        logger.info("Trader Learning / Imitation Agent initialized in observation-only mode")

    async def process_event(self, event: Event) -> None:
        payload = event.payload or {}
        if event.event_type == EventType.MARKET_DATA_UPDATE:
            self._capture_market_snapshot(payload)
            return

        if event.event_type in {EventType.TRADE_SIGNAL_ACCEPTED, EventType.TRADE_SIGNAL_REJECTED}:
            signal_id = self._signal_id(payload)
            if not signal_id:
                return
            symbol = payload.get("instrument") or payload.get("symbol")
            self.store.record_signal(
                signal_id=signal_id,
                source=payload.get("source") or "private_signal",
                message_id=payload.get("message_id"),
                raw_message=None,
                parsed_signal=payload,
                market_snapshot=self.latest_market_snapshot(str(symbol or "")),
                validation_status=payload.get("validation_status") or "ACCEPTED",
                rejection_reasons=payload.get("rejection_reasons") or [],
            )
            return

        if event.event_type == EventType.ORDER_REQUESTED:
            signal_id = self._signal_id(payload)
            self.store.record_execution_event(signal_id, event.event_type.value, payload)
            self.store.record_status(signal_id, execution_status="REQUESTED")
            return

        if event.event_type == EventType.POSITION_MODIFIED:
            signal_id = self._signal_id(payload)
            self.store.record_execution_event(signal_id, event.event_type.value, payload)
            self.store.record_status(signal_id, execution_status="ADOPTED")
            return

        if event.event_type == EventType.ORDER_REJECTED:
            signal_id = self._signal_id(payload)
            self.store.record_execution_event(signal_id, event.event_type.value, payload)
            self.store.record_status(signal_id, execution_status="REJECTED", outcome_status="REJECTED")
            return

        if event.event_type == EventType.ORDER_FILLED:
            signal_id = self._signal_id(payload)
            symbol = payload.get("symbol")
            if signal_id and symbol:
                self._open_signal_by_symbol[str(symbol)] = signal_id
            self.store.record_execution_event(signal_id, event.event_type.value, payload)
            self.store.record_status(signal_id, execution_status="FILLED")
            return

        if event.event_type == EventType.POSITION_CLOSED:
            signal_id = self._signal_id(payload)
            symbol = payload.get("symbol")
            if not signal_id and symbol:
                signal_id = self._open_signal_by_symbol.get(str(symbol))
            self.store.record_execution_event(signal_id, event.event_type.value, payload)
            self.store.record_close(signal_id, payload)
            if symbol:
                self._open_signal_by_symbol.pop(str(symbol), None)

    def record_private_signal(
        self,
        signal: ParsedTradeSignal,
        *,
        source: str = "private_signal",
        validation_status: str,
        rejection_reasons: Optional[list[str]] = None,
    ) -> None:
        parsed = signal.to_dict(include_raw=False)
        self.store.record_signal(
            signal_id=signal.signal_id,
            source=source,
            message_id=signal.message_id,
            raw_message=signal.raw_message,
            parsed_signal=parsed,
            market_snapshot=self.latest_market_snapshot(signal.instrument or ""),
            validation_status=validation_status,
            rejection_reasons=rejection_reasons or [],
        )

    def latest_market_snapshot(self, symbol: str) -> dict:
        snapshots = self._market_snapshots.get(str(symbol or ""))
        return dict(snapshots[-1]) if snapshots else {}

    def learning_summary(self, recent_limit: int = 25) -> dict:
        return self.store.summary(recent_limit=recent_limit)

    def _capture_market_snapshot(self, payload: Dict[str, Any]) -> None:
        symbol = payload.get("symbol")
        if not symbol:
            return
        snapshot = {
            "symbol": symbol,
            "price": payload.get("price"),
            "bid": payload.get("bid"),
            "ask": payload.get("ask"),
            "spread_bps": payload.get("spread_bps"),
            "rsi": (payload.get("indicators") or {}).get("rsi"),
            "volume": payload.get("volume"),
            "timestamp": payload.get("timestamp") or time.time(),
        }
        self._market_snapshots[str(symbol)].append(snapshot)

    def _signal_id(self, payload: dict) -> Optional[str]:
        value = payload.get("signal_id") or payload.get("source_signal_id")
        if not value:
            original = payload.get("original_request") or {}
            value = original.get("signal_id") or original.get("source_signal_id")
        if not value:
            trade = payload.get("trade") or {}
            value = trade.get("signal_id") or trade.get("source_signal_id")
        return str(value) if value else None
