"""
Risk Management Agent — The most important agent in the system.
If this agent is wrong, you lose money. If it fails silently, you lose everything.

Responsibilities:
1. Position sizing (Kelly Criterion + volatility adjustment)
2. Stop-loss / take-profit calculation
3. Portfolio-level risk monitoring
4. Kill switch activation

This agent has VETO POWER. It can block any trade regardless of what
the orchestrator decides. The orchestrator respects RISK_BREACH events.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class RiskParameters:
    """Tunable risk controls. Operators MUST review these before live trading."""
    # Portfolio limits
    max_portfolio_risk_pct: float = 0.02      # Max 2% of portfolio at risk per trade
    max_total_exposure_pct: float = 0.20      # Max 20% of capital deployed
    max_single_position_pct: float = 0.05    # Max 5% in any single name
    max_sector_exposure_pct: float = 0.25    # Max 25% in any sector
    
    # Drawdown limits
    max_daily_loss_pct: float = 0.05         # Kill switch at 5% daily loss
    max_drawdown_pct: float = 0.15           # Kill switch at 15% total drawdown
    
    # Trade-level controls
    min_risk_reward_ratio: float = 1.5        # Only trade if reward >= 1.5x risk
    max_slippage_bps: int = 50               # Max 50 basis points slippage
    
    # Volatility adjustments
    high_vix_threshold: float = 30.0         # Above this, reduce all position sizes 50%
    extreme_vix_threshold: float = 40.0      # Above this, no new positions


@dataclass
class PositionSizing:
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_units: float
    position_size_usd: float
    risk_amount_usd: float
    risk_reward_ratio: float
    kelly_fraction: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 4),
            "stop_loss": round(self.stop_loss, 4),
            "take_profit": round(self.take_profit, 4),
            "position_size_units": round(self.position_size_units, 4),
            "position_size_usd": round(self.position_size_usd, 2),
            "risk_amount_usd": round(self.risk_amount_usd, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "kelly_fraction": round(self.kelly_fraction, 4),
        }


@dataclass
class PortfolioState:
    total_capital: float = 100_000.0
    available_capital: float = 100_000.0
    deployed_capital: float = 0.0
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    peak_capital: float = 100_000.0
    positions: Dict[str, dict] = field(default_factory=dict)
    daily_loss_start: float = field(default_factory=lambda: 100_000.0)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_capital <= 0:
            return 0.0
        return (self.peak_capital - self.total_capital) / self.peak_capital

    @property
    def daily_loss_pct(self) -> float:
        if self.daily_loss_start <= 0:
            return 0.0
        return (self.daily_loss_start - self.total_capital) / self.daily_loss_start

    @property
    def exposure_pct(self) -> float:
        return self.deployed_capital / max(self.total_capital, 1)

    def to_dict(self) -> dict:
        return {
            "total_capital": round(self.total_capital, 2),
            "available_capital": round(self.available_capital, 2),
            "deployed_capital": round(self.deployed_capital, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "drawdown_pct": round(self.drawdown_pct * 100, 2),
            "daily_loss_pct": round(self.daily_loss_pct * 100, 2),
            "exposure_pct": round(self.exposure_pct * 100, 2),
            "open_positions": len(self.positions),
        }


class RiskManagementAgent(BaseAgent):
    """
    Guardian of capital. All order requests pass through here before execution.
    
    Two primary functions:
    1. Pre-trade: Size positions, set stop/take-profit, approve/reject orders
    2. Post-trade: Monitor drawdown, manage existing positions, trigger kill switch
    """

    def __init__(
        self,
        params: Optional[RiskParameters] = None,
        initial_capital: float = 100_000.0,
    ):
        super().__init__("risk_agent", "Risk Management Agent")
        self.params = params or RiskParameters()
        self.portfolio = PortfolioState(
            total_capital=initial_capital,
            available_capital=initial_capital,
            daily_loss_start=initial_capital,
            peak_capital=initial_capital,
        )
        self._current_vix: float = 20.0
        self._trade_history: List[dict] = []
        self._risk_log: List[dict] = []
        self._kill_switch_active = False

    async def initialize(self) -> None:
        self.bus.subscribe(EventType.ORDER_REQUESTED, self.handle_event)
        self.bus.subscribe(EventType.ORDER_FILLED, self.handle_event)
        self.bus.subscribe(EventType.POSITION_CLOSED, self.handle_event)
        self.bus.subscribe(EventType.MARKET_DATA_UPDATE, self.handle_event)
        logger.info("Risk Management Agent initialized — monitoring all orders")

    async def process_event(self, event: Event) -> None:
        if event.event_type == EventType.ORDER_REQUESTED:
            await self._evaluate_order_request(event)
        elif event.event_type == EventType.ORDER_FILLED:
            await self._handle_fill(event)
        elif event.event_type == EventType.POSITION_CLOSED:
            await self._handle_position_close(event)
        elif event.event_type == EventType.MARKET_DATA_UPDATE:
            await self._update_market_data(event)

    async def _evaluate_order_request(self, event: Event) -> None:
        """
        Gate every order through risk checks.
        Order passes only if ALL checks pass.
        """
        payload = event.payload
        symbol = payload.get("symbol", "")
        action = payload.get("action", "")
        confidence = float(payload.get("confidence", 0.5))

        # Skip if this is an emergency close-all
        if action == "CLOSE_ALL_POSITIONS":
            await self._handle_emergency_close(payload)
            return

        # ─── Pre-flight checks ───────────────────────────────────────────────
        checks = {
            "kill_switch": self._check_kill_switch_conditions(),
            "daily_loss": self._check_daily_loss(),
            "max_drawdown": self._check_max_drawdown(),
            "exposure": self._check_total_exposure(),
            "position_count": self._check_position_count(symbol),
            "vix_filter": self._check_vix_conditions(),
            "spread": self._check_spread(payload),
        }

        failed = {k: v for k, v in checks.items() if not v["pass"]}

        if failed:
            reasons = [v["reason"] for v in failed.values()]
            logger.warning(f"ORDER REJECTED: {symbol} {action} — {'; '.join(reasons)}")

            # If a hard kill-switch threshold (daily loss / drawdown) is breached,
            # formally activate the kill switch — not just veto this one order.
            # Otherwise repeated order requests would only be rejected one-by-one
            # without ever halting trading or closing open positions.
            kill_fail = checks.get("kill_switch", {"pass": True})
            if not kill_fail["pass"]:
                await self._activate_kill_switch(kill_fail["reason"])

            await self.publish(
                EventType.RISK_BREACH,
                {
                    "symbol": symbol,
                    "action": action,
                    "signal_id": payload.get("signal_id") or payload.get("source_signal_id"),
                    "rejected": True,
                    "reasons": reasons,
                    "original_request": payload,
                    "portfolio": self.portfolio.to_dict(),
                },
                priority=2,
            )
            return

        # ─── Position sizing ─────────────────────────────────────────────────
        price = float(payload.get("price", 0) or 0)
        if price <= 0:
            reason = f"Invalid order price {price!r}"
            logger.error(f"ORDER REJECTED: {symbol} {action} — {reason}")
            await self._reject_order_request(symbol, action, [reason], payload)
            return

        indicators = payload.get("indicators", {}) or {}
        atr = float(indicators.get("atr") or payload.get("atr") or 0)
        if atr <= 0:
            atr = price * 0.015  # Conservative fallback when no observed ATR exists

        direction = "BUY" if "BUY" in action else "SELL"
        requested_risk_pct = payload.get("requested_risk_pct")
        stop_loss = self._optional_positive_float(payload.get("stop_loss"))
        take_profit = self._optional_positive_float(payload.get("take_profit"))
        if stop_loss is not None or take_profit is not None:
            level_check = self._check_explicit_trade_levels(
                direction, price, stop_loss, take_profit
            )
            if not level_check["pass"]:
                logger.warning(
                    f"ORDER REJECTED: {symbol} {action} — {level_check['reason']}"
                )
                await self._reject_order_request(
                    symbol, action, [level_check["reason"]], payload
                )
                return
            sizing = self._calculate_position_size_from_levels(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence,
                requested_risk_pct=requested_risk_pct,
            )
        else:
            sizing = self._calculate_position_size(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                atr=atr,
                confidence=confidence,
                requested_risk_pct=requested_risk_pct,
            )

        if sizing.risk_reward_ratio + 1e-9 < self.params.min_risk_reward_ratio:
            reason = (
                f"R/R {sizing.risk_reward_ratio:.2f} < "
                f"min {self.params.min_risk_reward_ratio:.2f}"
            )
            logger.warning(f"ORDER REJECTED: {symbol} — {reason}")
            await self._reject_order_request(symbol, action, [reason], payload)
            return

        # ─── Approve with risk params attached ───────────────────────────────
        logger.info(
            f"ORDER APPROVED: {symbol} {sizing.direction} | "
            f"size=${sizing.position_size_usd:,.0f} | "
            f"stop={sizing.stop_loss:.4f} | tp={sizing.take_profit:.4f} | "
            f"R/R={sizing.risk_reward_ratio:.2f}"
        )

        await self.publish(
            EventType.RISK_ASSESSMENT,
            {
                "symbol": symbol,
                "risk_level": "NORMAL",
                "approved": True,
                "sizing": sizing.to_dict(),
                "original_request": payload,
                "portfolio_state": self.portfolio.to_dict(),
            },
            priority=2,
        )

    def _calculate_position_size(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        atr: float,
        confidence: float,
        requested_risk_pct: Optional[float] = None,
    ) -> PositionSizing:
        """
        Position sizing using ATR-based stops + Kelly fraction.
        
        Stop loss: 2x ATR from entry (captures normal volatility noise)
        Take profit: stop_distance * min_risk_reward
        Kelly fraction: confidence-adjusted, capped at max_position_pct
        """
        stop_distance = 2.0 * atr  # 2 ATR stop

        if direction == "BUY":
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + stop_distance * self.params.min_risk_reward_ratio
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - stop_distance * self.params.min_risk_reward_ratio

        # Kelly Criterion: f = (bp - q) / b
        # b = odds (R/R ratio), p = confidence, q = 1 - p
        b = self.params.min_risk_reward_ratio
        p = confidence
        q = 1 - p
        kelly_fraction = max(0.0, (b * p - q) / b)

        # Apply conservative scaling (half-Kelly is standard in professional trading)
        kelly_fraction *= 0.5

        # Apply VIX adjustment
        vix_multiplier = self._get_vix_multiplier()
        kelly_fraction *= vix_multiplier

        # Cap position size
        kelly_fraction = min(kelly_fraction, self.params.max_single_position_pct)

        risk_amount = self.portfolio.total_capital * self._risk_pct(requested_risk_pct)
        position_size_usd = (risk_amount / stop_distance) * entry_price
        position_size_usd = min(
            position_size_usd,
            self.portfolio.total_capital * kelly_fraction
        )
        position_size_units = position_size_usd / entry_price

        rr = abs(take_profit - entry_price) / max(abs(stop_loss - entry_price), 0.0001)

        return PositionSizing(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_units=position_size_units,
            position_size_usd=position_size_usd,
            risk_amount_usd=risk_amount,
            risk_reward_ratio=rr,
            kelly_fraction=kelly_fraction,
        )

    def _calculate_position_size_from_levels(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        confidence: float,
        requested_risk_pct: Optional[float] = None,
    ) -> PositionSizing:
        stop_distance = abs(entry_price - stop_loss)
        reward_distance = abs(take_profit - entry_price)
        rr = reward_distance / max(stop_distance, 0.0001)

        b = max(rr, 0.0001)
        p = confidence
        q = 1 - p
        kelly_fraction = max(0.0, (b * p - q) / b) * 0.5
        kelly_fraction *= self._get_vix_multiplier()
        kelly_fraction = min(kelly_fraction, self.params.max_single_position_pct)

        risk_amount = self.portfolio.total_capital * self._risk_pct(requested_risk_pct)
        position_size_usd = (risk_amount / stop_distance) * entry_price
        position_size_usd = min(
            position_size_usd,
            self.portfolio.total_capital * kelly_fraction,
        )
        position_size_units = position_size_usd / entry_price

        return PositionSizing(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_units=position_size_units,
            position_size_usd=position_size_usd,
            risk_amount_usd=risk_amount,
            risk_reward_ratio=rr,
            kelly_fraction=kelly_fraction,
        )

    async def _reject_order_request(
        self,
        symbol: str,
        action: str,
        reasons: List[str],
        original_request: dict,
    ) -> None:
        await self.publish(
            EventType.RISK_BREACH,
            {
                "symbol": symbol,
                "action": action,
                "signal_id": original_request.get("signal_id")
                or original_request.get("source_signal_id"),
                "rejected": True,
                "reasons": reasons,
                "original_request": original_request,
                "portfolio": self.portfolio.to_dict(),
            },
            priority=2,
        )

    def _optional_positive_float(self, value) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _check_explicit_trade_levels(
        self,
        direction: str,
        entry_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
    ) -> dict:
        if stop_loss is None or take_profit is None:
            return {
                "pass": False,
                "reason": "Explicit trade signals require both stop_loss and take_profit",
            }
        if abs(entry_price - stop_loss) <= 1e-12:
            return {"pass": False, "reason": "Stop loss equals entry price"}
        if direction == "BUY" and not (stop_loss < entry_price < take_profit):
            return {
                "pass": False,
                "reason": "BUY requires stop_loss < entry_price < take_profit",
            }
        if direction == "SELL" and not (take_profit < entry_price < stop_loss):
            return {
                "pass": False,
                "reason": "SELL requires take_profit < entry_price < stop_loss",
            }
        return {"pass": True, "reason": ""}

    def _risk_pct(self, requested_risk_pct: Optional[float]) -> float:
        if requested_risk_pct is None:
            return self.params.max_portfolio_risk_pct
        try:
            requested = float(requested_risk_pct)
        except (TypeError, ValueError):
            return self.params.max_portfolio_risk_pct
        requested = requested / 100 if requested > 1 else requested
        if requested <= 0:
            return self.params.max_portfolio_risk_pct
        return min(self.params.max_portfolio_risk_pct, requested)

    def _check_kill_switch_conditions(self) -> dict:
        """Auto-trigger kill switch if breach thresholds hit."""
        if self.portfolio.daily_loss_pct >= self.params.max_daily_loss_pct:
            return {"pass": False, "reason": f"Daily loss {self.portfolio.daily_loss_pct:.1%} >= {self.params.max_daily_loss_pct:.1%}"}
        if self.portfolio.drawdown_pct >= self.params.max_drawdown_pct:
            return {"pass": False, "reason": f"Drawdown {self.portfolio.drawdown_pct:.1%} >= {self.params.max_drawdown_pct:.1%}"}
        return {"pass": True, "reason": ""}

    def _check_daily_loss(self) -> dict:
        threshold = self.params.max_daily_loss_pct * 0.75  # Warning at 75%
        if self.portfolio.daily_loss_pct >= threshold:
            return {"pass": False, "reason": f"Near daily loss limit ({self.portfolio.daily_loss_pct:.1%})"}
        return {"pass": True, "reason": ""}

    def _check_max_drawdown(self) -> dict:
        threshold = self.params.max_drawdown_pct * 0.80
        if self.portfolio.drawdown_pct >= threshold:
            return {"pass": False, "reason": f"Near max drawdown ({self.portfolio.drawdown_pct:.1%})"}
        return {"pass": True, "reason": ""}

    def _check_total_exposure(self) -> dict:
        if self.portfolio.exposure_pct >= self.params.max_total_exposure_pct:
            return {"pass": False, "reason": f"Max exposure reached ({self.portfolio.exposure_pct:.1%})"}
        return {"pass": True, "reason": ""}

    def _check_position_count(self, symbol: str) -> dict:
        if symbol in self.portfolio.positions:
            return {"pass": False, "reason": f"Already have position in {symbol}"}
        return {"pass": True, "reason": ""}

    def _check_vix_conditions(self) -> dict:
        if self._current_vix >= self.params.extreme_vix_threshold:
            return {"pass": False, "reason": f"VIX extreme ({self._current_vix:.1f}) — no new positions"}
        return {"pass": True, "reason": ""}

    def _check_spread(self, payload: dict) -> dict:
        spread_bps = payload.get("spread_bps")
        if spread_bps is None:
            return {"pass": True, "reason": ""}
        spread_bps = float(spread_bps)
        if spread_bps > self.params.max_slippage_bps:
            return {
                "pass": False,
                "reason": f"Spread {spread_bps:.1f} bps > max {self.params.max_slippage_bps} bps",
            }
        return {"pass": True, "reason": ""}

    def _get_vix_multiplier(self) -> float:
        """Reduce position sizes when volatility is elevated."""
        if self._current_vix >= self.params.extreme_vix_threshold:
            return 0.0
        elif self._current_vix >= self.params.high_vix_threshold:
            return 0.5
        elif self._current_vix >= 25.0:
            return 0.75
        return 1.0

    async def _handle_fill(self, event: Event) -> None:
        """Update portfolio state after order fills."""
        p = event.payload
        symbol = p.get("symbol")
        fill_price = float(p.get("fill_price", 0))
        size_usd = float(p.get("position_size_usd", 0))
        direction = p.get("direction")

        if symbol and fill_price > 0:
            self.portfolio.positions[symbol] = {
                "entry_price": fill_price,
                "direction": direction,
                "size_usd": size_usd,
                "stop_loss": p.get("stop_loss"),
                "take_profit": p.get("take_profit"),
                "opened_at": time.time(),
            }
            self.portfolio.deployed_capital += size_usd
            self.portfolio.available_capital -= size_usd
            logger.info(f"Position opened: {symbol} {direction} ${size_usd:,.0f}")

    async def _handle_position_close(self, event: Event) -> None:
        """Update PnL and portfolio state after position close."""
        p = event.payload
        symbol = p.get("symbol")
        pnl = float(p.get("pnl", 0))

        if symbol and symbol in self.portfolio.positions:
            position = self.portfolio.positions.pop(symbol)
            self.portfolio.deployed_capital -= position["size_usd"]
            self.portfolio.available_capital += position["size_usd"] + pnl
            self.portfolio.total_capital += pnl
            self.portfolio.daily_pnl += pnl
            self.portfolio.total_pnl += pnl
            
            if self.portfolio.total_capital > self.portfolio.peak_capital:
                self.portfolio.peak_capital = self.portfolio.total_capital

            logger.info(f"Position closed: {symbol} | PnL: ${pnl:+,.2f}")
            
            # Check if we need to activate kill switch after loss
            kill_check = self._check_kill_switch_conditions()
            if not kill_check["pass"]:
                await self._activate_kill_switch(kill_check["reason"])

    async def _update_market_data(self, event: Event) -> None:
        """Track VIX updates for position sizing adjustments."""
        vix = event.payload.get("vix")
        if vix is not None:
            self._current_vix = float(vix)

    async def _handle_emergency_close(self, payload: dict) -> None:
        logger.critical(f"EMERGENCY CLOSE ALL: {payload.get('reason')}")
        if payload.get("emergency"):
            self._kill_switch_active = True
            return
        if self._kill_switch_active:
            return
        await self._activate_kill_switch(payload.get("reason", "Emergency closure"))

    async def _activate_kill_switch(self, reason: str) -> None:
        if self._kill_switch_active:
            return
        self._kill_switch_active = True
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
        await self.publish(
            EventType.KILL_SWITCH_ACTIVATED,
            {
                "reason": reason,
                "portfolio": self.portfolio.to_dict(),
                "timestamp": time.time(),
            },
            priority=1,  # Absolute maximum priority
        )

    def update_capital(self, new_capital: float) -> None:
        """Manual capital update for paper→live transitions."""
        self.portfolio.total_capital = new_capital
        self.portfolio.available_capital = new_capital - self.portfolio.deployed_capital
        if not self.portfolio.positions:
            self.portfolio.peak_capital = new_capital
            self.portfolio.daily_loss_start = new_capital
            self.portfolio.daily_pnl = 0.0
            self.portfolio.total_pnl = 0.0

    def deactivate_kill_switch(self) -> None:
        self._kill_switch_active = False

    @property
    def portfolio_state(self) -> dict:
        return self.portfolio.to_dict()

    @property
    def risk_parameters(self) -> dict:
        return {
            "max_portfolio_risk_pct": self.params.max_portfolio_risk_pct,
            "max_total_exposure_pct": self.params.max_total_exposure_pct,
            "max_daily_loss_pct": self.params.max_daily_loss_pct,
            "max_drawdown_pct": self.params.max_drawdown_pct,
            "max_slippage_bps": self.params.max_slippage_bps,
            "current_vix": self._current_vix,
            "vix_multiplier": self._get_vix_multiplier(),
        }

    def reconcile_broker_positions(self, positions: List[dict], equity: float) -> None:
        """Trust the broker snapshot for deployed capital and account equity."""
        self.portfolio.positions = {
            p["symbol"]: {
                "entry_price": p.get("price_open", 0),
                "direction": p.get("direction", "BUY"),
                "size_usd": float(p.get("margin_required") or p.get("notional_usd") or 0),
                "stop_loss": p.get("stop_loss"),
                "take_profit": p.get("take_profit"),
                "opened_at": p.get("time", time.time()),
            }
            for p in positions
            if p.get("symbol")
        }
        deployed = sum(float(p.get("margin_required") or p.get("notional_usd") or 0) for p in positions)
        self.portfolio.total_capital = equity
        self.portfolio.deployed_capital = deployed
        self.portfolio.available_capital = max(0.0, equity - deployed)
        if equity > self.portfolio.peak_capital:
            self.portfolio.peak_capital = equity
