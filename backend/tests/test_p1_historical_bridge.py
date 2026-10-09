import hashlib
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.rebuild.application import create_app
from core.rebuild.ledger import DemoAccount, IntentRequest, Ledger, canonical, hashed, now
from core.rebuild.lifecycle_contracts import ExecutionRequest, SafetyDecision, SourceEvent, TradeIntent
from core.rebuild.lifecycle_service import LifecycleService
from core.rebuild.migration_runner import migrate
from services.chat_import_service import ChatImportService
from services.historical_canonical_bridge import HistoricalCanonicalBridge
from services.signal_parser import PARSER_VERSION
from services.trader_learning_store import TraderLearningStore


CHAT = "[03/08/2026, 8:30:52 PM] Trader: EUR USD\nBUY Current price: 1.15975\nStoploss: 1.15930\nTake profit: 1.16000\n"
ACCOUNT = DemoAccount(account_id="m2-fixture", server="fixture", currency="USD", evidence_source="FIXTURE")


def packed(text=CHAT, year=2024, compression=0):
    buffer = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(buffer, "w", compression=compression) as zf:
        info = zipfile.ZipInfo("_chat.txt", (year, 1, 1, 0, 0, 0))
        info.compress_type = compression
        zf.writestr(info, text)
    return buffer.getvalue()


@pytest.fixture
def bridge(tmp_path):
    archive = ChatImportService(tmp_path / "archive", TraderLearningStore(str(tmp_path / "learning.db")))
    return HistoricalCanonicalBridge(archive, LifecycleService(Ledger(tmp_path / "core.db", account=ACCOUNT), fixture_mode=True))


def imported(bridge, content=None, **profile):
    meta = bridge.archive.import_file(content or packed(), "chat.zip", **({"date_order": "DMY", "utc_offset": 300} | profile))
    return meta, bridge.archive.messages(meta["id"])["messages"]


def counts(bridge):
    with bridge.ledger.connect() as conn:
        return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in
                ("source_events", "signals", "historical_links", "order_intents", "risk_decisions", "execution_requests", "broker_orders", "positions")}


def intent(signal, legacy=False):
    values = dict(client_order_id="historical-client", action="OPEN", signal_id=signal["signal_id"], symbol=signal["symbol"],
                  direction=signal["direction"], volume=.01, entry=signal["entry"], stop_loss=signal["stop_loss"],
                  take_profit=signal["take_profit"][0])
    return IntentRequest(**values) if legacy else TradeIntent(**values, entry_type=signal["entry_type"], take_profit_targets=signal["take_profit"])


def test_exact_zip_and_repack_preserve_archives_and_share_canonical_lineage(bridge):
    a, b = packed(), packed(year=2025, compression=8)
    assert a != b
    first, rows = imported(bridge, a)
    assert imported(bridge, a)[0]["duplicate"] is True
    second, replay = imported(bridge, b)
    assert first["archive_hash"] == hashlib.sha256(a).hexdigest()
    assert second["archive_hash"] == hashlib.sha256(b).hexdigest()
    assert first["transcript_fingerprint"] == second["transcript_fingerprint"]
    assert second["duplicate_of"] == first["id"]
    assert first["id"] != second["id"]
    links = [bridge.promote(m["id"], r[0]["id"]) for m, r in ((first, rows), (second, replay))]
    assert all(link["status"] == "VALIDATED" for link in links)
    assert links[0]["source_event_id"] == links[1]["source_event_id"]
    assert links[0]["signal_id"] == links[1]["signal_id"]
    with bridge.archive.connect() as conn:
        assert {bytes(r[0]) for r in conn.execute("SELECT archive FROM imports")} == {a, b}
    trace = bridge.lifecycle.trace(links[0]["source_event_id"])
    assert len(trace["historical_links"]) == 2
    assert trace["lifecycles"] == []
    assert counts(bridge) == dict(source_events=1, signals=1, historical_links=2, order_intents=0,
                                  risk_decisions=0, execution_requests=0, broker_orders=0, positions=0)


def test_different_transcripts_and_distinct_same_symbol_messages(bridge):
    one, _ = imported(bridge)
    two, rows = imported(bridge, packed(CHAT + CHAT.replace("8:30:52", "8:32:52")))
    assert one["transcript_fingerprint"] != two["transcript_fingerprint"]
    assert two["duplicate_of"] is None
    assert len({r["historical_message_id"] for r in rows}) == 2
    for row in rows:
        assert bridge.promote(two["id"], row["id"])["status"] == "VALIDATED"
    assert counts(bridge)["signals"] == 2


def test_identical_occurrences_are_not_dropped(bridge):
    meta, rows = imported(bridge, packed(CHAT + CHAT))
    assert meta["duplicates_removed"] == 0
    assert [row["occurrence"] for row in rows] == [0, 1]
    assert len({r["id"] for r in rows}) == 2
    for row in rows:
        bridge.promote(meta["id"], row["id"])
    assert counts(bridge)["signals"] == 2


def test_exact_whitespace_differences_are_not_fuzzy_merged(bridge):
    meta, rows = imported(bridge, packed(CHAT + CHAT.replace("Trader: EUR", "Trader:  EUR")))
    assert len(rows) == 2
    assert rows[0]["id"] != rows[1]["id"]
    for row in rows:
        assert bridge.promote(meta["id"], row["id"])["status"] == "VALIDATED"
    assert counts(bridge)["signals"] == 2


def test_bom_and_line_endings_normalize_only_transcript_container(bridge):
    first, rows = imported(bridge)
    initial = bridge.promote(first["id"], rows[0]["id"])
    content = ("\ufeff" + CHAT.replace("\n", "\r\n")).encode()
    second = bridge.archive.import_file(content, "chat.txt", "DMY", 300)
    assert second["duplicate_of"] == first["id"]
    assert second["transcript_fingerprint"] == first["transcript_fingerprint"]
    row = bridge.archive.messages(second["id"])["messages"][0]
    assert bridge.promote(second["id"], row["id"])["signal_id"] == initial["signal_id"]


def test_raw_evidence_and_explicit_time_and_parser_provenance(bridge):
    text = "\u200e" + CHAT.replace(" PM", "\u202fPM")
    content = ("\ufeff" + text.replace("\n", "\r\n")).encode()
    meta = bridge.archive.import_file(content, "chat.txt", "DMY", 300)
    row = bridge.archive.messages(meta["id"])["messages"][0]
    link = bridge.promote(meta["id"], row["id"])
    assert link["status"] == "VALIDATED"
    assert row["raw_record"] == text.rstrip("\n")
    assert row["identity_content"][-1] == row["raw_body"]
    source = json.loads(bridge.lifecycle.trace(link["source_event_id"])["source_event"]["payload"])
    assert source["raw_text"] == row["raw_body"]
    assert source["original_timestamp"] == "03/08/2026, 8:30:52\u202fPM"
    assert source["source_time_utc"] == "2026-08-03T15:30:52Z"
    assert "DMY" in source["timezone_evidence"]
    assert source["metadata"]["parser_version"] == PARSER_VERSION
    signal = json.loads(bridge.lifecycle.trace(link["source_event_id"])["signals"][0]["payload"])
    assert signal["signal_id"] == hashed([source["source_event_id"], "signal.v2", PARSER_VERSION])
    assert signal["raw_source_hash"] == hashlib.sha256(row["raw_body"].encode()).hexdigest()
    assert signal["source_type"] == "HISTORICAL_WHATSAPP"
    assert (signal["entry"], signal["stop_loss"], signal["take_profit"]) == (1.15975, 1.1593, [1.16])
    with bridge.archive.connect() as conn:
        assert conn.execute("SELECT archive FROM imports").fetchone()[0] == content
    with pytest.raises(KeyError):
        bridge.archive.media(meta["id"], "missing.jpg")


@pytest.mark.parametrize("profile", [{}, {"date_order": "DMY"}, {"utc_offset": 300}])
def test_unconfirmed_timestamp_stays_untrusted(bridge, profile):
    meta = bridge.archive.import_file(packed(), "chat.zip", **profile)
    row = bridge.archive.messages(meta["id"])["messages"][0]
    link = bridge.promote(meta["id"], row["id"])
    assert link["status"] == "REVIEW_REQUIRED"
    assert link["signal_id"] is None
    source = json.loads(bridge.lifecycle.trace(link["source_event_id"])["source_event"]["payload"])
    assert source["source_time_utc"] is None and source["timezone_evidence"] is None
    with pytest.raises(ValueError, match="Unresolved timestamp"):
        bridge.lifecycle.validate_source(link["source_event_id"])


def test_conflicting_time_profile_does_not_clone_or_overwrite_source(bridge):
    meta, rows = imported(bridge)
    original = bridge.promote(meta["id"], rows[0]["id"])
    different, rows = imported(bridge, utc_offset=0)
    conflict = bridge.promote(different["id"], rows[0]["id"])
    assert conflict["status"] == "REVIEW_REQUIRED" and "conflict" in conflict["reason"]
    assert conflict["candidate_source_event_id"] == original["source_event_id"]
    assert counts(bridge)["source_events"] == counts(bridge)["signals"] == 1


@pytest.mark.parametrize("body", ["EURUSD BUY SL 1.14 TP 1.16", "EURUSD BUY ENTRY 1.15 SL 1.17 TP 1.16",
                                  "EURUSD BUY ENTRY 1.15 SL 1.14 TP 1.16 TP2 1.13"])
def test_invalid_material_remains_reviewable_without_fabrication(bridge, body):
    meta, rows = imported(bridge, packed("[03/08/2026, 8:30 PM] Trader: " + body))
    link = bridge.promote(meta["id"], rows[0]["id"])
    assert link["status"] == "REVIEW_REQUIRED" and link["signal_id"] is None
    assert bridge.archive.messages(meta["id"])["messages"][0]["text"] == body
    assert counts(bridge)["signals"] == 0


def test_historical_approval_is_only_review_acceptance(bridge):
    meta, rows = imported(bridge)
    bridge.archive.approve(meta["id"], rows[0]["id"])
    link = bridge.promote(meta["id"], rows[0]["id"])
    assert link["status"] == "VALIDATED"
    assert json.loads(link["review_snapshot"])["review_status"] == "approved"
    assert link["review_semantics"] == "HISTORICAL_ACCEPTANCE_ONLY"
    assert counts(bridge)["risk_decisions"] == 0
    example = bridge.archive.learning_store.training_examples()[0]
    assert example["execution_status"] == "NOT_APPLICABLE" and example["outcome_status"] == "UNVERIFIED"


def test_correction_is_not_misrepresented_as_parser_output(bridge):
    meta, rows = imported(bridge)
    bridge.archive.correct(meta["id"], rows[0]["id"], dict(entry_price=1.1598, stop_loss=1.1593, take_profit_1=1.16, note="Fixture reviewed chart"))
    link = bridge.promote(meta["id"], rows[0]["id"])
    assert link["status"] == "REVIEW_REQUIRED" and link["signal_id"] is None
    assert json.loads(link["review_snapshot"])["review_history"]


def test_later_review_change_preserves_prior_canonical_evidence(bridge):
    meta, rows = imported(bridge)
    first = bridge.promote(meta["id"], rows[0]["id"])
    bridge.archive.correct(meta["id"], rows[0]["id"], dict(entry_price=1.1598, stop_loss=1.1593, take_profit_1=1.16, note="Fixture price correction"))
    latest = bridge.promote(meta["id"], rows[0]["id"])
    assert latest["status"] == "REVIEW_REQUIRED"
    assert latest["signal_id"] == first["signal_id"]
    assert json.loads(bridge.lifecycle.trace(first["source_event_id"])["signals"][0]["payload"])["entry"] == 1.15975
    with bridge.ledger.connect() as conn:
        snapshots = [json.loads(r[0])["review_snapshot"] for r in conn.execute("SELECT payload FROM audit_events WHERE event_type='HISTORICAL_PROMOTION_CHECKPOINT'")]
    assert any(row["review_history"] for row in snapshots)
    assert any(not row["review_history"] for row in snapshots)


def test_source_transaction_rollback_does_not_claim_link(bridge, monkeypatch):
    meta, rows = imported(bridge)
    original = bridge.ledger.audit
    def fail(conn, event_type, intent_id, payload):
        if event_type == "SOURCE_EVENT_RECORDED":
            raise RuntimeError("synthetic audit failure inside source transaction")
        return original(conn, event_type, intent_id, payload)
    monkeypatch.setattr(bridge.ledger, "audit", fail)
    with pytest.raises(RuntimeError):
        bridge.promote(meta["id"], rows[0]["id"])
    assert counts(bridge)["source_events"] == 0
    assert bridge.get(meta["id"], rows[0]["id"])["source_event_id"] is None
    monkeypatch.setattr(bridge.ledger, "audit", original)
    assert bridge.promote(meta["id"], rows[0]["id"])["status"] == "VALIDATED"


def test_historical_link_sql_preserves_identity_and_foreign_keys(bridge):
    meta, rows = imported(bridge)
    link = bridge.promote(meta["id"], rows[0]["id"])
    for statement in ("UPDATE historical_links SET source_event_id=NULL", "UPDATE historical_links SET signal_id=NULL",
                      "UPDATE historical_links SET archive_hash='changed'", "DELETE FROM historical_links"):
        with bridge.ledger.transaction() as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement)
    assert bridge.get(meta["id"], rows[0]["id"]) == link
    with bridge.ledger.connect() as conn:
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_non_signal_or_missing_message_cannot_create_link(bridge):
    meta, rows = imported(bridge, packed("[03/08/2026, 8:30 PM] Trader: Hello"))
    with pytest.raises(ValueError, match="signal candidates"):
        bridge.promote(meta["id"], rows[0]["id"])
    with pytest.raises(KeyError):
        bridge.promote(meta["id"], "missing")
    assert counts(bridge)["historical_links"] == 0


@pytest.mark.parametrize("stage", ["source", "validation", "final_checkpoint"])
def test_partial_failure_retry_and_restart(bridge, monkeypatch, stage):
    meta, rows = imported(bridge)
    target, method = (bridge.lifecycle, "save_source") if stage == "source" else (
        (bridge.lifecycle, "validate_source") if stage == "validation" else (bridge, "_checkpoint"))
    original = getattr(target, method)
    def fail(*args):
        if stage != "final_checkpoint" or args[2] == "VALIDATED":
            raise RuntimeError("synthetic interrupted write")
        return original(*args)
    monkeypatch.setattr(target, method, fail)
    with pytest.raises(RuntimeError):
        bridge.promote(meta["id"], rows[0]["id"])
    state = bridge.get(meta["id"], rows[0]["id"])
    assert state["status"] == ("PENDING" if stage == "source" else "SOURCE_ONLY")
    assert state["signal_id"] is None
    monkeypatch.setattr(target, method, original)
    restarted = HistoricalCanonicalBridge(bridge.archive, LifecycleService(Ledger(bridge.ledger.path, account=ACCOUNT), fixture_mode=True))
    link = restarted.promote(meta["id"], rows[0]["id"])
    assert link["status"] == "VALIDATED"
    assert restarted.promote(meta["id"], rows[0]["id"]) == link
    assert counts(bridge)["source_events"] == counts(bridge)["signals"] == 1


def test_concurrent_import_promotion(bridge):
    containers = [packed(year=2024 + i % 2) for i in range(12)]
    def run(content):
        meta, rows = imported(bridge, content)
        return bridge.promote(meta["id"], rows[0]["id"])
    with ThreadPoolExecutor(max_workers=6) as pool:
        links = list(pool.map(run, containers))
    assert all(link["status"] == "VALIDATED" for link in links)
    assert len({link["source_event_id"] for link in links}) == 1
    assert counts(bridge)["signals"] == 1 and counts(bridge)["historical_links"] == 2
    imports = bridge.archive.list_imports()
    assert sum(item["duplicate_of"] is not None for item in imports) == 1


@pytest.mark.parametrize("source_type", ["HISTORICAL_WHATSAPP", "SCREENSHOT"])
@pytest.mark.parametrize("legacy_wrapper", [False, True])
def test_direct_execution_firewall_including_fixture_and_legacy_wrapper(bridge, source_type, legacy_wrapper):
    event = SourceEvent(source_event_id="source-fixture", source_type=source_type, source_id="fixture", source_message_id="message-one",
                        raw_text="EURUSD BUY ENTRY 1.15 SL 1.14 TP 1.16", original_timestamp="2026-01-01 UTC",
                        source_time_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), received_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    bridge.lifecycle.save_source(event)
    signal = bridge.lifecycle.validate_source(event.source_event_id)
    request = intent(signal, legacy_wrapper)
    with pytest.raises(ValueError, match="Historical sources"):
        (bridge.ledger if legacy_wrapper else bridge.lifecycle).create_intent(request)
    with bridge.ledger.transaction() as conn, pytest.raises(sqlite3.IntegrityError, match="Historical sources"):
        conn.execute("INSERT INTO order_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (hashed("raw-bypass"), signal["signal_id"], request.client_order_id, hashed(request.model_dump()), canonical(request.model_dump()),
                      "OPEN", "EURUSD", None, "CREATED", now(), .01, 1.15, 1.14, 1.16))
    with pytest.raises(ValueError):
        bridge.lifecycle.create_execution_request(ExecutionRequest(execution_request_id="missing-request", intent_id=hashed("raw-bypass"), safety_decision_id="missing-decision"))
    assert counts(bridge)["order_intents"] == counts(bridge)["risk_decisions"] == counts(bridge)["execution_requests"] == 0


def test_authenticated_historical_route_isolated_from_operator_storage(tmp_path):
    archive = ChatImportService(tmp_path / "archive")
    app = create_app(database_path=tmp_path / "core.db", token="synthetic-m2-token", historical_service_factory=lambda: archive)
    headers = {"X-Control-Token": "synthetic-m2-token"}
    with TestClient(app) as client:
        assert client.post("/api/private/chat-imports", files={"file": ("chat.zip", packed())}).status_code == 403
        response = client.post("/api/private/chat-imports", headers=headers, files={"file": ("chat.zip", packed())}, data={"date_order": "DMY", "utc_offset": "300"})
        assert response.status_code == 200
        meta = response.json()
        row = archive.messages(meta["id"])["messages"][0]
        path = f"/api/private/chat-imports/{meta['id']}/messages/{row['id']}/canonical"
        assert client.get(path, headers=headers).status_code == 404
        response = client.post(path, headers=headers)
        assert response.status_code == 200 and response.json()["status"] == "VALIDATED"
        assert client.get(path, headers=headers).json() == response.json()
        assert client.post(f"/api/private/chat-imports/{meta['id']}/train", headers=headers).status_code == 423
        assert client.post("/api/private/chat-imports/missing/messages/missing/canonical", headers=headers).status_code == 404
        assert client.get("/api/core/status", headers=headers).json()["execution_enabled"] is False


def test_legacy_import_not_silently_assigned_new_evidence(bridge):
    meta, rows = imported(bridge)
    with bridge.archive.connect() as conn:
        old = dict(meta)
        old.pop("archive_hash")
        conn.execute("UPDATE imports SET metadata=? WHERE id=?", (json.dumps(old), meta["id"]))
    result = bridge.promote(meta["id"], rows[0]["id"])
    assert result["status"] == "REVIEW_REQUIRED" and result["source_event_id"] is None


def test_canonical_route_never_constructs_learning_store(tmp_path, monkeypatch):
    archive = ChatImportService(tmp_path / "archive")
    meta = archive.import_file(packed(), "chat.zip", "DMY", 300)
    message = archive.messages(meta["id"])["messages"][0]
    monkeypatch.setattr("services.chat_import_routes.ChatImportService", lambda: archive)
    def forbidden():
        raise AssertionError("Canonical projection must not open learning storage")
    monkeypatch.setattr("services.chat_import_routes.TraderLearningStore", forbidden)
    app = create_app(database_path=tmp_path / "core.db", token="synthetic-m2-token")
    with TestClient(app) as client:
        path = f"/api/private/chat-imports/{meta['id']}/messages/{message['id']}/canonical"
        headers = {"X-Control-Token": "synthetic-m2-token"}
        assert client.post(path, headers=headers).json()["status"] == "VALIDATED"
        assert client.get(path, headers=headers).json()["status"] == "VALIDATED"


@pytest.mark.parametrize("source_type", ["HISTORICAL_WHATSAPP", "SCREENSHOT"])
def test_pre004_preservation_and_preexisting_historical_intent_firewall(tmp_path, bridge, source_type):
    event = SourceEvent(source_event_id="old-event-0001", source_type=source_type, source_id="fixture", source_message_id="old-message",
                        raw_text="EURUSD BUY ENTRY 1.15 SL 1.14 TP 1.16", original_timestamp="2026-01-01 UTC",
                        source_time_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), received_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    bridge.lifecycle.save_source(event)
    signal = bridge.lifecycle.validate_source(event.source_event_id)
    request = intent(signal)
    path = tmp_path / "pre004.db"
    migrations = Path(__file__).parents[1] / "core/rebuild/migrations"
    with sqlite3.connect(path) as conn, bridge.ledger.connect() as origin:
        for n in (1, 2, 3):
            conn.executescript(next(migrations.glob(f"00{n}_*.sql")).read_text())
        for table in ("account_binding", "source_events", "signals"):
            for row in origin.execute(f"SELECT * FROM {table}"):
                conn.execute(f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})", tuple(row))
        values = (hashed("pre004-intent"), signal["signal_id"], request.client_order_id, hashed(request.model_dump()), canonical(request.model_dump()),
                  "OPEN", "EURUSD", None, "CREATED", now(), .01, 1.15, 1.14, 1.16)
        conn.execute("INSERT INTO order_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        conn.commit()
        before = {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in
                  ("source_events", "signals", "order_intents", "halt_state", "account_binding")}
        migrate(conn)
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 9
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        for table, rows in before.items():
            assert conn.execute(f"SELECT * FROM {table}").fetchall() == rows
        for n in (1, 2, 3, 4):
            script = next(migrations.glob(f"00{n}_*.sql")).read_text()
            assert conn.execute("SELECT sha256 FROM migration_checksums WHERE version=?", (n,)).fetchone()[0] == hashlib.sha256(script.encode()).hexdigest()
    service = LifecycleService(Ledger(path, account=ACCOUNT), fixture_mode=True)
    approval = SafetyDecision(safety_decision_id="old-approval", intent_id=values[0], decision="APPROVED", reason_codes=("FIXTURE",),
                              explanation="Synthetic only", policy_id="p1-fixture", policy_version="1", decision_timestamp=datetime.now(timezone.utc),
                              evidence_scope="FIXTURE", risk_budget=0., approved_volume=.01)
    with pytest.raises(ValueError, match="Historical sources"):
        service.create_intent(request)
    with pytest.raises(ValueError, match="Historical sources"):
        service.record_decision(approval)
    with pytest.raises(ValueError, match="Historical sources"):
        service.create_execution_request(ExecutionRequest(execution_request_id="old-request", intent_id=values[0], safety_decision_id=approval.safety_decision_id))
    statements = [
        ("INSERT INTO risk_decisions(risk_decision_id,intent_id,decision,reason_codes,risk_budget,approved_volume,state_version,timestamp) VALUES(?,?,'APPROVED','[]',0,.01,0,?)", ("sql-approval", values[0], now())),
        ("INSERT INTO broker_orders VALUES(?,?,?,0,.01,0,'PLACED',1)", ("sql-order", values[0], request.client_order_id)),
        ("INSERT INTO positions VALUES(?,?,'EURUSD','BUY',.01,'OPEN')", ("sql-position", values[0])),
    ]
    for sql, args in statements:
        with service.ledger.transaction() as conn, pytest.raises(sqlite3.IntegrityError, match="Historical sources"):
            conn.execute(sql, args)
