"""Incident characterization using synthetic SQLite stores only."""

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.chat_import_routes import chat_import_router
from services.chat_import_service import ChatImportService
from services.trader_learning_store import TraderLearningStore


CHAT = b"[03/08/2026, 8:30 PM] Fixture: EURUSD BUY ENTRY 1.15 SL 1.14 TP 1.16"


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("preexisting", [False, True])
def test_prefixed_route_pattern_characterized_only_in_temp_storage(tmp_path, monkeypatch, preexisting):
    default = tmp_path / "discarded-default.db"
    monkeypatch.setattr("services.trader_learning_store.DEFAULT_TRADER_LEARNING_PATH", default)
    if preexisting:
        TraderLearningStore(str(default))
        with sqlite3.connect(default) as conn:
            conn.execute("INSERT INTO trader_signals(signal_id,parsed_signal_json) VALUES('fixture-preserved','{}')")
        before = fingerprint(default)
    else:
        assert not default.exists()
    original_connect = sqlite3.connect
    statements = []
    def guarded_connect(path, *args, **kwargs):
        resolved = Path(path).resolve()
        assert resolved.is_relative_to(tmp_path.resolve()), "Test DB escaped its temporary root"
        conn = original_connect(path, *args, **kwargs)
        if resolved == default:
            conn.set_trace_callback(statements.append)
        return conn
    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    # Reproduce the exact old eager-argument mistake, with its default redirected.
    monkeypatch.setattr("services.chat_import_routes.ChatImportService", lambda **kw:
                        ChatImportService(tmp_path / "archive", TraderLearningStore(str(tmp_path / "learning.db"))))
    app = FastAPI()
    app.include_router(chat_import_router(lambda: None))
    with TestClient(app) as client:
        response = client.post("/api/private/chat-imports", files={"file": ("chat.txt", CHAT)})
        assert response.status_code == 200
        imported = response.json()["id"]
        message = client.get(f"/api/private/chat-imports/{imported}/messages").json()["messages"][0]
        assert client.post(f"/api/private/chat-imports/{imported}/messages/{message['id']}/approve").status_code == 200
        assert client.get("/api/private/chat-imports/missing/messages").status_code == 404
        assert client.get(f"/api/private/chat-imports/{imported}/messages?limit=0").status_code == 422
    assert len(statements) == 24  # Six DDL statements for each of four service calls.
    assert all(sql.lstrip().upper().startswith(("CREATE TABLE IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS")) for sql in statements)
    with original_connect(default) as conn:
        assert conn.execute("SELECT count(*) FROM trader_signals").fetchone()[0] == int(preexisting)
        assert conn.execute("SELECT count(*) FROM trader_execution_events").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM trader_shadow_predictions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM sqlite_sequence").fetchone()[0] == 0
    if preexisting:
        assert fingerprint(default) == before
    else:
        assert default.exists() and default.stat().st_size > 0


def test_current_injected_route_concurrent_calls_never_construct_default(tmp_path, monkeypatch):
    original_connect = sqlite3.connect
    observed = []
    def guarded_connect(path, *args, **kwargs):
        resolved = Path(path).resolve()
        assert resolved.is_relative_to(tmp_path.resolve()), "Non-fixture SQLite path"
        observed.append(str(resolved))
        return original_connect(path, *args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    def forbidden():
        raise AssertionError("Default learning store constructed")
    monkeypatch.setattr("services.chat_import_routes.TraderLearningStore", forbidden)
    archive = ChatImportService(tmp_path / "archive", TraderLearningStore(str(tmp_path / "learning.db")))
    app = FastAPI()
    app.include_router(chat_import_router(lambda: None, service_factory=lambda: archive))
    def request(_):
        with TestClient(app) as client:
            uploaded = client.post("/api/private/chat-imports", files={"file": ("chat.txt", CHAT)})
            assert uploaded.status_code == 200
            imported = uploaded.json()["id"]
            row = client.get(f"/api/private/chat-imports/{imported}/messages").json()["messages"][0]
            assert client.post(f"/api/private/chat-imports/{imported}/messages/{row['id']}/approve").status_code == 200
            return imported
    with ThreadPoolExecutor(max_workers=4) as pool:
        imports = list(pool.map(request, range(8)))
    assert len(set(imports)) == 1
    assert len(archive.learning_store.training_examples()) == 1
    assert observed and all(Path(p).is_relative_to(tmp_path) for p in observed)


@pytest.mark.parametrize("failure", ["factory", "sqlite", "missing_record", "bad_upload"])
def test_current_route_failures_never_fall_back_to_default(tmp_path, monkeypatch, failure):
    archive = ChatImportService(tmp_path / "archive")
    default_calls = []
    def forbidden():
        default_calls.append(True)
        raise AssertionError("Default fallback forbidden")
    monkeypatch.setattr("services.chat_import_routes.TraderLearningStore", forbidden)
    def service_factory():
        if failure == "factory":
            raise RuntimeError("Synthetic factory failure")
        return archive
    if failure == "sqlite":
        def denied(*args, **kwargs):
            raise sqlite3.OperationalError("Synthetic database failure")
        monkeypatch.setattr(sqlite3, "connect", denied)
    app = FastAPI()
    app.include_router(chat_import_router(lambda: None, service_factory=service_factory))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = (client.post("/api/private/chat-imports", files={"file": ("chat.txt", b"invalid export")})
                    if failure == "bad_upload" else client.get("/api/private/chat-imports/missing/messages"))
        assert response.status_code == {"factory": 500, "sqlite": 500, "missing_record": 404, "bad_upload": 422}[failure]
    assert default_calls == []
