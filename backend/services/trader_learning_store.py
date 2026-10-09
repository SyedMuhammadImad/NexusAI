"""Local-only trader learning store for private provider patterns."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


DEFAULT_TRADER_LEARNING_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "private_trader_learning.sqlite3"
)
MIN_SHADOW_SAMPLE_SIZE = 100


class TraderLearningStore:
    """Stores raw private examples locally and exposes redacted summaries only."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or DEFAULT_TRADER_LEARNING_PATH)
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
                CREATE TABLE IF NOT EXISTS trader_signals (
                    signal_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'private_signal',
                    message_id TEXT,
                    raw_message TEXT,
                    parsed_signal_json TEXT NOT NULL,
                    instrument TEXT,
                    direction TEXT,
                    signal_timestamp REAL,
                    received_timestamp REAL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    validation_status TEXT,
                    rejection_reasons_json TEXT DEFAULT '[]',
                    market_snapshot_json TEXT DEFAULT '{}',
                    execution_status TEXT DEFAULT 'PENDING',
                    outcome_status TEXT DEFAULT 'OPEN',
                    pnl REAL,
                    pnl_r REAL,
                    created_at REAL,
                    updated_at REAL
                );

                CREATE TABLE IF NOT EXISTS trader_execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trader_shadow_predictions (
                    prediction_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    prediction_timestamp REAL NOT NULL,
                    predicted_entry REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    imitation_probability REAL,
                    performance_quality REAL,
                    features_json TEXT NOT NULL,
                    matched_signal_id TEXT,
                    match_quality_json TEXT DEFAULT '{}',
                    outcome_json TEXT DEFAULT '{}',
                    created_at REAL,
                    updated_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_trader_signals_symbol_direction
                ON trader_signals (instrument, direction);

                CREATE INDEX IF NOT EXISTS idx_trader_signals_updated_at
                ON trader_signals (updated_at);

                CREATE INDEX IF NOT EXISTS idx_trader_predictions_created_at
                ON trader_shadow_predictions (created_at);
                """
            )

    def record_signal(
        self,
        *,
        signal_id: str,
        source: str,
        message_id: Optional[str],
        raw_message: Optional[str],
        parsed_signal: Dict[str, Any],
        market_snapshot: Optional[Dict[str, Any]],
        validation_status: str,
        rejection_reasons: Iterable[str],
    ) -> None:
        if not signal_id:
            return
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trader_signals (
                    signal_id, source, message_id, raw_message, parsed_signal_json,
                    instrument, direction, signal_timestamp, received_timestamp,
                    entry_price, stop_loss, take_profit, validation_status,
                    rejection_reasons_json, market_snapshot_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_id) DO UPDATE SET
                    raw_message=COALESCE(excluded.raw_message, raw_message),
                    parsed_signal_json=excluded.parsed_signal_json,
                    instrument=excluded.instrument,
                    direction=excluded.direction,
                    signal_timestamp=excluded.signal_timestamp,
                    received_timestamp=excluded.received_timestamp,
                    entry_price=excluded.entry_price,
                    stop_loss=excluded.stop_loss,
                    take_profit=excluded.take_profit,
                    validation_status=excluded.validation_status,
                    rejection_reasons_json=excluded.rejection_reasons_json,
                    market_snapshot_json=excluded.market_snapshot_json,
                    updated_at=excluded.updated_at
                """,
                (
                    signal_id,
                    source or "private_signal",
                    message_id,
                    raw_message,
                    json.dumps(parsed_signal),
                    parsed_signal.get("instrument") or parsed_signal.get("symbol"),
                    parsed_signal.get("direction"),
                    self._float_or_none(parsed_signal.get("message_timestamp")),
                    self._float_or_none(parsed_signal.get("received_timestamp")),
                    self._float_or_none(parsed_signal.get("entry_price")),
                    self._float_or_none(parsed_signal.get("stop_loss")),
                    self._float_or_none(
                        parsed_signal.get("take_profit")
                        or parsed_signal.get("take_profit_1")
                    ),
                    validation_status,
                    json.dumps(list(rejection_reasons or [])),
                    json.dumps(market_snapshot or {}),
                    now,
                    now,
                ),
            )

    def record_execution_event(self, signal_id: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
        if not signal_id:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trader_execution_events (signal_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (signal_id, event_type, json.dumps(payload), time.time()),
            )

    def record_status(self, signal_id: Optional[str], *, execution_status: Optional[str] = None, outcome_status: Optional[str] = None) -> None:
        if not signal_id:
            return
        updates = []
        values: list[Any] = []
        if execution_status:
            updates.append("execution_status=?")
            values.append(execution_status)
        if outcome_status:
            updates.append("outcome_status=?")
            values.append(outcome_status)
        if not updates:
            return
        updates.append("updated_at=?")
        values.append(time.time())
        values.append(signal_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE trader_signals SET {', '.join(updates)} WHERE signal_id=?",
                values,
            )

    def record_close(self, signal_id: Optional[str], payload: Dict[str, Any]) -> None:
        if not signal_id:
            return
        pnl = self._float_or_none(payload.get("pnl"))
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trader_signals
                SET outcome_status='CLOSED', pnl=?, updated_at=?
                WHERE signal_id=?
                """,
                (pnl, time.time(), signal_id),
            )

    def record_shadow_prediction(
        self,
        *,
        symbol: str,
        direction: str,
        predicted_entry: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
        imitation_probability: Optional[float],
        performance_quality: Optional[float],
        features: Dict[str, Any],
        matched_signal_id: Optional[str],
        match_quality: Optional[Dict[str, Any]] = None,
        outcome: Optional[Dict[str, Any]] = None,
        prediction_id: Optional[str] = None,
    ) -> str:
        now = time.time()
        prediction_id = prediction_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trader_shadow_predictions (
                    prediction_id, symbol, direction, prediction_timestamp,
                    predicted_entry, stop_loss, take_profit,
                    imitation_probability, performance_quality, features_json,
                    matched_signal_id, match_quality_json, outcome_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(prediction_id) DO UPDATE SET
                    imitation_probability=excluded.imitation_probability,
                    performance_quality=excluded.performance_quality,
                    features_json=excluded.features_json,
                    match_quality_json=excluded.match_quality_json,
                    outcome_json=excluded.outcome_json,
                    updated_at=excluded.updated_at
                """,
                (
                    prediction_id,
                    symbol or "UNKNOWN",
                    direction or "UNKNOWN",
                    now,
                    predicted_entry,
                    stop_loss,
                    take_profit,
                    imitation_probability,
                    performance_quality,
                    json.dumps(features or {}),
                    matched_signal_id,
                    json.dumps(match_quality or {}),
                    json.dumps(outcome or {}),
                    now,
                    now,
                ),
            )
        return prediction_id

    def training_examples(self, *, limit: int = 5000) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM trader_signals
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 20000)),),
            ).fetchall()
        return [self._signal_row(row) for row in rows]

    def execution_events_by_signal_ids(self, signal_ids: Iterable[str], *, limit_per_signal: int = 50) -> dict[str, list[dict]]:
        ids = [signal_id for signal_id in signal_ids if signal_id]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        max_rows = max(1, min(int(limit_per_signal), 250)) * len(ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT signal_id, event_type, payload_json, created_at
                FROM trader_execution_events
                WHERE signal_id IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [*ids, max_rows],
            ).fetchall()

        grouped: dict[str, list[dict]] = {signal_id: [] for signal_id in ids}
        for row in rows:
            grouped.setdefault(row["signal_id"], []).append(
                {
                    "event_type": row["event_type"],
                    "payload": self._loads_dict(row["payload_json"]),
                    "created_at": row["created_at"],
                }
            )
        return {
            signal_id: events[: max(1, min(int(limit_per_signal), 250))]
            for signal_id, events in grouped.items()
        }

    def summary(self, *, recent_limit: int = 25) -> dict:
        with self._connect() as conn:
            totals = self._row_to_dict(
                conn.execute(
                    """
                    SELECT
                        COUNT(*) AS tracked_signals,
                        SUM(CASE WHEN raw_message IS NOT NULL AND raw_message != '' THEN 1 ELSE 0 END) AS raw_examples,
                        SUM(CASE WHEN validation_status='ACCEPTED' THEN 1 ELSE 0 END) AS accepted_signals,
                        SUM(CASE WHEN execution_status IN ('REQUESTED','ADOPTED','FILLED') THEN 1 ELSE 0 END) AS acted_signals,
                        SUM(CASE WHEN outcome_status='CLOSED' THEN 1 ELSE 0 END) AS closed_signals,
                        AVG(pnl) AS avg_pnl
                    FROM trader_signals
                    """
                ).fetchone()
            )
            by_symbol = [
                self._stat_row(row)
                for row in conn.execute(
                    """
                    SELECT instrument, direction, COUNT(*) AS sample_size,
                           SUM(CASE WHEN validation_status='ACCEPTED' THEN 1 ELSE 0 END) AS accepted,
                           AVG(pnl) AS avg_pnl
                    FROM trader_signals
                    GROUP BY instrument, direction
                    ORDER BY sample_size DESC, instrument ASC
                    LIMIT 20
                    """
                ).fetchall()
            ]
            recent = [
                self._signal_row(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM trader_signals
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(recent_limit), 250)),),
                ).fetchall()
            ]
            predictions = [
                self._prediction_row(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM trader_shadow_predictions
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(recent_limit), 250)),),
                ).fetchall()
            ]

        total_count = int(totals.get("tracked_signals") or 0)
        return {
            "learning_mode": "observation_only",
            "copy_agent_separate": True,
            "independent_execution_enabled": False,
            "shadow_sample_threshold": MIN_SHADOW_SAMPLE_SIZE,
            "shadow_ready": total_count >= MIN_SHADOW_SAMPLE_SIZE,
            "recommendation": self._recommendation(total_count),
            "totals": self._rounded_totals(totals),
            "by_symbol_direction": by_symbol,
            "recent_signals": recent,
            "recent_shadow_predictions": predictions,
            "timestamp": time.time(),
        }

    def _recommendation(self, total_count: int) -> str:
        if total_count < MIN_SHADOW_SAMPLE_SIZE:
            return f"Import or observe {MIN_SHADOW_SAMPLE_SIZE - total_count} more provider signals before training a real imitation filter."
        return "Enough provider signals exist for offline model review; keep predictions in shadow mode until manually approved."

    def _stat_row(self, row: sqlite3.Row) -> dict:
        data = self._row_to_dict(row)
        data["sample_size"] = int(data.get("sample_size") or 0)
        data["accepted"] = int(data.get("accepted") or 0)
        data["avg_pnl"] = self._round_or_none(data.get("avg_pnl"))
        return data

    def _signal_row(self, row: sqlite3.Row) -> dict:
        data = self._row_to_dict(row)
        data["raw_message"] = None
        data["raw_message_stored"] = bool(row["raw_message"])
        data["parsed_signal"] = self._loads_dict(data.pop("parsed_signal_json", "{}"))
        data["rejection_reasons"] = self._loads_list(data.pop("rejection_reasons_json", "[]"))
        data["market_snapshot"] = self._loads_dict(data.pop("market_snapshot_json", "{}"))
        for key in ("signal_timestamp", "received_timestamp", "entry_price", "stop_loss", "take_profit", "pnl", "pnl_r"):
            data[key] = self._round_or_none(data.get(key))
        return data

    def _prediction_row(self, row: sqlite3.Row) -> dict:
        data = self._row_to_dict(row)
        data["features"] = self._loads_dict(data.pop("features_json", "{}"))
        data["match_quality"] = self._loads_dict(data.pop("match_quality_json", "{}"))
        data["outcome"] = self._loads_dict(data.pop("outcome_json", "{}"))
        for key in ("predicted_entry", "stop_loss", "take_profit", "imitation_probability", "performance_quality"):
            data[key] = self._round_or_none(data.get(key))
        return data

    def _rounded_totals(self, totals: dict) -> dict:
        rounded = dict(totals)
        for key in ("tracked_signals", "raw_examples", "accepted_signals", "acted_signals", "closed_signals"):
            rounded[key] = int(rounded.get(key) or 0)
        rounded["avg_pnl"] = self._round_or_none(rounded.get("avg_pnl"))
        return rounded

    def _loads_dict(self, value: Any) -> dict:
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _loads_list(self, value: Any) -> list:
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else [parsed]

    def _row_to_dict(self, row: Optional[sqlite3.Row]) -> dict:
        if row is None:
            return {}
        return {key: row[key] for key in row.keys()}

    def _float_or_none(self, value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed

    def _round_or_none(self, value: Any, digits: int = 4) -> Optional[float]:
        parsed = self._float_or_none(value)
        return round(parsed, digits) if parsed is not None else None
