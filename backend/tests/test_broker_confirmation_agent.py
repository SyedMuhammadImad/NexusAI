import pytest

from agents.broker_confirmation_agent import BrokerMomentumConfirmationAgent
from core.event_bus import Event, EventType


def broker_tick(symbol: str, price: float) -> Event:
    return Event(
        event_type=EventType.MARKET_DATA_UPDATE,
        source_agent="exness_mt5",
        payload={
            "symbol": symbol,
            "asset_class": "broker",
            "price": price,
        },
    )


@pytest.mark.asyncio
async def test_broker_confirmation_agent_emits_momentum_signal():
    agent = BrokerMomentumConfirmationAgent(
        symbols=["EURUSDm"],
        min_history=4,
        cooldown_seconds=0,
        min_move_bps=0.1,
    )
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    for price in [1.1000, 1.1001, 1.1002, 1.1004]:
        await agent.process_event(broker_tick("EURUSDm", price))

    assert len(published) == 1
    event_type, payload, priority, _ = published[0]
    assert event_type == EventType.MACRO_SIGNAL
    assert priority == 4
    assert payload["symbol"] == "EURUSDm"
    assert payload["direction"] == "BUY"
    assert payload["price"] == 1.1004


@pytest.mark.asyncio
async def test_broker_confirmation_agent_ignores_unlisted_symbol():
    agent = BrokerMomentumConfirmationAgent(
        symbols=["EURUSDm"],
        min_history=4,
        cooldown_seconds=0,
        min_move_bps=0.1,
    )
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    for price in [80.0, 80.1, 80.2, 80.3]:
        await agent.process_event(broker_tick("USOILm", price))

    assert published == []
