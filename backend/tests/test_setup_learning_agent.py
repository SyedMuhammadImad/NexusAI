import pytest

from agents.setup_learning_agent import SetupLearningAgent
from core.event_bus import Event, EventType
from services.setup_learning_store import SetupLearningStore


@pytest.mark.asyncio
async def test_setup_learning_agent_tracks_provider_trade_lifecycle(tmp_path):
    store = SetupLearningStore(db_path=str(tmp_path / "setup_learning.sqlite3"))
    agent = SetupLearningAgent(store=store)

    await agent.process_event(
        Event(
            event_type=EventType.TRADE_SIGNAL_ACCEPTED,
            source_agent="image_signal_upload",
            payload={
                "signal_id": "sig-1",
                "instrument": "EURUSDm",
                "direction": "BUY",
                "entry_type": "MARKET",
                "stop_loss": 1.09,
                "take_profit": 1.12,
                "requested_risk_pct": 0.5,
                "parser_confidence": 1.0,
                "signal_age": 1.2,
                "message_timestamp": 1_700_000_000,
                "validation_status": "ACCEPTED",
            },
        )
    )
    await agent.process_event(
        Event(
            event_type=EventType.ORDER_FILLED,
            source_agent="execution_agent",
            payload={
                "signal_id": "sig-1",
                "symbol": "EURUSDm",
                "direction": "BUY",
                "fill_price": 1.1,
                "fill_quantity": 1000,
                "stop_loss": 1.09,
                "take_profit": 1.12,
                "risk_amount_usd": 10.0,
            },
        )
    )
    await agent.process_event(
        Event(
            event_type=EventType.POSITION_CLOSED,
            source_agent="portfolio_manager",
            payload={
                "signal_id": "sig-1",
                "symbol": "EURUSDm",
                "pnl": 20.0,
                "reason": "take_profit",
            },
        )
    )

    summary = agent.learning_summary()

    assert summary["learning_mode"] == "observation_only"
    assert summary["automation_ready"] is False
    assert summary["totals"]["tracked_setups"] == 1
    assert summary["totals"]["filled_setups"] == 1
    assert summary["totals"]["closed_setups"] == 1
    assert summary["totals"]["winning_setups"] == 1
    assert summary["totals"]["avg_pnl"] == 20.0
    assert summary["totals"]["avg_pnl_r"] == 2.0
    assert summary["by_symbol_direction"][0]["instrument"] == "EURUSDm"
    assert summary["by_symbol_direction"][0]["direction"] == "BUY"
    assert summary["by_symbol_direction"][0]["win_rate_pct"] == 100.0
    assert summary["recent_setups"][0]["signal_id"] == "sig-1"


@pytest.mark.asyncio
async def test_setup_learning_agent_records_risk_rejection(tmp_path):
    store = SetupLearningStore(db_path=str(tmp_path / "setup_learning.sqlite3"))
    agent = SetupLearningAgent(store=store)

    await agent.process_event(
        Event(
            event_type=EventType.TRADE_SIGNAL_ACCEPTED,
            source_agent="image_signal_upload",
            payload={
                "signal_id": "sig-2",
                "instrument": "USOILm",
                "direction": "SELL",
                "validation_status": "ACCEPTED",
            },
        )
    )
    await agent.process_event(
        Event(
            event_type=EventType.RISK_BREACH,
            source_agent="risk_agent",
            payload={
                "signal_id": "sig-2",
                "symbol": "USOILm",
                "reasons": ["Spread 80.0 bps > max 50 bps"],
            },
        )
    )

    setup = agent.learning_summary()["recent_setups"][0]
    assert setup["risk_status"] == "REJECTED"
    assert setup["outcome_status"] == "REJECTED"
    assert setup["rejection_reasons"] == ["Spread 80.0 bps > max 50 bps"]
