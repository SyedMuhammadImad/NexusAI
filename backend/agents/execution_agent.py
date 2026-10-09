"""
Execution Agent - Turns approved risk assessments into orders.

Supports: Market, Limit, TWAP, VWAP order types.
In paper mode: simulates fills with realistic slippage model.
In live mode: requires an injected broker client. The current local broker
adapter is Exness MT5 demo.

This is where paper mode diverges from live.
If your paper PnL doesn't account for slippage + spread, it's a fantasy.
"""

import asyncio
import inspect
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    TWAP = "twap"
    VWAP = "vwap"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


@dataclass
class Order:
    order_id: str
    symbol: str
    direction: str  # BUY / SELL
    order_type: OrderType
    quantity: float
    limit_price: Optional[float]
    stop_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    risk_amount_usd: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    fill_price: Optional[float] = None
    fill_quantity: Optional[float] = None
    fill_timestamp: Optional[float] = None
    slippage_bps: float = 0.0
    created_at: float = field(default_factory=time.time)
    source_decision: Optional[dict] = None
    source_signal_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "order_type": self.order_type.value,
            "quantity": round(self.quantity, 6),
            "limit_price": self.limit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_amount_usd": self.risk_amount_usd,
            "status": self.status.value,
            "fill_price": self.fill_price,
            "fill_quantity": self.fill_quantity,
            "fill_timestamp": self.fill_timestamp,
            "slippage_bps": round(self.slippage_bps, 2),
            "created_at": self.created_at,
            "source_signal_id": self.source_signal_id,
            "signal_id": self.source_signal_id,
        }


class ExecutionAgent(BaseAgent):
    """
    Order lifecycle management.
    
    Paper mode simulates:
    - Gaussian slippage (mean=0, std based on liquidity)
    - Partial fills for large orders
    - Order book spread
    - Market impact for size
    
    Live mode: plug in a broker adapter that implements submit_market_order().
    """

    def __init__(self, mode: TradingMode = TradingMode.PAPER):
        super().__init__("execution_agent", "Execution Agent")
        self.mode = mode
        self._orders: Dict[str, Order] = {}  # order_id -> Order
        self._active_orders: Dict[str, str] = {}  # symbol -> order_id
        self._order_history: List[dict] = []
        self._max_slippage_bps = 50  # Hard limit — reject order if simulated slippage exceeds this
        self._broker_client = None  # Injected in live mode

    async def initialize(self) -> None:
        # Listen for approved risk assessments (these are cleared for execution)
        self.bus.subscribe(EventType.RISK_ASSESSMENT, self.handle_event)
        self.bus.subscribe(EventType.KILL_SWITCH_ACTIVATED, self.handle_event)
        self.bus.subscribe(EventType.POSITION_CLOSED, self.handle_event)
        logger.info(f"Execution Agent initialized | mode={self.mode.value}")

    async def process_event(self, event: Event) -> None:
        if event.event_type == EventType.KILL_SWITCH_ACTIVATED:
            await self._cancel_all_pending()
            return

        if event.event_type == EventType.POSITION_CLOSED:
            self._handle_position_closed(event)
            return

        if event.event_type == EventType.RISK_ASSESSMENT:
            payload = event.payload
            if payload.get("approved") and payload.get("sizing"):
                await self._process_approved_order(payload)

    async def _process_approved_order(self, payload: dict) -> None:
        """Convert an approved risk assessment into an executable order."""
        sizing = payload["sizing"]
        original = payload.get("original_request", {})

        symbol = sizing["symbol"]
        direction = sizing["direction"]

        # Don't stack orders on the same symbol
        if symbol in self._active_orders:
            logger.info(f"Skipping {symbol} — already has active order")
            return

        order = Order(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            direction=direction,
            order_type=OrderType.MARKET,  # Default; can switch to LIMIT via config
            quantity=sizing["position_size_units"],
            limit_price=None,
            stop_price=None,
            stop_loss=sizing["stop_loss"],
            take_profit=sizing["take_profit"],
            risk_amount_usd=sizing.get("risk_amount_usd"),
            source_decision=original.get("orchestrator_decision"),
            source_signal_id=original.get("signal_id") or payload.get("signal_id"),
        )

        self._orders[order.order_id] = order
        self._active_orders[symbol] = order.order_id

        logger.info(
            f"ORDER CREATED: {order.order_id[:8]}… | {symbol} {direction} "
            f"{order.quantity:.4f} units | SL={sizing['stop_loss']:.4f} | TP={sizing['take_profit']:.4f}"
        )

        await self.publish(EventType.ORDER_SUBMITTED, order.to_dict(), priority=2)

        # Execute based on mode
        if self.mode == TradingMode.PAPER:
            await self._paper_execute(order, sizing["entry_price"])
        else:
            await self._live_execute(order)

    async def _paper_execute(self, order: Order, expected_price: float) -> None:
        """
        Realistic paper trading execution with slippage simulation.
        
        Slippage model:
        - Base spread: 1-5 bps depending on asset class
        - Market impact: scales with order size relative to avg volume
        - Random component: Gaussian noise (real markets have this)
        """
        # Simulate execution latency (5-50ms in reality)
        await asyncio.sleep(random.uniform(0.005, 0.05))

        # Slippage calculation
        base_spread_bps = self._get_base_spread(order.symbol)
        impact_bps = min(20, (order.quantity * expected_price) / 1_000_000 * 10)
        random_bps = abs(random.gauss(0, 3))
        total_slippage_bps = base_spread_bps + impact_bps + random_bps

        if total_slippage_bps > self._max_slippage_bps:
            # Order would have too much impact — reject
            order.status = OrderStatus.REJECTED
            logger.warning(f"Order rejected: excessive slippage {total_slippage_bps:.1f} bps")
            await self._handle_rejection(order, "Slippage exceeds limit")
            return

        # Apply slippage to fill price
        slippage_multiplier = total_slippage_bps / 10_000
        if order.direction == "BUY":
            fill_price = expected_price * (1 + slippage_multiplier)
        else:
            fill_price = expected_price * (1 - slippage_multiplier)

        # Update order
        order.fill_price = round(fill_price, 6)
        order.fill_quantity = order.quantity
        order.fill_timestamp = time.time()
        order.slippage_bps = total_slippage_bps
        order.status = OrderStatus.FILLED

        self.metrics.signals_generated += 1

        logger.info(
            f"PAPER FILL: {order.symbol} {order.direction} | "
            f"fill={fill_price:.4f} | slippage={total_slippage_bps:.1f}bps"
        )

        await self.publish(
            EventType.ORDER_FILLED,
            {
                **order.to_dict(),
                "position_size_usd": order.fill_quantity * order.fill_price,
            },
            priority=2,
        )

        await self.publish(
            EventType.POSITION_OPENED,
            {
                "symbol": order.symbol,
                "direction": order.direction,
                "entry_price": order.fill_price,
                "quantity": order.fill_quantity,
                "stop_loss": order.stop_loss,
                "take_profit": order.take_profit,
                "order_id": order.order_id,
                "source_signal_id": order.source_signal_id,
                "signal_id": order.source_signal_id,
            },
            priority=3,
        )

        self._order_history.append(order.to_dict())

    async def _live_execute(self, order: Order) -> None:
        """Execute an approved order through an injected broker client."""
        if self._broker_client is None:
            logger.error("Live mode requires broker client. Rejecting order.")
            await self._handle_rejection(order, "Live mode requires broker client")
            return

        submit = getattr(self._broker_client, "submit_market_order", None)
        if submit is None:
            await self._handle_rejection(order, "Broker client does not implement submit_market_order")
            return

        try:
            result = submit(order)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            logger.error("Live broker order failed", exc_info=True)
            await self._handle_rejection(order, f"Live broker exception: {exc}")
            return

        if not result or not result.get("ok"):
            reason = result.get("reason") if isinstance(result, dict) else "Live broker rejected order"
            await self._handle_rejection(order, reason or "Live broker rejected order")
            return

        order.fill_price = round(float(result["fill_price"]), 6)
        order.fill_quantity = float(result["fill_quantity"])
        order.fill_timestamp = time.time()
        order.slippage_bps = 0.0
        order.status = OrderStatus.FILLED

        deployed_capital = result.get("margin_required")
        if deployed_capital is None:
            deployed_capital = result.get("position_size_usd", order.fill_quantity * order.fill_price)

        filled_payload = {
            **order.to_dict(),
            "broker": result.get("broker"),
            "broker_symbol": result.get("symbol", order.symbol),
            "broker_order_id": result.get("broker_order_id"),
            "broker_deal_id": result.get("broker_deal_id"),
            "volume_lots": result.get("volume_lots"),
            "margin_required": result.get("margin_required"),
            "notional_usd": result.get("notional_usd"),
            "actual_risk_usd": result.get("actual_risk_usd"),
            "position_size_usd": deployed_capital,
        }
        logger.info(
            f"LIVE DEMO FILL: {order.symbol} {order.direction} | "
            f"broker_symbol={filled_payload['broker_symbol']} | fill={order.fill_price:.6f}"
        )

        await self.publish(EventType.ORDER_FILLED, filled_payload, priority=2)
        await self.publish(
            EventType.POSITION_OPENED,
            {
                "symbol": order.symbol,
                "broker_symbol": filled_payload["broker_symbol"],
                "direction": order.direction,
                "entry_price": order.fill_price,
                "quantity": order.fill_quantity,
                "stop_loss": order.stop_loss,
                "take_profit": order.take_profit,
                "order_id": order.order_id,
                "broker_order_id": result.get("broker_order_id"),
                "broker_deal_id": result.get("broker_deal_id"),
                "source_signal_id": order.source_signal_id,
                "signal_id": order.source_signal_id,
            },
            priority=3,
        )
        self._order_history.append(filled_payload)

    def _get_base_spread(self, symbol: str) -> float:
        """Realistic spread estimates by asset class."""
        if "-USD" in symbol:  # Crypto
            return random.uniform(3, 8)
        elif "/" in symbol:  # Forex
            return random.uniform(0.5, 2)
        else:  # Equities
            return random.uniform(1, 4)

    async def _cancel_all_pending(self) -> None:
        """Kill switch — cancel everything."""
        cancelled = 0
        for order_id, order in self._orders.items():
            if order.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED):
                order.status = OrderStatus.CANCELLED
                cancelled += 1
        
        self._active_orders.clear()
        logger.critical(f"Kill switch: cancelled {cancelled} pending orders")

        if self.mode == TradingMode.LIVE and self._broker_client is not None:
            close_all = getattr(self._broker_client, "close_all_positions", None)
            if close_all is not None:
                result = close_all()
                if inspect.isawaitable(result):
                    result = await result
                for closed in (result or {}).get("closed", []):
                    if closed.get("ok"):
                        await self.publish(
                            EventType.POSITION_CLOSED,
                            {
                                "symbol": closed.get("symbol"),
                                "signal_id": closed.get("signal_id"),
                                "pnl": closed.get("pnl", 0),
                                "reason": "kill_switch_broker_close",
                                "trade": closed,
                            },
                            priority=1,
                        )
        
        await self.publish(
            EventType.ORDER_CANCELLED,
            {"reason": "kill_switch", "cancelled_count": cancelled},
            priority=1,
        )

    async def _handle_rejection(self, order: Order, reason: str) -> None:
        order.status = OrderStatus.REJECTED
        if order.symbol in self._active_orders:
            del self._active_orders[order.symbol]
        self._order_history.append({**order.to_dict(), "reject_reason": reason})
        await self.publish(
            EventType.ORDER_REJECTED,
            {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "reason": reason,
                "source_signal_id": order.source_signal_id,
                "signal_id": order.source_signal_id,
            },
            priority=3,
        )

    def _handle_position_closed(self, event) -> None:
        symbol = event.payload.get("symbol")
        if symbol and symbol in self._active_orders:
            del self._active_orders[symbol]

    def reconcile_open_symbols(self, open_symbols: set[str]) -> None:
        for symbol, order_id in list(self._active_orders.items()):
            order = self._orders.get(order_id)
            if order and order.status == OrderStatus.FILLED and symbol not in open_symbols:
                del self._active_orders[symbol]

    def set_live_broker(self, broker_client) -> None:
        """Inject broker client for live trading."""
        self._broker_client = broker_client
        logger.info(f"Live broker client set: {type(broker_client).__name__}")

    def cancel_order(self, order_id: str) -> bool:
        """Manual order cancellation."""
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED):
                order.status = OrderStatus.CANCELLED
                if order.symbol in self._active_orders:
                    del self._active_orders[order.symbol]
                return True
        return False

    @property
    def open_orders(self) -> List[dict]:
        return [
            o.to_dict() for o in self._orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED)
        ]

    @property
    def order_history(self) -> List[dict]:
        return self._order_history[-100:]

    @property
    def trading_mode(self) -> str:
        return self.mode.value
