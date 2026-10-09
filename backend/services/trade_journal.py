"""Local-only SQLite trade journal for private signal and execution audit."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_JOURNAL_PATH = Path(__file__).resolve().parents[1] / "data" / "private_trade_journal.sqlite3"


class TradeJournal:
    def __init__(self, db_path: Optional[str] = None, hash_salt: Optional[str] = None):
        self.db_path = Path(db_path or os.getenv("TRADE_JOURNAL_DB", str(DEFAULT_JOURNAL_PATH)))
        self.hash_salt = hash_salt or os.getenv("PRIVATE_ID_HASH_SALT", "local-development-salt")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trade_signals (
                    signal_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    group_id_hash TEXT NOT NULL,
                    sender_id_hash TEXT NOT NULL,
                    raw_message_hash TEXT NOT NULL,
                    message_timestamp REAL NOT NULL,
                    received_timestamp REAL NOT NULL,
                    instrument TEXT,
                    direction TEXT,
                    entry_type TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit_1 REAL,
                    take_profit_2 REAL,
                    take_profit_3 REAL,
                    requested_risk_pct REAL,
                    parser_confidence REAL NOT NULL,
                    parser_version TEXT NOT NULL,
                    validation_status TEXT NOT NULL,
                    risk_status TEXT NOT NULL DEFAULT 'PENDING',
                    execution_status TEXT NOT NULL DEFAULT 'PENDING',
                    rejection_reasons TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    severity TEXT NOT NULL,
                    code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )

    def hash_identifier(self, value: str) -> str:
        raw = f"{self.hash_salt}:{value}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def record_signal(self, signal: Any, *, source: str = "private_signal") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_signals (
                    signal_id, message_id, source, group_id_hash, sender_id_hash,
                    raw_message_hash, message_timestamp, received_timestamp,
                    instrument, direction, entry_type, entry_price, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3, requested_risk_pct,
                    parser_confidence, parser_version, validation_status,
                    rejection_reasons, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.message_id,
                    source,
                    self.hash_identifier(signal.group_id),
                    self.hash_identifier(signal.sender_id),
                    self.hash_identifier(signal.raw_message),
                    signal.message_timestamp,
                    signal.received_timestamp,
                    signal.instrument,
                    signal.direction,
                    signal.entry_type,
                    signal.entry_price,
                    signal.stop_loss,
                    signal.take_profit_1,
                    signal.take_profit_2,
                    signal.take_profit_3,
                    signal.requested_risk_pct,
                    signal.parser_confidence,
                    signal.parser_version,
                    signal.validation_status,
                    json.dumps(signal.rejection_reasons),
                    time.time(),
                ),
            )

    def record_execution_event(self, signal_id: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_events (signal_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (signal_id, event_type, json.dumps(payload, default=str), time.time()),
            )

    def alert(self, severity: str, code: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts (severity, code, message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (severity, code, message, json.dumps(payload or {}, default=str), time.time()),
            )

    def message_seen(self, message_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM trade_signals WHERE message_id = ? LIMIT 1",
                (message_id,),
            ).fetchone()
        return row is not None

    def recent_signals(self, limit: int = 50) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_signals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def recent_alerts(self, limit: int = 50) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        for key in ("payload_json", "rejection_reasons"):
            if key in data and isinstance(data[key], str):
                try:
                    data[key] = json.loads(data[key])
                except json.JSONDecodeError:
                    pass
        return data
