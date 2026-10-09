import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from services.chat_import_routes import chat_import_router
from services.chat_import_service import ChatImportService, parse_transcript
from services.trader_learning_store import TraderLearningStore


CHAT = """[03/08/2026, 8:30:52 PM] Trader: EUR USD
BUY at current rate: 1.15975
Stoploss: 1.15930
Take profit: 1.16000
[03/08/2026, 8:32:00 PM] Trader: Move stoploss to 1.15980
[03/08/2026, 8:35:00 PM] Trader: TAKE PROFIT HIT
[03/08/2026, 8:36:00 PM] Trader: GOLD BUY
Current rate: 4525
Stoploss: 4243
Take profit: 4266
[03/08/2026, 8:37:00 PM] Trader: GOLD BUY at current rate
Stoploss: 44250
Take profit: 4436
"""


@pytest.fixture
def service(tmp_path):
    return ChatImportService(tmp_path / "chat", TraderLearningStore(str(tmp_path / "learning.sqlite3")))


def archive(text, extras=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("_chat.txt", text)
        for name, content in (extras or {}).items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_historical_import_is_review_only_and_idempotent(service):
    content = archive(CHAT)
    result = service.import_file(content, "chat.zip")
    assert result["messages"] == 5
    assert result["counts"]["signal"] == 3
    assert result["needs_review"] == 2
    assert result["execution_enabled"] is False
    assert service.learning_store.training_examples() == []
    assert service.import_file(content, "chat.zip")["duplicate"]
    assert len(service.list_imports()) == 1
    rows = service.messages(result["id"])["messages"]
    assert rows[1]["kind"] == "update"
    assert rows[1]["candidate_ids"] == [rows[0]["id"]]
    assert rows[2]["kind"] == "reported_result"
    assert rows[2]["outcome_verified"] is False
    for _ in range(2):
        service.approve(result["id"], rows[0]["id"])
    examples = service.learning_store.training_examples()
    assert len(examples) == 1
    assert examples[0]["execution_status"] == "NOT_APPLICABLE"
    assert examples[0]["outcome_status"] == "UNVERIFIED"
    assert examples[0]["market_snapshot"] == {}
    with pytest.raises(ValueError, match="complete"):
        service.approve(result["id"], rows[3]["id"])


def test_timestamp_formats_and_multiline():
    ios = parse_transcript("\u200e[03/08/2026, 8:30:52\u202fPM] Trader: Hi\ncontinued", "DMY", 300)
    android = parse_transcript("8/3/26, 20:30:52 - Trader: Hi\ncontinued", "MDY", 300)
    assert ios[0]["timestamp"] == android[0]["timestamp"]
    assert ios[0]["text"] == "Hi\ncontinued"
    with pytest.raises(ValueError):
        parse_transcript("[31/08/2026, 20:00] A: Hi", "MDY", 300)


def test_result_mentions_direction_without_becoming_new_signal(service):
    result = service.import_file(b"[03/08/2026, 8:30 PM] Trader: SILVER SHORTSELL TRADE booked 443 usd profit", "chat.txt")
    row = service.messages(result["id"])["messages"][0]
    assert row["kind"] == "reported_result"
    assert row["signal"] is None


def test_correction_requires_valid_prices_and_preserves_original(service):
    result = service.import_file(CHAT.encode(), "chat.txt")
    row = service.messages(result["id"])["messages"][3]
    fields = {"entry_price": 4250, "stop_loss": 4243, "take_profit_1": 4266, "note": "Checked original chart entry"}
    with pytest.raises(ValueError):
        service.correct(result["id"], row["id"], {**fields, "entry_price": float("nan")})
    revised = service.correct(result["id"], row["id"], fields)
    assert revised["text"] == row["text"]
    assert revised["review_history"][0]["previous_signal"]["entry_price"] == 4525
    assert revised["review_status"] == "ready"
    assert service.learning_store.training_examples() == []
    service.approve(result["id"], row["id"])
    assert service.learning_store.training_examples()[0]["entry_price"] == 4250


def test_media_retained_and_unsafe_zip_rejected(service):
    result = service.import_file(archive(CHAT + "\n[03/08/2026, 9:00:00 PM] Trader: <attached: chart.jpg>", {"chart.jpg": b"image"}), "chat.zip")
    assert service.media(result["id"], "chart.jpg") == b"image"
    assert service.messages(result["id"], "media")["messages"][0]["available_media"] == ["chart.jpg"]
    with pytest.raises(ValueError, match="Unsafe"):
        service.import_file(archive(CHAT, {"../outside.txt": "bad"}), "chat.zip")
    with pytest.raises(ValueError):
        service.import_file(b"not a zip", "chat.zip")
    with pytest.raises(ValueError):
        service.import_file(b"not a chat", "chat.txt")


def test_overlapping_exports_deduplicate_learning(service):
    first = service.import_file(CHAT.encode(), "a.txt")
    second = service.import_file((CHAT + "\n[03/08/2026, 9:00 PM] Trader: Hello").encode(), "b.txt")
    for result in (first, second):
        row = service.messages(result["id"], "signal")["messages"][0]
        service.approve(result["id"], row["id"])
    assert len(service.learning_store.training_examples()) == 1


def test_concurrent_import_and_approval_preserves_one_example(service):
    with ThreadPoolExecutor(max_workers=4) as pool:
        imports = list(pool.map(lambda _: service.import_file(CHAT.encode(), "chat.txt"), range(8)))
    assert len(service.list_imports()) == 1
    import_id = imports[0]["id"]
    message_id = service.messages(import_id)["messages"][0]["id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: service.approve(import_id, message_id), range(8)))
    assert len(service.learning_store.training_examples()) == 1


def test_overlapping_archive_cannot_overwrite_reviewed_prices(service):
    first = service.import_file(CHAT.encode(), "a.txt")
    second = service.import_file((CHAT + "\n[03/08/2026, 9:00 PM] Trader: Hi").encode(), "b.txt")
    row = service.messages(first["id"])["messages"][0]
    service.correct(first["id"], row["id"], {"entry_price": 1.1598, "stop_loss": 1.1593, "take_profit_1": 1.16, "note": "Verified chart price"})
    service.approve(first["id"], row["id"])
    service.approve(second["id"], row["id"])
    assert service.learning_store.training_examples()[0]["entry_price"] == 1.1598
    assert service.messages(second["id"])["messages"][0]["signal"]["entry_price"] == 1.1598


@pytest.mark.parametrize("extras", [{"second.txt": "hi"}, {"nested/chart.jpg": b"1", "chart.jpg": b"2"}, {"C:/chart.jpg": b"1"}])
def test_ambiguous_and_unsafe_archives_rejected(service, extras):
    with pytest.raises(ValueError):
        service.import_file(archive(CHAT, extras), "chat.zip")
    assert service.list_imports() == []


def test_large_archive_pagination_and_candidate_bounds(service):
    start = datetime(2026, 8, 3, 12)
    lines = []
    for index in range(2000):
        timestamp = (start + timedelta(seconds=index)).strftime("%d/%m/%Y, %H:%M:%S")
        body = "EURUSD BUY Current rate: 1.15 SL 1.14 TP 1.16" if index % 2 == 0 else "TAKE PROFIT HIT"
        lines.append(f"[{timestamp}] Trader: {body}")
    result = service.import_file("\n".join(lines).encode(), "large.txt")
    assert result["messages"] == 2000
    page = service.messages(result["id"], offset=1950, limit=50)
    assert len(page["messages"]) == 50
    assert max(len(row["candidate_ids"]) for row in page["messages"]) <= 20
    assert service.learning_store.training_examples() == []


def test_routes_import_review_and_access(monkeypatch, tmp_path):
    archive = ChatImportService(tmp_path / "chat", TraderLearningStore(str(tmp_path / "learning.db")))
    def forbidden_default_store():
        raise AssertionError("Route fixture must never construct the operator learning store")
    monkeypatch.setattr("services.chat_import_routes.TraderLearningStore", forbidden_default_store)
    app = FastAPI()
    app.include_router(chat_import_router(lambda: None, service_factory=lambda: archive))
    with TestClient(app) as client:
        response = client.post("/api/private/chat-imports", files={"file": ("chat.txt", CHAT.encode(), "text/plain")})
        assert response.status_code == 200
        import_id = response.json()["id"]
        result = client.get(f"/api/private/chat-imports/{import_id}/messages?kind=signal&limit=1").json()
        assert result["total"] == 3
        assert len(result["messages"]) == 1
        message_id = result["messages"][0]["id"]
        assert client.post(f"/api/private/chat-imports/{import_id}/messages/{message_id}/approve").json()["execution_enabled"] is False
        assert client.get("/api/private/chat-imports/missing/messages").status_code == 404
        assert client.get(f"/api/private/chat-imports/{import_id}/messages?limit=0").status_code == 422
    def denied():
        raise HTTPException(403)
    protected = FastAPI()
    protected.include_router(chat_import_router(denied))
    with TestClient(protected) as client:
        assert client.get("/api/private/chat-imports").status_code == 403
