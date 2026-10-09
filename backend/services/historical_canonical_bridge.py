"""Recoverable historical evidence projection. No intent, approval or execution writer."""

import json
from datetime import datetime, timezone

from core.rebuild.ledger import canonical, hashed, now
from core.rebuild.lifecycle_contracts import SourceEvent
from services.chat_import_service import parser_differences
from services.signal_parser import PARSER_VERSION


class HistoricalCanonicalBridge:
    def __init__(self, archive, lifecycle):
        self.archive = archive
        self.lifecycle = lifecycle
        self.ledger = lifecycle.ledger

    def get(self, import_id, message_id):
        with self.ledger.connect() as conn:
            row = conn.execute("SELECT * FROM historical_links WHERE import_id=? AND message_id=?", (import_id, message_id)).fetchone()
        if not row:
            raise KeyError("Historical link not found")
        return {**dict(row), "execution_enabled": False, "execution_eligibility": "NONE",
                "review_semantics": "HISTORICAL_ACCEPTANCE_ONLY"}

    def _checkpoint(self, import_id, message_id, status, reason, snapshot):
        with self.ledger.transaction() as conn:
            row = conn.execute("SELECT * FROM historical_links WHERE import_id=? AND message_id=?", (import_id, message_id)).fetchone()
            source = conn.execute("SELECT source_event_id FROM source_events WHERE source_event_id=?", (row["candidate_source_event_id"],)).fetchone()
            signal = conn.execute("SELECT signal_id FROM signals WHERE source_event_id=?", (source[0],)).fetchone() if source else None
            # A slower concurrent retry must not downgrade a completed identical snapshot.
            if row["status"] == "VALIDATED" and row["review_snapshot"] == snapshot and status == "SOURCE_ONLY":
                return
            if status == "VALIDATED" and (not source or not signal):
                raise ValueError("Validated historical linkage requires persisted source and signal")
            values = (source[0] if source else None, signal[0] if signal else None, status, reason, snapshot)
            if values != tuple(row[k] for k in ("source_event_id", "signal_id", "status", "reason", "review_snapshot")):
                conn.execute("UPDATE historical_links SET source_event_id=?,signal_id=?,status=?,reason=?,review_snapshot=?,updated_at=? WHERE import_id=? AND message_id=?",
                             (*values, now(), import_id, message_id))
                self.ledger.audit(conn, "HISTORICAL_PROMOTION_CHECKPOINT", None,
                                  {"import_id": import_id, "message_id": message_id, "status": status,
                                   "reason": reason, "review_snapshot": json.loads(snapshot)})

    def promote(self, import_id, message_id):
        imported, message = self.archive.historical_record(import_id, message_id)
        if message["kind"] != "signal":
            raise ValueError("Only historical signal candidates can be projected")
        historical_id = message.get("historical_message_id")
        candidate = "hist-" + hashed(["historical-source.v1", historical_id or [import_id, message_id]])
        snapshot = canonical({"review_status": message["review_status"], "signal": message.get("signal"),
                              "review_history": message.get("review_history", []), "reasons": message["reasons"],
                              "raw_record": message.get("raw_record"), "identity_content": message.get("identity_content"),
                              "original_timestamp": message.get("original_timestamp"),
                              "local_time": message["local_time"], "sender": message["sender"],
                              "date_order": imported["date_order"], "utc_offset": imported["utc_offset"],
                              "time_evidence_confirmed": imported.get("time_evidence_confirmed", False),
                              "parser_version": PARSER_VERSION, "duplicate_of": imported.get("duplicate_of")})
        with self.ledger.transaction() as conn:
            conn.execute("INSERT INTO historical_links VALUES(?,?,?,?,?,?,NULL,NULL,'PENDING','',?,?,?) ON CONFLICT(import_id,message_id) DO NOTHING",
                         (import_id, message_id, imported.get("archive_hash"), imported.get("transcript_fingerprint"),
                          historical_id, candidate, snapshot, now(), now()))
        try:
            if not historical_id or not imported.get("archive_hash") or not message.get("raw_evidence_parsed"):
                raise ValueError("Legacy import lacks canonical identity/raw evidence; explicit re-import review required")
            confirmed = imported.get("time_evidence_confirmed", False)
            event = SourceEvent(
                source_event_id=candidate, source_type="HISTORICAL_WHATSAPP", source_id=imported["group"],
                source_message_id=historical_id, sender_id=message["raw_sender"], raw_text=message["raw_body"],
                original_timestamp=message["original_timestamp"],
                timezone_evidence=f"export profile: {imported['date_order']}; UTC offset minutes {imported['utc_offset']}" if confirmed else None,
                source_time_utc=datetime.fromtimestamp(message["timestamp"], timezone.utc) if confirmed else None,
                received_at=datetime.fromtimestamp(imported["created"], timezone.utc),
                metadata={"identity_version": imported["identity_version"], "parser_version": PARSER_VERSION,
                          "parser_normalization": "historical-text.v1", "execution_eligibility": "NONE"})
            self.lifecycle.save_source(event)
            self._checkpoint(import_id, message_id, "SOURCE_ONLY", "Awaiting deterministic validation", snapshot)
            if not confirmed:
                raise ValueError("Explicit date order and UTC offset evidence required; review defaults are untrusted")
            if message["reasons"] or parser_differences(message, imported["group"]):
                raise ValueError("Historical review or corrected parser projection requires explicit revision")
            self.lifecycle.validate_source(candidate)
            self._checkpoint(import_id, message_id, "VALIDATED", "Historical evidence only; no execution authorization", snapshot)
        except ValueError as exc:
            self._checkpoint(import_id, message_id, "REVIEW_REQUIRED", str(exc), snapshot)
        # Technical errors propagate, leaving PENDING/SOURCE_ONLY for idempotent retry.
        return self.get(import_id, message_id)
