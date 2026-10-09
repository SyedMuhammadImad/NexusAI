from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.rebuild.application import create_app
from core.rebuild.contracts import parse_source
from core.rebuild.ledger import BrokerDeal, BrokerOrder, DemoAccount, IntentRequest, Ledger as CoreLedger

ACCOUNT = DemoAccount(account_id="fixture-account", server="fixture-server", currency="USD", evidence_source="FIXTURE")


def Ledger(path):
    return CoreLedger(path, account=ACCOUNT)


def source(text="EURUSD BUY ENTRY 100 SL 90 TP 120", **kwargs):
    message_id = kwargs.pop("source_message_id", "message")
    return parse_source(text=text, source_type="SCREENSHOT", source_id="group", source_message_id=message_id,
                        source_timestamp=1000., received_timestamp=1001., parsed_timestamp=1002., **kwargs)


@pytest.mark.parametrize("tp,value", [("TP 120",120.),("TP 2400",2400.),("TP1 2400",2400.),
                                      ("TP1:2400",2400.),("TAKE PROFIT 120",120.),("TP 120.25",120.25)])
def test_tp_tokenization(tp, value):
    assert source(f"EURUSD BUY ENTRY 100 SL 90 {tp}").take_profit == (value,)


def test_multiple_targets_and_determinism():
    text = "EURUSD BUY ENTRY 100 SL 90 TP1 120 TP2:130 TP3=140"
    assert source(text) == source(text)
    assert source(text).take_profit == (120., 130., 140.)


@pytest.mark.parametrize("text", ["EURUSD BUY ENTRY NaN SL 90 TP 120", "EURUSD BUY ENTRY inf SL 90 TP 120",
    "EURUSD BUY ENTRY -100 SL 90 TP 120", "EURUSD BUY ENTRY 0 SL 90 TP 120",
    "EURUSD BUY ENTRY 100 SL 110 TP 120", "EURUSD BUY ENTRY 100 SL 90 TP -120",
    "EURUSD BUY SELL ENTRY 100 SL 90 TP 120", "UNKNOWN BUY ENTRY 100 SL 90 TP 120",
    "EURUSD BUY ENTRY 100 SL 90", "EURUSD BUY ENTRY 100 SL 90 TP 120 TP 130",
    "EURUSD BUY ENTRY 1e3 SL 90 TP 120", "EURUSD BUY ENTRY 1,000 SL 90 TP 120"])
def test_reject_unsafe_source(text):
    with pytest.raises(ValueError):
        source(text)


def test_contract_is_frozen_and_time_cannot_rejuvenate():
    signal = source()
    with pytest.raises(ValidationError):
        signal.entry = 500.
    with pytest.raises(ValidationError):
        type(signal)(**{**signal.model_dump(), "source_timestamp": 1100.})
    with pytest.raises(ValidationError):
        type(signal)(**{**signal.model_dump(), "entry": float("nan")})


def request(signal, key="request-one"):
    return IntentRequest(client_order_id=key, signal_id=signal.signal_id, action="OPEN", symbol=signal.symbol,
                         direction="BUY", volume=.01, entry=100., stop_loss=90., take_profit=120.)


def test_durable_replay_concurrent_and_restart(tmp_path):
    ledger = Ledger(tmp_path / "core.db")
    signal = source()
    ledger.save_signal(signal)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: ledger.create_intent(request(signal)), range(10)))
    assert len({r["intent_id"] for r in results}) == 1
    restarted = Ledger(ledger.path)
    assert restarted.create_intent(request(signal))["intent_id"] == results[0]["intent_id"]
    assert restarted.status()["counts"]["order_intents"] == 1
    with pytest.raises(ValueError, match="different request"):
        restarted.create_intent(request(signal).model_copy(update={"volume": .02}))


def test_halt_survives_restart_and_schema_is_idempotent(tmp_path):
    ledger = Ledger(tmp_path / "core.db")
    assert ledger.status()["halt"]["state"] == "RECOVERY_REQUIRED"
    ledger.halt("operator")
    assert Ledger(ledger.path).status()["halt"]["state"] == "HALTED"


def test_signal_conflicts_and_missing_source_rejected(tmp_path):
    ledger = Ledger(tmp_path / "core.db")
    signal = source()
    with pytest.raises(ValueError, match="Persist signal"):
        ledger.create_intent(request(signal))
    ledger.save_signal(signal)
    ledger.save_signal(signal)
    with pytest.raises(ValueError, match="Immutable signal"):
        ledger.save_signal(source("EURUSD BUY ENTRY 100 SL 90 TP 130"))


def test_rebuild_http_has_no_execution_or_training_routes(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "core.db", token="local-test")) as client:
        assert client.get("/api/core/status").status_code == 403
        client.headers["X-Control-Token"] = "local-test"
        status = client.get("/api/core/status").json()
        assert status["halt"]["state"] == "HALTED"
        assert status["agents_running"] == 0
        assert status["execution_enabled"] is False
        for path in ("/api/backtest", "/api/controls/reset-kill-switch", "/api/controls/inject-test-signals",
                     "/api/private/signals/image/submit", "/api/broker/exness/positions/levels",
                     "/api/private/trader-learning/train", "/api/private/chat-imports/id/train"):
            assert client.post(path).status_code == 423
        assert client.get("/api/portfolio").status_code == 404
        assert client.post("/api/controls/kill-switch").json()["halt"]["state"] == "HALTED"


def test_empty_token_never_unlocks_development(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "core.db", token="")) as client:
        assert client.get("/api/core/status").status_code == 403


def order(key, broker_id, volume=.01):
    return BrokerOrder(account_key=ACCOUNT.key, client_order_id=key, broker_order_id=broker_id, retcode=10009,
                       requested_volume=volume, filled_volume=volume, status="FILLED", timestamp=1003.)


def deal(deal_id, order_id, position_id, kind="IN", volume=.01):
    return BrokerDeal(account_key=ACCOUNT.key, broker_deal_id=deal_id, broker_order_id=order_id, broker_position_id=position_id,
                      deal_type=kind, volume=volume, price=100., profit=0., commission=-.1, swap=0., fee=0., timestamp=1004.)


def test_two_gold_positions_opposite_directions_have_exact_lineage(tmp_path):
    ledger = Ledger(tmp_path / "core.db")
    buy = source("GOLD BUY ENTRY 100 SL 90 TP 120", source_message_id="buy")
    sell = source("GOLD SELL ENTRY 100 SL 110 TP 80", source_message_id="sell")
    for signal, key, broker_id, position_id in ((buy,"request-buy","o1","p1"), (sell,"request-sell","o2","p2")):
        ledger.save_signal(signal)
        req = IntentRequest(client_order_id=key, signal_id=signal.signal_id, action="OPEN", symbol=signal.symbol,
                            direction=signal.direction, volume=.01, entry=signal.entry,
                            stop_loss=signal.stop_loss, take_profit=signal.take_profit[0])
        ledger.create_intent(req)
        ledger.record_order(order(key,broker_id))
        for _ in range(10):
            ledger.record_deal(deal("d"+broker_id, broker_id, position_id))
    lines = Ledger(ledger.path).deal_lineage()
    assert [(r["broker_position_id"],r["signal_id"]) for r in lines] == [("p1",buy.signal_id),("p2",sell.signal_id)]
    assert ledger.status()["counts"]["broker_deals"] == 2
    assert ledger.status()["counts"]["trade_outcomes"] == 0


def test_out_of_order_deal_quarantine_then_exact_replay(tmp_path):
    ledger = Ledger(tmp_path / "core.db")
    evidence = deal("d1","o1","p1")
    assert ledger.record_deal(evidence) == "QUARANTINED"
    assert ledger.record_deal(evidence) == "QUARANTINED"
    signal = source()
    ledger.save_signal(signal)
    ledger.create_intent(request(signal))
    ledger.record_order(order("request-one","o1"))
    assert ledger.record_deal(evidence) == "RECORDED"
    assert ledger.status()["counts"]["quarantine"] == 0
    with pytest.raises(ValueError, match="Immutable broker deal"):
        ledger.record_deal(evidence.model_copy(update={"price": 101.}))


def test_partial_order_cannot_regress_or_reopen(tmp_path):
    ledger = Ledger(tmp_path / "core.db")
    signal = source()
    ledger.save_signal(signal)
    ledger.create_intent(request(signal))
    full = order("request-one", "o1")
    partial = full.model_copy(update={"filled_volume": .005, "status": "PARTIALLY_FILLED", "timestamp":1002.})
    ledger.record_order(partial)
    ledger.record_order(full)
    assert ledger.record_order(partial)["status"] == "FILLED"
    with pytest.raises(ValueError):
        ledger.record_order(partial.model_copy(update={"timestamp":1005.}))
    with pytest.raises(ValueError, match="identity conflict"):
        ledger.record_order(full.model_copy(update={"broker_order_id":"duplicate-order"}))


def test_new_client_key_cannot_duplicate_logical_request(tmp_path):
    ledger = Ledger(tmp_path / "core.db")
    signal = source()
    ledger.save_signal(signal)
    ledger.create_intent(request(signal))
    with pytest.raises(ValueError, match="already has a client key"):
        ledger.create_intent(request(signal, "different-client"))


def test_partial_close_deals_join_explicit_position_only(tmp_path):
    ledger = Ledger(tmp_path / "core.db")
    opened = source()
    ledger.save_signal(opened)
    ledger.create_intent(request(opened))
    ledger.record_order(order("request-one","o1"))
    ledger.record_deal(deal("d1","o1","p1"))
    closed = source(source_message_id="close")
    ledger.save_signal(closed)
    close_req = request(closed,"request-close").model_copy(update={"action":"PARTIAL_CLOSE","volume":.005,"target_position_id":"p1"})
    ledger.create_intent(close_req)
    ledger.record_order(order("request-close","o2",.005))
    with pytest.raises(ValueError, match="exact owned position"):
        ledger.record_deal(deal("d2","o2","p2","OUT",.005))
    ledger.record_deal(deal("d2","o2","p1","OUT",.005))
    assert ledger.deal_lineage()[-1]["target_position_id"] == "p1"
    assert ledger.status()["counts"]["trade_outcomes"] == 0
