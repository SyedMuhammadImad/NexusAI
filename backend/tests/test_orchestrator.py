import pytest

from core.event_bus import Event, EventType
from core.orchestrator import MasterOrchestrator


def signal(source_agent, direction="BUY", price=95_000, confidence=0.95):
    event_type = (
        EventType.STRATEGY_SIGNAL
        if source_agent == "strategy_agent"
        else EventType.MACRO_SIGNAL
        if source_agent == "broker_confirmation_agent"
        else EventType.SENTIMENT_SIGNAL
    )
    return Event(
        event_type=event_type,
        source_agent=source_agent,
        payload={
            "symbol": "BTC-USD",
            "direction": direction,
            "confidence": confidence,
            "reasoning": "test signal",
            "price": price,
            "indicators": {"atr": 10.0},
        },
    )


@pytest.mark.asyncio
async def test_orchestrator_dispatches_order_with_flat_signal_price():
    orchestrator = MasterOrchestrator()
    orchestrator._cooldown_seconds = 0
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    orchestrator.publish = capture

    await orchestrator.process_event(signal("strategy_agent"))
    await orchestrator.process_event(signal("sentiment_agent"))

    orders = [payload for event_type, payload, _, _ in published if event_type == EventType.ORDER_REQUESTED]
    assert len(orders) == 1
    assert orders[0]["symbol"] == "BTC-USD"
    assert orders[0]["action"] == "EXECUTE_BUY"
    assert orders[0]["price"] == 95_000
    assert orders[0]["indicators"]["atr"] == 10.0
    assert orders[0]["agent_signals"]


@pytest.mark.asyncio
async def test_orchestrator_blocks_without_independent_confirmation():
    orchestrator = MasterOrchestrator()
    orchestrator._cooldown_seconds = 0
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    orchestrator.publish = capture

    await orchestrator.process_event(signal("strategy_agent"))
    await orchestrator.process_event(signal("unknown_agent"))

    assert [
        payload for event_type, payload, _, _ in published
        if event_type == EventType.ORDER_REQUESTED
    ] == []
    assert orchestrator.recent_decisions[-1]["blocked_by"] == "strict_agent_gate"


@pytest.mark.asyncio
async def test_orchestrator_accepts_broker_confirmation_agent():
    orchestrator = MasterOrchestrator()
    orchestrator._cooldown_seconds = 0
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    orchestrator.publish = capture

    await orchestrator.process_event(signal("strategy_agent"))
    await orchestrator.process_event(signal("broker_confirmation_agent"))

    orders = [payload for event_type, payload, _, _ in published if event_type == EventType.ORDER_REQUESTED]
    assert len(orders) == 1
    assert orders[0]["action"] == "EXECUTE_BUY"


@pytest.mark.asyncio
async def test_orchestrator_blocks_low_confidence_agent_agreement():
    orchestrator = MasterOrchestrator(cooldown_seconds=0)
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    orchestrator.publish = capture

    await orchestrator.process_event(signal("strategy_agent", confidence=0.56))
    await orchestrator.process_event(signal("broker_confirmation_agent", confidence=0.53))

    assert [
        payload for event_type, payload, _, _ in published
        if event_type == EventType.ORDER_REQUESTED
    ] == []
    assert orchestrator.recent_decisions[-1]["blocked_by"] == "confidence_gate"


@pytest.mark.asyncio
async def test_orchestrator_blocks_new_signal_orders_after_kill_switch():
    orchestrator = MasterOrchestrator()
    orchestrator._cooldown_seconds = 0
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    orchestrator.publish = capture

    await orchestrator.process_event(Event(
        event_type=EventType.KILL_SWITCH_ACTIVATED,
        source_agent="risk_agent",
        payload={"reason": "test breach"},
    ))
    assert published[-1][1]["action"] == "CLOSE_ALL_POSITIONS"

    published.clear()
    await orchestrator.process_event(signal("strategy_agent"))
    await orchestrator.process_event(signal("sentiment_agent"))

    assert published == []
