import hashlib
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.rebuild.application import create_app
from core.rebuild.ledger import DemoAccount, Ledger, hashed
from core.rebuild.lifecycle_contracts import CanonicalSignal, ExecutionRequest, SafetyDecision, SourceEvent, TradeIntent
from core.rebuild.lifecycle_service import LifecycleService


ACCOUNT = DemoAccount(account_id="p1-fixture", server="fixture", currency="USD", evidence_source="FIXTURE")
ORIGIN = datetime(2026, 1, 1, 10, tzinfo=timezone(timedelta(hours=5)))


def event(key="event-0001", source_type="MANUAL", **changes):
    return SourceEvent(**(dict(source_event_id=key, source_type=source_type, source_id="source-one",
                              source_message_id=key, sender_id="fixture-sender",
                              raw_text="EURUSD BUY ENTRY 100 SL 90 TP 120 TP2 130 RISK 1%",
                              original_timestamp="2026-01-01 10:00 +05:00", timezone_evidence="+05:00",
                              source_time_utc=ORIGIN, received_at=ORIGIN + timedelta(seconds=1),
                              metadata={"archive_id": "archive-fixture", "transcript_id": "transcript-fixture"}) | changes))


def service(path, fixture=True):
    ledger = Ledger(path, account=ACCOUNT)
    ledger.halt("Fixture halt")
    return LifecycleService(ledger, fixture_mode=fixture)


def prepare(svc, key="event-0001", source_type="MANUAL"):
    svc.save_source(event(key, source_type))
    signal = svc.validate_source(key)
    request = TradeIntent(client_order_id="client-" + key, signal_id=signal["signal_id"],
                          symbol=signal["symbol"], direction=signal["direction"], volume=.01,
                          entry=signal["entry"], stop_loss=signal["stop_loss"], take_profit=signal["take_profit"][0],
                          take_profit_targets=signal["take_profit"], entry_type=signal["entry_type"], requested_risk_pct=1.)
    return signal, request, svc.create_intent(request)


def decision(intent, key="decision-0001", verdict="APPROVED", **changes):
    return SafetyDecision(**(dict(safety_decision_id=key, intent_id=intent["intent_id"], decision=verdict,
                                 reason_codes=("FIXTURE_ONLY",), explanation="Synthetic fixture; no economic authorization",
                                 policy_id="p1-fixture", policy_version="1", decision_timestamp=datetime.now(timezone.utc),
                                 evidence_scope="FIXTURE", risk_budget=0.,
                                 approved_volume=.01 if verdict == "APPROVED" else 0.) | changes))


def execution(intent, key="request-0001", decision_id="decision-0001"):
    return ExecutionRequest(execution_request_id=key, intent_id=intent["intent_id"], safety_decision_id=decision_id)


def count(svc, table):
    with svc.ledger.connect() as conn:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_complete_fixture_chain_and_reopen(tmp_path):
    path = tmp_path / "p1.db"
    svc = service(path)
    signal, proposed, intent = prepare(svc)
    approval = decision(intent)
    recorded = svc.record_decision(approval)
    request = execution(intent)
    stored = svc.create_execution_request(request)
    assert svc.create_execution_request(request) == stored
    assert svc.create_intent(proposed) == intent
    assert svc.record_decision(approval) == recorded
    assert svc.validate_source("event-0001") == signal
    reopened = LifecycleService(Ledger(path, account=ACCOUNT), fixture_mode=True)
    assert reopened.create_execution_request(request) == stored
    trace = reopened.trace("event-0001")
    source = json.loads(trace["source_event"]["payload"])
    assert source["source_time_utc"] == "2026-01-01T05:00:00Z"
    assert source["timezone_evidence"] == "+05:00"
    assert source["original_timestamp"] == "2026-01-01 10:00 +05:00"
    assert source["metadata"]["transcript_id"] == "transcript-fixture"
    assert signal["source_event_id"] == "event-0001"
    assert signal["signal_id"] == hashed(["event-0001", "signal.v2", signal["parser_version"]])
    lifecycle = trace["lifecycles"][0]
    assert lifecycle["intent"]["signal_id"] == signal["signal_id"]
    assert lifecycle["safety_decisions"][0]["risk_decision_id"] == "decision-0001"
    assert lifecycle["execution_requests"][0]["account_key"] == ACCOUNT.key
    assert lifecycle["execution_requests"][0]["status"] == "RECORDED_NOT_SUBMITTED"
    assert all(not lifecycle[k] for k in ("broker_orders", "broker_deals", "positions", "outcomes"))
    assert trace["execution_enabled"] is False
    assert reopened.ledger.status()["halt"]["state"] == "HALTED"
    assert reopened.ledger.status()["broker_provenance"] == "UNAVAILABLE"


@pytest.mark.parametrize("source_type", ["MANUAL", "WHATSAPP_HUMAN", "NEXUSAI_STRATEGY", "HISTORICAL_WHATSAPP", "SCREENSHOT"])
def test_source_taxonomy_and_execution_eligibility(tmp_path, source_type):
    svc = service(tmp_path / "p1.db")
    if source_type in {"HISTORICAL_WHATSAPP", "SCREENSHOT"}:
        with pytest.raises(ValueError, match="Historical sources"):
            prepare(svc, source_type=source_type)
        assert count(svc, "signals") == 1
        assert count(svc, "order_intents") == 0
        assert count(svc, "risk_decisions") == 0
        assert count(svc, "execution_requests") == 0
        return
    signal, _, intent = prepare(svc, source_type=source_type)
    assert signal["source_type"] == source_type
    svc.record_decision(decision(intent))
    if source_type in {"MANUAL", "WHATSAPP_HUMAN"}:
        svc.create_execution_request(execution(intent))
    else:
        with pytest.raises(sqlite3.IntegrityError, match="approved fixture lineage"):
            svc.create_execution_request(execution(intent))
        assert count(svc, "execution_requests") == 0


def test_source_retry_and_conflicting_event_identity(tmp_path):
    svc = service(tmp_path / "p1.db")
    source = event()
    first = svc.save_source(source)
    retry = source.model_copy(update={"received_at": source.received_at + timedelta(seconds=10)})
    assert svc.save_source(retry) == first
    for changes in ({"raw_text": "EURUSD BUY ENTRY 100 SL 90 TP 140"}, {"source_event_id": "event-OTHER"},
                    {"source_id": "different"}, {"metadata": {"archive_id": "changed"}},
                    {"timezone_evidence": "unknown"}, {"sender_id": "changed"}):
        with pytest.raises(ValueError, match="conflict"):
            svc.save_source(source.model_copy(update=changes))
    assert count(svc, "source_events") == 1


def test_unknown_time_is_storable_but_not_validated(tmp_path):
    svc = service(tmp_path / "p1.db")
    saved = svc.save_source(event(source_time_utc=None, original_timestamp="ambiguous 1/2 10am", timezone_evidence=None))
    assert saved["status"] == "TIME_UNRESOLVED"
    with pytest.raises(ValueError, match="Unresolved timestamp"):
        svc.validate_source("event-0001")
    assert count(svc, "signals") == 0


@pytest.mark.parametrize("changes", [
    {"source_time_utc": datetime(2026, 1, 1)}, {"received_at": datetime(2026, 1, 1)},
    {"source_time_utc": ORIGIN + timedelta(days=1)}, {"source_time_utc": datetime(1960, 1, 1, tzinfo=timezone.utc)},
    {"original_timestamp": None}, {"source_type": "WHATSAPP"}, {"source_id": " "},
])
def test_invalid_source_contract(changes):
    with pytest.raises(ValidationError):
        event(**changes)


@pytest.mark.parametrize("changes", [
    {"direction": "HOLD"}, {"action": "SELL"}, {"action": "CLOSE"},
    {"volume": float("nan")}, {"entry": float("inf")}, {"stop_loss": -1.},
    {"take_profit_targets": (float("inf"),)}, {"requested_risk_pct": float("nan")},
    {"direction": "SELL"}, {"volume": True},
])
def test_invalid_intent_contract(tmp_path, changes):
    svc = service(tmp_path / "p1.db")
    _, request, _ = prepare(svc)
    with pytest.raises(ValidationError):
        svc.create_intent(request.model_copy(update=changes))


def test_independent_same_symbol_and_invalid_lineage(tmp_path):
    svc = service(tmp_path / "p1.db")
    s1, r1, i1 = prepare(svc)
    s2, _, i2 = prepare(svc, "event-0002")
    assert s1["signal_id"] != s2["signal_id"] and i1["intent_id"] != i2["intent_id"]
    for changes in ({"signal_id": "not-there", "client_order_id": "different-key"},
                    {"client_order_id": "different-key"}, {"volume": .02},
                    {"entry_type": "MARKET", "client_order_id": "different-key"},
                    {"requested_risk_pct": 2., "client_order_id": "different-key"}):
        with pytest.raises(ValueError):
            svc.create_intent(r1.model_copy(update=changes))
    svc.record_decision(decision(i1))
    with pytest.raises(ValueError, match="Exact approved"):
        svc.create_execution_request(execution(i2))
    assert len(svc.trace("event-0001")["lifecycles"]) == 1


def test_rejection_persists_and_cannot_be_overridden(tmp_path):
    svc = service(tmp_path / "p1.db")
    _, _, intent = prepare(svc)
    rejected = decision(intent, verdict="REJECTED")
    row = svc.record_decision(rejected)
    assert row["policy_version"] == "1" and row["explanation"] == rejected.explanation
    assert json.loads(row["reason_codes"]) == ["FIXTURE_ONLY"]
    with pytest.raises(ValueError, match="Exact approved"):
        svc.create_execution_request(execution(intent))
    with pytest.raises(ValueError, match="overridden"):
        svc.record_decision(decision(intent, key="decision-0002"))
    assert count(svc, "execution_requests") == 0


def test_missing_conflicting_and_later_veto_decisions(tmp_path):
    svc = service(tmp_path / "p1.db")
    _, _, intent = prepare(svc)
    with pytest.raises(ValueError):
        svc.create_execution_request(execution(intent))
    approved = decision(intent)
    svc.record_decision(approved)
    with pytest.raises(ValueError, match="identity conflict"):
        svc.record_decision(approved.model_copy(update={"explanation": "changed"}))
    svc.record_decision(decision(intent, key="decision-rejected", verdict="REJECTED"))
    with pytest.raises(ValueError, match="Rejected intent"):
        svc.create_execution_request(execution(intent))


@pytest.mark.parametrize("changes", [{"intent_id": "0" * 64}, {"approved_volume": .02},
                                   {"decision_timestamp": ORIGIN}, {"policy_id": "invented-p2-policy"}])
def test_invalid_decision_lineage_and_policy(tmp_path, changes):
    svc = service(tmp_path / "p1.db")
    _, _, intent = prepare(svc)
    with pytest.raises(ValueError):
        svc.record_decision(decision(intent, **changes))
    assert count(svc, "risk_decisions") == 0


@pytest.mark.parametrize("changes", [{"risk_budget": float("nan")}, {"approved_volume": float("inf")},
                                   {"reason_codes": (" ",)}, {"evidence_scope": "P1_DISABLED"}])
def test_invalid_decision_contract(changes):
    with pytest.raises(ValidationError):
        decision({"intent_id": "0" * 64}, **changes)


def test_concurrent_request_replay_and_conflicting_ids(tmp_path):
    svc = service(tmp_path / "p1.db")
    _, _, intent = prepare(svc)
    svc.record_decision(decision(intent))
    request = execution(intent)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: svc.create_execution_request(request), range(12)))
    assert all(row == results[0] for row in results)
    assert count(svc, "execution_requests") == 1
    with pytest.raises(ValueError, match="identity conflict"):
        svc.create_execution_request(execution(intent, key="request-other"))
    _, _, other = prepare(svc, "event-0002")
    svc.record_decision(decision(other, key="decision-other"))
    with pytest.raises(ValueError, match="identity conflict"):
        svc.create_execution_request(execution(other, decision_id="decision-other"))


def test_concurrent_default_rejection_retains_one_timestamp(tmp_path):
    svc = service(tmp_path / "p1.db", fixture=False)
    _, _, intent = prepare(svc)
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda _: svc.reject_intent(intent["intent_id"], "decision-retry"), range(12)))
    assert all(row == rows[0] for row in rows)
    assert count(svc, "risk_decisions") == 1


@pytest.mark.parametrize("stop", ["inside_transaction", "after_commit"])
def test_process_crash_and_service_retry(tmp_path, stop):
    path = tmp_path / "crash.db"
    script = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
from test_p1_lifecycle import service, prepare, decision, execution
svc = service(Path(sys.argv[3]))
_, _, intent = prepare(svc)
svc.record_decision(decision(intent))
if sys.argv[4] == 'inside_transaction':
    svc.ledger.audit = lambda *args: os._exit(73)
svc.create_execution_request(execution(intent))
os._exit(73)
"""
    tests = Path(__file__).parent
    result = subprocess.run([sys.executable, "-B", "-c", script, str(tests.parent), str(tests), str(path), stop],
                            capture_output=True, timeout=40)
    assert result.returncode == 73, result.stderr.decode()
    svc = service(path)
    assert count(svc, "execution_requests") == int(stop == "after_commit")
    _, _, intent = prepare(svc)
    svc.create_execution_request(execution(intent))
    assert count(svc, "execution_requests") == 1
    assert count(svc, "risk_decisions") == 1
    with svc.ledger.connect() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("operation,table", [("source", "source_events"), ("intent", "order_intents"),
                                            ("decision", "risk_decisions"), ("request", "execution_requests")])
def test_failed_audit_rolls_back_operation(tmp_path, monkeypatch, operation, table):
    svc = service(tmp_path / "p1.db")
    if operation != "source":
        svc.save_source(event())
        signal = svc.validate_source("event-0001")
        request = TradeIntent(client_order_id="client-one", signal_id=signal["signal_id"], symbol="EURUSD",
                              direction="BUY", volume=.01, entry=100., stop_loss=90., take_profit=120.,
                              take_profit_targets=(120., 130.), entry_type="LIMIT", requested_risk_pct=1.)
        if operation != "intent":
            intent = svc.create_intent(request)
            approved = decision(intent)
            if operation == "request":
                svc.record_decision(approved)
    def fail(*args):
        raise sqlite3.OperationalError("injected audit failure")
    monkeypatch.setattr(svc.ledger, "audit", fail)
    calls = {"source": lambda: svc.save_source(event()), "intent": lambda: svc.create_intent(request),
             "decision": lambda: svc.record_decision(approved), "request": lambda: svc.create_execution_request(execution(intent))}
    with pytest.raises(sqlite3.OperationalError, match="injected"):
        calls[operation]()
    assert count(svc, table) == 0
    monkeypatch.undo()
    calls[operation]()
    assert count(svc, table) == 1


@pytest.mark.parametrize("statement", ["UPDATE source_events SET source_id='changed'", "DELETE FROM source_events",
                                     "UPDATE execution_requests SET status='SUBMITTED'", "DELETE FROM execution_requests",
                                     "DELETE FROM risk_decisions"])
def test_database_identity_guards(tmp_path, statement):
    svc = service(tmp_path / "p1.db")
    _, _, intent = prepare(svc)
    svc.record_decision(decision(intent))
    svc.create_execution_request(execution(intent))
    with svc.ledger.transaction() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(statement)


def test_sql_request_guard_rejects_unapproved_lineage(tmp_path):
    svc = service(tmp_path / "p1.db")
    _, _, intent = prepare(svc)
    svc.record_decision(decision(intent, verdict="REJECTED"))
    with svc.ledger.transaction() as conn, pytest.raises(sqlite3.IntegrityError, match="approved fixture lineage"):
        conn.execute("INSERT INTO execution_requests VALUES(?,?,?,?,?,?,?,?,?)",
                     ("request-0001", intent["intent_id"], "decision-0001", intent["client_order_id"], ACCOUNT.key,
                      "RECORDED_NOT_SUBMITTED", "FIXTURE", "hash", datetime.now(timezone.utc).isoformat()))


def test_forged_signal_source_lineage_and_unknown_trace(tmp_path):
    svc = service(tmp_path / "p1.db")
    signal, _, _ = prepare(svc)
    forged = CanonicalSignal.model_validate_json(json.dumps(signal)).model_copy(update={"source_event_id": "event-missing", "signal_id": "f" * 64, "source_message_id": "different"})
    with pytest.raises(sqlite3.IntegrityError, match="source event lineage"):
        svc.ledger.save_signal(forged)
    with pytest.raises(KeyError):
        svc.trace("missing-event")


def test_active_app_auth_halt_and_default_rejection(tmp_path):
    app = create_app(database_path=tmp_path / "api.db", token="fixture-token", lifecycle_account=ACCOUNT)
    with TestClient(app) as client:
        assert client.post("/api/core/lifecycle/sources", json=event().model_dump(mode="json")).status_code == 403
        client.headers["X-Control-Token"] = "fixture-token"
        assert client.post("/api/core/lifecycle/sources", json=event().model_dump(mode="json")).status_code == 200
        r = client.post("/api/core/lifecycle/signals", json={"source_event_id": "event-0001"})
        assert r.status_code == 200, r.text
        _, request, intent = prepare(app.state.lifecycle)
        assert client.post("/api/core/lifecycle/intents", json=request.model_dump(mode="json")).status_code == 200
        path = f"/api/core/lifecycle/intents/{intent['intent_id']}/evaluate"
        body = {"safety_decision_id": "decision-default"}
        first = client.post(path, json=body)
        assert first.status_code == 200 and first.json()["record"]["decision"] == "REJECTED"
        assert client.post(path, json=body).json() == first.json()
        assert client.post(path, json=body | {"decision": "APPROVED"}).status_code == 422
        assert client.post("/api/core/lifecycle/requests", json=execution(intent, decision_id="decision-default").model_dump()).status_code == 409
        assert client.get("/api/core/lifecycle/sources/event-0001/trace").status_code == 200
        assert client.post("/api/controls/reset-kill-switch").status_code == 423
        status = client.get("/api/core/status").json()
        assert status["execution_enabled"] is False and status["halt"]["state"] == "HALTED"
        assert status["agents_running"] == 0
        assert count(app.state.lifecycle, "broker_orders") == 0


def test_fixture_request_through_same_active_composition(tmp_path):
    app = create_app(database_path=tmp_path / "fixture.db", token="fixture-token", lifecycle_account=ACCOUNT, fixture_mode=True)
    with TestClient(app) as client:
        client.headers["X-Control-Token"] = "fixture-token"
        _, _, intent = prepare(app.state.lifecycle)
        # Approval is injected into the explicit fixture service, never accepted from HTTP.
        app.state.lifecycle.record_decision(decision(intent))
        response = client.post("/api/core/lifecycle/requests", json=execution(intent).model_dump())
        assert response.status_code == 200, response.text
        assert response.json()["execution_enabled"] is False
        assert response.json()["record"]["evidence_scope"] == "FIXTURE"


def test_unbound_default_and_no_implicit_fixture_account(tmp_path):
    app = create_app(database_path=tmp_path / "unbound.db", token="fixture-token")
    with TestClient(app):
        with pytest.raises(ValueError, match="P4_SOURCE_NOT_AUTHORIZED"):
            prepare(app.state.lifecycle)
        assert count(app.state.lifecycle, "source_events") == 0
        assert count(app.state.lifecycle, "signals") == 0
        assert count(app.state.lifecycle, "order_intents") == 0
    unbound = LifecycleService(Ledger(tmp_path / "unbound-domain.db"))
    with pytest.raises(ValueError, match="binding required"):
        prepare(unbound)
    assert count(unbound, "source_events") == 1
    assert count(unbound, "signals") == 1
    assert count(unbound, "order_intents") == 0
    with pytest.raises(ValueError, match="isolated database"):
        create_app(token="fixture-token", fixture_mode=True)
    with pytest.raises(ValueError, match="synthetic FIXTURE"):
        create_app(database_path=tmp_path / "none.db", token="fixture-token", lifecycle_account=ACCOUNT.model_copy(update={"evidence_source": "MT5_DEMO"}))


def test_additive_migration_preserves_v2_predecessor_and_failure_rollback(tmp_path):
    from core.rebuild.migration_runner import migrate
    path = tmp_path / "old.db"
    migrations = Path(__file__).parents[1] / "core/rebuild/migrations"
    with sqlite3.connect(path, isolation_level=None) as conn:
        conn.executescript((migrations / "001_lifecycle.sql").read_text())
        conn.executescript((migrations / "002_identity_integrity.sql").read_text())
        conn.execute("UPDATE halt_state SET reason='preserved evidence'")
        conn.execute("INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?,?)", ("legacy-id", "WHATSAPP", "g", "m", "old-hash", "{}", 1000., 1001., "deterministic_v2", "VALID"))
        conn.execute("CREATE TABLE source_events(already_present TEXT)")
        with pytest.raises(sqlite3.OperationalError):
            migrate(conn)
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 2
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='execution_requests'").fetchone()
        conn.execute("DROP TABLE source_events")
        migrate(conn)
        assert conn.execute("SELECT payload,source_type,source_event_id FROM signals").fetchone() == ("{}", "WHATSAPP", None)
        assert conn.execute("SELECT reason FROM halt_state").fetchone()[0] == "preserved evidence"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        for n in (1, 2):
            script = next(migrations.glob(f"00{n}_*.sql")).read_text()
            assert conn.execute("SELECT sha256 FROM migration_checksums WHERE version=?", (n,)).fetchone()[0] == hashlib.sha256(script.encode()).hexdigest()
