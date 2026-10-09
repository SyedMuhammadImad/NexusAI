import pytest

from agents.sentiment_agent import NEWS_SEARCH_TERMS, NEWS_TEMPLATES, SentimentAgent
from core.event_bus import EventType


def test_sentiment_agent_has_exness_symbol_inputs():
    assert "EURUSDm" in NEWS_TEMPLATES
    assert "USOILm" in NEWS_TEMPLATES
    assert NEWS_SEARCH_TERMS["EURUSDm"] == "EUR USD forex euro dollar"
    assert NEWS_SEARCH_TERMS["USOILm"] == "WTI crude oil US oil"


@pytest.mark.asyncio
async def test_sentiment_agent_emits_broker_symbol_signal():
    agent = SentimentAgent()
    agent.add_symbol("EURUSDm")
    published = []

    async def capture(event_type, payload, priority=5, correlation_id=None):
        published.append((event_type, payload, priority, correlation_id))

    agent.publish = capture

    await agent._ingest("Euro strengthens as dollar softens after economic data", "reuters", ["EURUSDm"])
    await agent._ingest("ECB policy comments support euro against dollar", "reuters", ["EURUSDm"])

    assert len(published) == 1
    event_type, payload, priority, _ = published[0]
    assert event_type == EventType.SENTIMENT_SIGNAL
    assert priority == 4
    assert payload["symbol"] == "EURUSDm"
    assert payload["direction"] == "BUY"
    assert payload["confidence"] >= 0.45
