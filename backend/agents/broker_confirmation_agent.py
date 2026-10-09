"""
Broker Momentum Confirmation Agent.

This agent consumes broker-sourced ticks and emits an independent confirmation
signal only after short-term broker-price momentum is visible. It gives the
orchestrator a second agent vote without bypassing risk or execution.
"""

import logging
import time
from typing import Dict, List, Optional

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


class BrokerMomentumConfirmationAgent(BaseAgent):
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        min_history: int = 8,
        cooldown_seconds: float = 45.0,
        min_move_bps: float = 0.25,
    ):
        super().__init__("broker_confirmation_agent", "Broker Momentum Confirmation Agent")
        self._symbols = set(symbols or [])
        self._history: Dict[str, List[float]] = {}
        self._last_signal_at: Dict[str, float] = {}
        self._min_history = min_history
        self._cooldown_seconds = cooldown_seconds
        self._min_move_bps = min_move_bps

    async def initialize(self) -> None:
        self.bus.subscribe(EventType.MARKET_DATA_UPDATE, self.handle_event)
        logger.info(
            "Broker Momentum Confirmation Agent initialized | symbols=%s",
            sorted(self._symbols) if self._symbols else "all broker symbols",
        )

    async def process_event(self, event: Event) -> None:
        payload = event.payload
        if payload.get("asset_class") != "broker":
            return

        symbol = payload.get("symbol")
        price = float(payload.get("price") or 0)
        if not symbol or price <= 0:
            return
        if self._symbols and symbol not in self._symbols:
            return

        history = self._history.setdefault(symbol, [])
        history.append(price)
        if len(history) > 60:
            del history[:-60]
        if len(history) < self._min_history:
            return

        now = time.time()
        if now - self._last_signal_at.get(symbol, 0.0) < self._cooldown_seconds:
            return

        direction, confidence, move_bps = self._evaluate(history)
        if direction == "HOLD":
            return

        self._last_signal_at[symbol] = now
        self.metrics.signals_generated += 1
        await self.publish(
            EventType.MACRO_SIGNAL,
            {
                "symbol": symbol,
                "direction": direction,
                "confidence": confidence,
                "price": price,
                "ttl_seconds": 90.0,
                "reasoning": (
                    f"Broker momentum confirmation: {move_bps:+.2f} bps over "
                    f"{self._min_history} broker ticks"
                ),
            },
            priority=4,
        )

    def add_symbol(self, symbol: str) -> None:
        self._symbols.add(symbol)

    def _evaluate(self, history: List[float]) -> tuple[str, float, float]:
        recent = history[-self._min_history:]
        short_ma = sum(recent[-3:]) / 3
        long_ma = sum(recent) / len(recent)
        first = recent[0]
        last = recent[-1]
        move_bps = (last - first) / first * 10_000 if first > 0 else 0.0
        if abs(move_bps) < self._min_move_bps:
            return "HOLD", 0.0, move_bps

        if short_ma > long_ma and move_bps > 0:
            confidence = min(0.82, 0.50 + abs(move_bps) / 25)
            return "BUY", round(confidence, 4), move_bps
        if short_ma < long_ma and move_bps < 0:
            confidence = min(0.82, 0.50 + abs(move_bps) / 25)
            return "SELL", round(confidence, 4), move_bps
        return "HOLD", 0.0, move_bps
