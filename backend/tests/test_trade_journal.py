from services.signal_parser import SignalParser
from services.trade_journal import TradeJournal


def test_trade_journal_hashes_private_identifiers_and_tracks_duplicates(tmp_path):
    journal = TradeJournal(db_path=str(tmp_path / "journal.sqlite3"), hash_salt="test-salt")
    signal = SignalParser().parse(
        message_id="wa-msg-1",
        group_id="private-group",
        sender_id="private-sender",
        text="BUY EURUSDm market SL 1.1600 TP1 1.1660",
    )
    signal.validation_status = "ACCEPTED"

    journal.record_signal(signal)

    assert journal.message_seen("wa-msg-1") is True
    rows = journal.recent_signals()
    assert len(rows) == 1
    row = rows[0]
    assert "group_id" not in row
    assert "sender_id" not in row
    assert "raw_message" not in row
    assert len(row["group_id_hash"]) == 64
    assert len(row["sender_id_hash"]) == 64
    assert len(row["raw_message_hash"]) == 64
    assert row["validation_status"] == "ACCEPTED"


def test_trade_journal_records_alerts(tmp_path):
    journal = TradeJournal(db_path=str(tmp_path / "journal.sqlite3"), hash_salt="test-salt")

    journal.alert("warning", "trade_signal_rejected", "Rejected", {"reason": "stale"})

    alerts = journal.recent_alerts()
    assert len(alerts) == 1
    assert alerts[0]["payload_json"] == {"reason": "stale"}
