"""
Portfolio Manager Agent — Tracks P&L, positions, performance metrics.
Market Regime Detection Agent — Classifies bull/bear/sideways/volatile.

These are separate agents but live in the same file since they're 
lightweight and tightly coupled to portfolio state.
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import numpy as np

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# PORTFOLIO MANAGER AGENT
# ═══════════════════════════════════════════════════════════════

@dataclass
class PositionRecord:
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    current_price: float
    stop_loss: float
    take_profit: float
    opened_at: float
    order_id: str
    source_signal_id: Optional[str] = None
    broker_ticket: Optional[int] = None
    volume_lots: Optional[float] = None
    margin_required: Optional[float] = None
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0

    def update_price(self, price: float) -> None:
        self.current_price = price
        if self.direction == "BUY":
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.quantity
        cost_basis = self.entry_price * self.quantity
        self.unrealized_pnl_pct = self.unrealized_pnl / max(cost_basis, 0.0001) * 100

    def check_exit_conditions(self) -> Optional[str]:
        """Returns exit reason if stop or target hit."""
        if self.direction == "BUY":
            if self.current_price <= self.stop_loss:
                return "stop_loss"
            if self.current_price >= self.take_profit:
                return "take_profit"
        else:
            if self.current_price >= self.stop_loss:
                return "stop_loss"
            if self.current_price <= self.take_profit:
                return "take_profit"
        return None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 6),
            "current_price": round(self.current_price, 6),
            "quantity": round(self.quantity, 6),
            "stop_loss": round(self.stop_loss, 6),
            "take_profit": round(self.take_profit, 6),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "opened_at": self.opened_at,
            "order_id": self.order_id,
            "source_signal_id": self.source_signal_id,
            "signal_id": self.source_signal_id,
            "broker_ticket": self.broker_ticket,
            "volume_lots": self.volume_lots,
            "margin_required": self.margin_required,
        }


class PortfolioManagerAgent(BaseAgent):
    """
    Single source of truth for portfolio state.
    
    Tracks all positions, calculates real-time P&L,
    monitors stop/take-profit levels, and computes performance metrics
    (Sharpe, win rate, max drawdown, etc.)
    """

    def __init__(self, initial_capital: float = 100_000.0):
        super().__init__("portfolio_manager", "Portfolio Manager Agent")
        self._initial_capital = initial_capital
        self._current_capital = initial_capital
        self._positions: Dict[str, PositionRecord] = {}
        self._closed_trades: List[dict] = []
        self._equity_curve: List[dict] = []
        self._daily_returns: List[float] = []

    async def initialize(self) -> None:
        self.bus.subscribe(EventType.ORDER_FILLED, self.handle_event)
        self.bus.subscribe(EventType.MARKET_DATA_UPDATE, self.handle_event)
        self.bus.subscribe(EventType.KILL_SWITCH_ACTIVATED, self.handle_event)
        logger.info("Portfolio Manager initialized")

    async def process_event(self, event: Event) -> None:
        if event.event_type == EventType.ORDER_FILLED:
            await self._handle_fill(event)
        elif event.event_type == EventType.MARKET_DATA_UPDATE:
            await self._handle_price_update(event)
        elif event.event_type == EventType.KILL_SWITCH_ACTIVATED:
            await self._handle_kill_switch(event)

    async def _handle_fill(self, event: Event) -> None:
        p = event.payload
        symbol = p.get("symbol")
        if not symbol:
            return

        position = PositionRecord(
            symbol=symbol,
            direction=p.get("direction", "BUY"),
            entry_price=float(p.get("fill_price", 0)),
            quantity=float(p.get("fill_quantity", 0)),
            current_price=float(p.get("fill_price", 0)),
            stop_loss=float(p.get("stop_loss", 0)),
            take_profit=float(p.get("take_profit", 0)),
            opened_at=time.time(),
            order_id=p.get("order_id", ""),
            source_signal_id=p.get("signal_id") or p.get("source_signal_id"),
        )
        self._positions[symbol] = position
        logger.info(f"Position tracked: {symbol} {position.direction} @ {position.entry_price}")

    async def _handle_price_update(self, event: Event) -> None:
        symbol = event.payload.get("symbol")
        price = event.payload.get("price")

        if not symbol or not price or symbol not in self._positions:
            return

        position = self._positions[symbol]
        position.update_price(float(price))

        # Check if stop/target hit
        exit_reason = position.check_exit_conditions()
        if exit_reason:
            await self._close_position(symbol, float(price), exit_reason)

    async def _close_position(self, symbol: str, price: float, reason: str) -> None:
        if symbol not in self._positions:
            return

        position = self._positions.pop(symbol)
        position.update_price(price)
        pnl = position.unrealized_pnl

        trade_record = {
            **position.to_dict(),
            "exit_price": round(price, 6),
            "exit_reason": reason,
            "pnl": round(pnl, 2),
            "pnl_pct": round(position.unrealized_pnl_pct, 2),
            "closed_at": time.time(),
            "duration_seconds": time.time() - position.opened_at,
        }
        self._closed_trades.append(trade_record)
        self._current_capital += pnl

        self._equity_curve.append({
            "timestamp": time.time(),
            "equity": self._current_capital,
            "pnl_this_trade": pnl,
        })

        await self.publish(
            EventType.POSITION_CLOSED,
            {
                "symbol": symbol,
                "source_signal_id": position.source_signal_id,
                "signal_id": position.source_signal_id,
                "pnl": pnl,
                "reason": reason,
                "trade": trade_record,
            },
            priority=3,
        )

        logger.info(f"Position closed: {symbol} via {reason} | PnL: ${pnl:+,.2f}")
        await self.publish(EventType.PORTFOLIO_UPDATE, self.portfolio_summary, priority=5)

    async def _handle_kill_switch(self, event: Event) -> None:
        """Close all tracked positions at their latest observed prices."""
        if not self._positions:
            return

        reason = event.payload.get("reason", "kill_switch")
        for symbol, position in list(self._positions.items()):
            await self._close_position(symbol, position.current_price, reason)

    def force_close_all(self, prices: Dict[str, float]) -> None:
        """Emergency close — called by kill switch."""
        for symbol, position in list(self._positions.items()):
            price = prices.get(symbol, position.current_price)
            asyncio.create_task(self._close_position(symbol, price, "kill_switch"))

    def update_capital(self, new_capital: float) -> None:
        self._initial_capital = new_capital
        self._current_capital = new_capital

    def reconcile_broker_positions(self, positions: List[dict], equity: float) -> None:
        broker_positions: Dict[str, PositionRecord] = {}
        unrealized = 0.0
        for p in positions:
            symbol = p.get("symbol")
            if not symbol:
                continue
            quantity = float(p.get("quantity") or 0)
            entry = float(p.get("price_open") or 0)
            current = float(p.get("price_current") or entry or 0)
            profit = float(p.get("profit") or 0)
            record = PositionRecord(
                symbol=symbol,
                direction=p.get("direction", "BUY"),
                entry_price=entry,
                quantity=quantity,
                current_price=current,
                stop_loss=float(p.get("stop_loss") or 0),
                take_profit=float(p.get("take_profit") or 0),
                opened_at=float(p.get("time") or time.time()),
                order_id=str(p.get("ticket") or ""),
                source_signal_id=p.get("signal_id") or p.get("source_signal_id"),
                broker_ticket=p.get("ticket"),
                volume_lots=p.get("volume_lots"),
                margin_required=p.get("margin_required"),
            )
            record.unrealized_pnl = profit
            cost_basis = max(abs(entry * quantity), 0.0001)
            record.unrealized_pnl_pct = profit / cost_basis * 100
            broker_positions[symbol] = record
            unrealized += profit

        self._positions = broker_positions
        self._current_capital = round(equity - unrealized, 2)
        if self._initial_capital <= 0:
            self._initial_capital = equity

    @property
    def portfolio_summary(self) -> dict:
        unrealized_pnl = sum(p.unrealized_pnl for p in self._positions.values())
        realized_pnl = sum(t["pnl"] for t in self._closed_trades)

        return {
            "initial_capital": self._initial_capital,
            "current_capital": round(self._current_capital, 2),
            "total_value": round(self._current_capital + unrealized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "total_return_pct": round(
                (self._current_capital - self._initial_capital) / self._initial_capital * 100, 2
            ),
            "open_positions": len(self._positions),
            "total_trades": len(self._closed_trades),
            "positions": [p.to_dict() for p in self._positions.values()],
        }

    @property
    def performance_metrics(self) -> dict:
        """Compute key hedge fund metrics."""
        trades = self._closed_trades
        if len(trades) < 2:
            return {"message": "Need at least 2 closed trades for metrics"}

        pnls = [t["pnl"] for t in trades]
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p <= 0]

        win_rate = len(winning) / len(pnls)
        avg_win = sum(winning) / len(winning) if winning else 0
        avg_loss = abs(sum(losing) / len(losing)) if losing else 0
        gross_profit = sum(winning)
        gross_loss = abs(sum(losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

        # Sharpe ratio (annualized, assuming 252 trading days)
        if len(self._daily_returns) > 1:
            returns_arr = np.array(self._daily_returns)
            sharpe = (
                np.mean(returns_arr) / np.std(returns_arr) * math.sqrt(252)
                if np.std(returns_arr) > 0 else 0
            )
        else:
            sharpe = 0.0

        # Max drawdown from equity curve
        if len(self._equity_curve) > 1:
            equities = [e["equity"] for e in self._equity_curve]
            peak = equities[0]
            max_dd = 0.0
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak
                max_dd = max(max_dd, dd)
        else:
            max_dd = 0.0

        return {
            "total_trades": len(trades),
            "win_rate": round(win_rate * 100, 1),
            "avg_win_usd": round(avg_win, 2),
            "avg_loss_usd": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "total_pnl": round(sum(pnls), 2),
            "expectancy_per_trade": round(sum(pnls) / len(pnls), 2),
        }


# ═══════════════════════════════════════════════════════════════
# MARKET REGIME DETECTION AGENT
# ═══════════════════════════════════════════════════════════════

class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    CRISIS = "CRISIS"
    UNKNOWN = "UNKNOWN"


class RegimeDetectionAgent(BaseAgent):
    """
    Classifies the current market regime using multiple signals:
    - Price trend (vs 200-day SMA)
    - Volatility (VIX or realized vol)
    - Breadth (% of stocks above moving averages)
    - Momentum (rate of change)
    
    Regime changes affect orchestrator agent weights.
    """

    def __init__(self):
        super().__init__("regime_agent", "Market Regime Detection Agent")
        self._current_regime: MarketRegime = MarketRegime.UNKNOWN
        self._price_history: Dict[str, List[float]] = {}
        self._current_vix: float = 20.0
        self._regime_history: List[dict] = []
        self._last_regime_change: float = 0.0
        self._min_regime_duration = 300.0  # Don't flip regimes more than once per 5min

    async def initialize(self) -> None:
        self.bus.subscribe(EventType.MARKET_DATA_UPDATE, self.handle_event)
        logger.info("Regime Detection Agent initialized")

    async def process_event(self, event: Event) -> None:
        payload = event.payload
        symbol = payload.get("symbol")
        price = payload.get("price")
        vix = payload.get("vix")

        if vix:
            self._current_vix = float(vix)

        if symbol and price:
            if symbol not in self._price_history:
                self._price_history[symbol] = []
            self._price_history[symbol].append(float(price))
            if len(self._price_history[symbol]) > 200:
                self._price_history[symbol] = self._price_history[symbol][-200:]

        # Re-evaluate regime on every significant update
        if symbol in ("SPY", "^GSPC", "BTC-USD"):  # Benchmark symbols
            await self._evaluate_regime()

    async def _evaluate_regime(self) -> None:
        """Multi-factor regime classification."""
        # Cooldown to prevent rapid oscillation
        if time.time() - self._last_regime_change < self._min_regime_duration:
            return

        regime = self._classify_regime()
        
        if regime != self._current_regime:
            old_regime = self._current_regime
            self._current_regime = regime
            self._last_regime_change = time.time()

            regime_record = {
                "regime": regime.value,
                "previous": old_regime.value,
                "vix": self._current_vix,
                "timestamp": time.time(),
            }
            self._regime_history.append(regime_record)

            logger.info(f"REGIME CHANGE: {old_regime.value} → {regime.value} (VIX={self._current_vix:.1f})")

            await self.publish(
                EventType.MARKET_REGIME_CHANGE,
                {
                    "regime": regime.value,
                    "previous_regime": old_regime.value,
                    "vix": self._current_vix,
                    "confidence": self._regime_confidence(regime),
                    "reasoning": self._regime_reasoning(regime),
                },
                priority=3,
            )

            await self.publish(
                EventType.STRATEGY_SIGNAL,  # Reuse for regime advisory signal
                {
                    "symbol": "PORTFOLIO",
                    "direction": "BUY" if regime == MarketRegime.BULL else "SELL" if regime == MarketRegime.BEAR else "HOLD",
                    "confidence": self._regime_confidence(regime) * 0.7,  # Reduced confidence for regime signals
                    "reasoning": f"Market regime: {regime.value}",
                    "ttl_seconds": 600.0,
                },
                priority=4,
            )

    def _classify_regime(self) -> MarketRegime:
        """
        Regime classification logic.
        
        Crisis: VIX > 40
        High volatility: VIX > 30
        Bear: VIX 20-30 + downtrend
        Bull: VIX < 20 + uptrend
        Sideways: Low volatility, no trend
        """
        if self._current_vix >= 40:
            return MarketRegime.CRISIS
        
        if self._current_vix >= 30:
            return MarketRegime.HIGH_VOLATILITY

        # Check price trends for benchmark symbols
        trend_signals = []
        for symbol in ("SPY", "BTC-USD"):
            prices = self._price_history.get(symbol, [])
            if len(prices) >= 20:
                sma_20 = sum(prices[-20:]) / 20
                sma_50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else sma_20
                current = prices[-1]
                
                if current > sma_20 > sma_50:
                    trend_signals.append("BULL")
                elif current < sma_20 < sma_50:
                    trend_signals.append("BEAR")
                else:
                    trend_signals.append("SIDEWAYS")

        if not trend_signals:
            return MarketRegime.UNKNOWN

        bull_count = trend_signals.count("BULL")
        bear_count = trend_signals.count("BEAR")

        if bull_count > bear_count and self._current_vix < 25:
            return MarketRegime.BULL
        elif bear_count > bull_count or self._current_vix > 25:
            return MarketRegime.BEAR
        else:
            return MarketRegime.SIDEWAYS

    def _regime_confidence(self, regime: MarketRegime) -> float:
        if regime == MarketRegime.CRISIS:
            return 0.95  # Crisis is obvious
        if regime == MarketRegime.HIGH_VOLATILITY:
            return 0.85
        if regime in (MarketRegime.BULL, MarketRegime.BEAR):
            return 0.70
        return 0.50

    def _regime_reasoning(self, regime: MarketRegime) -> str:
        return (
            f"VIX={self._current_vix:.1f} | "
            f"Regime classified as {regime.value} | "
            f"Based on VIX threshold + price trend analysis"
        )

    @property
    def current_regime(self) -> str:
        return self._current_regime.value

    @property
    def regime_history(self) -> List[dict]:
        return self._regime_history[-20:]
