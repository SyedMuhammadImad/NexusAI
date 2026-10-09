import pytest

from agents.advanced_agents import LearningAgent
from core.event_bus import Event, EventType


class DummyOrchestrator:
    def __init__(self):
        self._weights = {"strategy_agent": 0.30, "sentiment_agent": 0.15}

    @property
    def agent_weights(self):
        return self._weights.copy()

    def update_agent_weight(self, agent_id, new_weight):
        self._weights[agent_id] = new_weight


def decision():
    return {
        "symbol": "EURUSDm",
        "action": "EXECUTE_BUY",
        "signal_details": [
            {"agent_id": "strategy_agent", "direction": "BUY"},
            {"agent_id": "sentiment_agent", "direction": "SELL"},
        ],
        "reasoning": ["wording can change without breaking attribution"],
    }


@pytest.mark.asyncio
async def test_learning_agent_uses_structured_signal_details_for_attribution():
    orchestrator = DummyOrchestrator()
    agent = LearningAgent(orchestrator=orchestrator)
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    for _ in range(5):
        agent._pending_decisions.append({"decision": decision(), "timestamp": 1.0})
        await agent._attribute_outcome(
            Event(
                event_type=EventType.POSITION_CLOSED,
                source_agent="test",
                payload={"symbol": "EURUSDm", "pnl": 10.0},
            )
        )

    assert orchestrator.agent_weights["strategy_agent"] > 0.30
    assert orchestrator.agent_weights["sentiment_agent"] < 0.15
    assert published[-1][0] == EventType.WEIGHT_UPDATE
