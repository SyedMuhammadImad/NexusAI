import pytest

from agents.risk_agent import RiskManagementAgent, RiskParameters
from core.event_bus import Event, EventType


def order_request(price, symbol="BTC-USD", action="EXECUTE_BUY"):
    return Event(
        event_type=EventType.ORDER_REQUESTED,
        source_agent="test",
        payload={
            "symbol": symbol,
            "action": action,
            "confidence": 0.9,
            "price": price,
        },
    )


def test_update_capital_resets_empty_portfolio_baselines():
    agent = RiskManagementAgent(initial_capital=100_000.0)

    agent.update_capital(100.0)

    state = agent.portfolio_state
    assert state["total_capital"] == 100.0
    assert state["available_capital"] == 100.0
    assert state["drawdown_pct"] == 0.0
    assert state["daily_loss_pct"] == 0.0


@pytest.mark.asyncio
async def test_risk_agent_rejects_missing_or_zero_price_without_silent_fallback():
    agent = RiskManagementAgent()
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._evaluate_order_request(order_request(0))

    assert len(published) == 1
    event_type, payload, _, _ = published[0]
    assert event_type == EventType.RISK_BREACH
    assert payload["rejected"] is True
    assert "Invalid order price" in payload["reasons"][0]


@pytest.mark.asyncio
async def test_risk_agent_uses_flat_order_price_for_sizing():
    agent = RiskManagementAgent()
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._evaluate_order_request(order_request(95_000))

    assert len(published) == 1
    event_type, payload, _, _ = published[0]
    assert event_type == EventType.RISK_ASSESSMENT
    assert payload["approved"] is True
    assert payload["sizing"]["entry_price"] == 95_000
    assert payload["sizing"]["position_size_usd"] > 1_000


@pytest.mark.asyncio
async def test_risk_agent_uses_explicit_stop_and_take_profit_from_private_signal():
    agent = RiskManagementAgent()
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    event = order_request(1.1620, symbol="EURUSDm")
    event.payload["stop_loss"] = 1.1600
    event.payload["take_profit"] = 1.1660
    event.payload["requested_risk_pct"] = 0.005

    await agent._evaluate_order_request(event)

    assert len(published) == 1
    event_type, payload, _, _ = published[0]
    assert event_type == EventType.RISK_ASSESSMENT
    sizing = payload["sizing"]
    assert sizing["stop_loss"] == 1.16
    assert sizing["take_profit"] == 1.166
    assert sizing["risk_reward_ratio"] == 2.0
    assert sizing["risk_amount_usd"] == 500.0


@pytest.mark.asyncio
async def test_risk_agent_activates_kill_switch_when_hard_loss_threshold_is_breached():
    params = RiskParameters(max_daily_loss_pct=0.001, max_drawdown_pct=0.15)
    agent = RiskManagementAgent(params=params)
    agent.portfolio.total_capital = 99_800.0
    agent.portfolio.daily_loss_start = 100_000.0
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._evaluate_order_request(order_request(95_000))

    event_types = [event_type for event_type, _, _, _ in published]
    assert EventType.KILL_SWITCH_ACTIVATED in event_types
    assert EventType.RISK_BREACH in event_types
    assert agent._kill_switch_active is True
