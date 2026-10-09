from services.trader_imitation_model import TraderImitationModelService
from services.trader_learning_store import TraderLearningStore


def _signal(symbol, direction, status, index):
    return {
        "signal_id": f"sig-{index}",
        "message_id": f"msg-{index}",
        "instrument": symbol,
        "direction": direction,
        "entry_type": "MARKET",
        "entry_price": None,
        "stop_loss": 1.0,
        "take_profit_1": 1.2 if direction == "BUY" else 0.8,
        "message_timestamp": 1_700_000_000 + index * 60,
        "received_timestamp": 1_700_000_010 + index * 60,
        "parser_confidence": 1.0 if status != "REJECTED" else 0.45,
        "validation_status": status,
    }


def test_trader_imitation_model_trains_and_writes_shadow_predictions(tmp_path):
    store = TraderLearningStore(db_path=str(tmp_path / "learning.sqlite3"))
    for index in range(12):
        status = "ACCEPTED" if index % 3 else "REJECTED"
        signal = _signal("EURUSDm", "BUY" if index % 2 else "SELL", status, index)
        store.record_signal(
            signal_id=signal["signal_id"],
            source="test",
            message_id=signal["message_id"],
            raw_message="stored local signal",
            parsed_signal=signal,
            market_snapshot={"price": 1.1, "spread_bps": 1.2, "rsi": 51},
            validation_status=status,
            rejection_reasons=[] if status != "REJECTED" else ["test reject"],
        )

    service = TraderImitationModelService(
        store=store,
        model_path=tmp_path / "model.json",
        min_examples=5,
    )

    result = service.train()

    assert result["trained"] is True
    assert result["execution_enabled"] is False
    assert result["metrics"]["train_size"] > 0
    assert (tmp_path / "model.json").exists()
    summary = store.summary()
    assert summary["recent_shadow_predictions"]


def test_trader_imitation_model_requires_two_label_classes(tmp_path):
    store = TraderLearningStore(db_path=str(tmp_path / "learning.sqlite3"))
    for index in range(5):
        signal = _signal("EURUSDm", "BUY", "ACCEPTED", index)
        store.record_signal(
            signal_id=signal["signal_id"],
            source="test",
            message_id=signal["message_id"],
            raw_message="stored local signal",
            parsed_signal=signal,
            market_snapshot={"price": 1.1},
            validation_status="ACCEPTED",
            rejection_reasons=[],
        )

    service = TraderImitationModelService(
        store=store,
        model_path=tmp_path / "model.json",
        min_examples=5,
    )

    result = service.train()

    assert result["trained"] is False
    assert result["execution_enabled"] is False
    assert "accepted and rejected" in result["reason"]
