"""Local private storage for uploaded signal screenshots and parsed results."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_IMAGE_SIGNAL_DB = Path(__file__).resolve().parents[1] / "data" / "private_signal_images.sqlite3"


class ImageSignalStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or DEFAULT_IMAGE_SIGNAL_DB)
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
                CREATE TABLE IF NOT EXISTS image_signals (
                    image_id TEXT PRIMARY KEY,
                    image_hash TEXT NOT NULL UNIQUE,
                    image_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'ui_execution_upload',
                    raw_extracted_text TEXT,
                    extracted_json TEXT NOT NULL DEFAULT '{}',
                    normalized_text TEXT,
                    parsed_signal_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    rejection_reasons_json TEXT NOT NULL DEFAULT '[]',
                    submit_result_json TEXT NOT NULL DEFAULT '{}',
                    submitted_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_image_signals_updated_at
                ON image_signals (updated_at);
                """
            )

    def upsert_parse_result(
        self,
        *,
        image_id: str,
        image_hash: str,
        image_path: str,
        mime_type: str,
        source: str,
        raw_extracted_text: Optional[str],
        extracted_json: Dict[str, Any],
        normalized_text: Optional[str],
        parsed_signal: Dict[str, Any],
        status: str,
        rejection_reasons: list[str],
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO image_signals (
                    image_id, image_hash, image_path, mime_type, source,
                    raw_extracted_text, extracted_json, normalized_text,
                    parsed_signal_json, status, rejection_reasons_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_hash) DO UPDATE SET
                    raw_extracted_text=excluded.raw_extracted_text,
                    extracted_json=excluded.extracted_json,
                    normalized_text=excluded.normalized_text,
                    parsed_signal_json=excluded.parsed_signal_json,
                    status=excluded.status,
                    rejection_reasons_json=excluded.rejection_reasons_json,
                    updated_at=excluded.updated_at
                """,
                (
                    image_id,
                    image_hash,
                    image_path,
                    mime_type,
                    source,
                    raw_extracted_text,
                    json.dumps(extracted_json, default=str),
                    normalized_text,
                    json.dumps(parsed_signal, default=str),
                    status,
                    json.dumps(rejection_reasons),
                    now,
                    now,
                ),
            )

    def update_submit_result(self, image_id: str, submit_result: Dict[str, Any], status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE image_signals
                SET submit_result_json=?, status=?, submitted_at=?, updated_at=?
                WHERE image_id=?
                """,
                (
                    json.dumps(submit_result, default=str),
                    status,
                    time.time(),
                    time.time(),
                    image_id,
                ),
            )

    def get(self, image_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM image_signals WHERE image_id=?",
                (image_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_by_hash(self, image_hash: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM image_signals WHERE image_hash=?",
                (image_hash,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def recent(self, limit: int = 25) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM image_signals ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 250)),),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        for key in ("extracted_json", "parsed_signal_json", "rejection_reasons_json", "submit_result_json"):
            try:
                data[key] = json.loads(data.get(key) or "{}")
            except (TypeError, json.JSONDecodeError):
                data[key] = {} if key != "rejection_reasons_json" else []
        return data
