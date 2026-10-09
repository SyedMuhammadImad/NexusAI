import pytest

from agents.execution_agent import ExecutionAgent, Order, OrderStatus, OrderType, TradingMode
from core.event_bus import Event, EventType


@pytest.mark.asyncio
async def test_live_mode_without_broker_rejects_order_without_price_fallback():
    agent = ExecutionAgent(mode=TradingMode.LIVE)
    order = Order(
        order_id="order-1",
        symbol="BTC-USD",
        direction="BUY",
        order_type=OrderType.MARKET,
        quantity=1.0,
        limit_price=None,
        stop_price=None,
        stop_loss=90_000,
        take_profit=100_000,
    )
    agent._active_orders[order.symbol] = order.order_id
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._live_execute(order)

    assert order.status == OrderStatus.REJECTED
    assert order.symbol not in agent._active_orders
    assert published == [
        (
            EventType.ORDER_REJECTED,
            {
                "order_id": "order-1",
                "symbol": "BTC-USD",
                "reason": "Live mode requires broker client",
                "source_signal_id": None,
                "signal_id": None,
            },
            3,
            None,
        )
    ]


@pytest.mark.asyncio
async def test_live_mode_publishes_broker_fill():
    class FakeBroker:
        def submit_market_order(self, order):
            return {
                "ok": True,
                "broker": "exness_mt5",
                "symbol": "XAUUSDm",
                "fill_price": 2301.55,
                "fill_quantity": 1.0,
                "volume_lots": 0.01,
                "position_size_usd": 2301.55,
                "broker_order_id": 11,
                "broker_deal_id": 22,
            }

    agent = ExecutionAgent(mode=TradingMode.LIVE)
    agent.set_live_broker(FakeBroker())
    order = Order(
        order_id="order-2",
        symbol="XAUUSDm",
        direction="BUY",
        order_type=OrderType.MARKET,
        quantity=0.001,
        limit_price=None,
        stop_price=None,
        stop_loss=2200.0,
        take_profit=2400.0,
    )
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._live_execute(order)

    assert order.status == OrderStatus.FILLED
    assert order.fill_price == 2301.55
    assert published[0][0] == EventType.ORDER_FILLED
    assert published[0][1]["broker"] == "exness_mt5"
    assert published[0][1]["broker_symbol"] == "XAUUSDm"
    assert published[1][0] == EventType.POSITION_OPENED


@pytest.mark.asyncio
async def test_signal_id_propagates_from_risk_assessment_to_fill_and_position():
    agent = ExecutionAgent(mode=TradingMode.PAPER)
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._process_approved_order(
        {
            "sizing": {
                "symbol": "EURUSDm",
                "direction": "BUY",
                "entry_price": 1.1,
                "stop_loss": 1.09,
                "take_profit": 1.12,
                "position_size_units": 1000,
                "risk_amount_usd": 10.0,
            },
            "original_request": {
                "signal_id": "private-signal-1",
                "source": "image_execution_upload",
            },
        }
    )

    filled = [payload for event_type, payload, _, _ in published if event_type == EventType.ORDER_FILLED]
    opened = [payload for event_type, payload, _, _ in published if event_type == EventType.POSITION_OPENED]
    assert filled[0]["signal_id"] == "private-signal-1"
    assert opened[0]["signal_id"] == "private-signal-1"


@pytest.mark.asyncio
async def test_rejected_order_is_visible_in_order_history():
    agent = ExecutionAgent(mode=TradingMode.LIVE)
    order = Order(
        order_id="order-3",
        symbol="USOILm",
        direction="BUY",
        order_type=OrderType.MARKET,
        quantity=1.0,
        limit_price=None,
        stop_price=None,
        stop_loss=80.0,
        take_profit=90.0,
    )
    agent._active_orders[order.symbol] = order.order_id
    agent.publish = capture_noop

    await agent._handle_rejection(order, "broker minimum volume risk exceeds approved risk")

    assert agent.order_history[-1]["status"] == "rejected"
    assert "broker minimum volume risk" in agent.order_history[-1]["reject_reason"]


def test_position_close_releases_active_symbol():
    agent = ExecutionAgent(mode=TradingMode.LIVE)
    agent._active_orders["EURUSDm"] = "order-4"

    agent._handle_position_closed(Event(
        event_type=EventType.POSITION_CLOSED,
        source_agent="portfolio_manager",
        payload={"symbol": "EURUSDm", "pnl": 1.0},
    ))

    assert "EURUSDm" not in agent._active_orders


async def capture_noop(event_type, payload, priority=5, correlation_id=None):
    return None
