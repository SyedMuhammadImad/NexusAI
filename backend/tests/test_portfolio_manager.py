import pytest
from starlette.responses import JSONResponse

from agents.portfolio_regime_agents import PortfolioManagerAgent
from core.event_bus import Event, EventType


def filled_order():
    return Event(
        event_type=EventType.ORDER_FILLED,
        source_agent="execution_agent",
        payload={
            "order_id": "order-1",
            "symbol": "BTC-USD",
            "direction": "BUY",
            "fill_price": 100.0,
            "fill_quantity": 10.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
        },
    )


@pytest.mark.asyncio
async def test_portfolio_closes_position_on_stop_loss():
    agent = PortfolioManagerAgent()
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._handle_fill(filled_order())
    await agent._handle_price_update(Event(
        event_type=EventType.MARKET_DATA_UPDATE,
        source_agent="test",
        payload={"symbol": "BTC-USD", "price": 94.0},
    ))

    closed = [payload for event_type, payload, _, _ in published if event_type == EventType.POSITION_CLOSED]
    assert agent.portfolio_summary["open_positions"] == 0
    assert closed[0]["reason"] == "stop_loss"
    assert closed[0]["pnl"] == -60.0


@pytest.mark.asyncio
async def test_portfolio_closes_all_positions_on_kill_switch():
    agent = PortfolioManagerAgent()
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._handle_fill(filled_order())
    await agent._handle_price_update(Event(
        event_type=EventType.MARKET_DATA_UPDATE,
        source_agent="test",
        payload={"symbol": "BTC-USD", "price": 98.0},
    ))
    await agent._handle_kill_switch(Event(
        event_type=EventType.KILL_SWITCH_ACTIVATED,
        source_agent="risk_agent",
        payload={"reason": "daily loss"},
    ))

    closed = [payload for event_type, payload, _, _ in published if event_type == EventType.POSITION_CLOSED]
    assert agent.portfolio_summary["open_positions"] == 0
    assert closed[0]["reason"] == "daily loss"
    assert closed[0]["pnl"] == -20.0


def test_performance_metrics_are_json_safe_when_there_are_no_losses():
    agent = PortfolioManagerAgent()
    agent._closed_trades = [{"pnl": 5.0}, {"pnl": 3.0}]

    metrics = agent.performance_metrics

    assert metrics["profit_factor"] is None
    JSONResponse({"metrics": metrics})
