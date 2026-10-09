"""Local-only setup learning store for private provider signals."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


DEFAULT_SETUP_LEARNING_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "private_setup_learning.sqlite3"
)
MIN_AUTOMATION_SAMPLE_SIZE = 20


class SetupLearningStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or DEFAULT_SETUP_LEARNING_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_setups (
                    signal_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'private_signal',
                    instrument TEXT,
                    direction TEXT,
                    entry_type TEXT,
                    stop_loss REAL,
                    take_profit REAL,
                    requested_risk_pct REAL,
                    parser_confidence REAL,
                    signal_age REAL,
                    weekday_utc INTEGER,
                    hour_utc INTEGER,
                    accepted_at REAL,
                    entry_price REAL,
                    spread_bps REAL,
                    risk_amount_usd REAL,
                    risk_reward_ratio REAL,
                    risk_status TEXT DEFAULT 'PENDING',
                    execution_status TEXT DEFAULT 'PENDING',
                    outcome_status TEXT DEFAULT 'OPEN',
                    pnl REAL,
                    pnl_r REAL,
                    rejection_reasons TEXT DEFAULT '[]',
                    updated_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_provider_setups_symbol_direction
                ON provider_setups (instrument, direction)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_provider_setups_updated_at
                ON provider_setups (updated_at)
                """
            )

    def record_signal(self, payload: Dict[str, Any]) -> None:
        signal_id = self._signal_id(payload)
        if not signal_id:
            return

        now = time.time()
        timestamp = float(payload.get("message_timestamp") or payload.get("accepted_at") or now)
        utc = time.gmtime(timestamp)
        reasons = payload.get("rejection_reasons") or []
        status = payload.get("validation_status") or "ACCEPTED"
        outcome = "REJECTED" if status == "REJECTED" else "OPEN"

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_setups (
                    signal_id, source, instrument, direction, entry_type,
                    stop_loss, take_profit, requested_risk_pct, parser_confidence,
                    signal_age, weekday_utc, hour_utc, accepted_at,
                    risk_status, execution_status, outcome_status,
                    rejection_reasons, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_id) DO UPDATE SET
                    instrument=excluded.instrument,
                    direction=excluded.direction,
                    entry_type=excluded.entry_type,
                    stop_loss=excluded.stop_loss,
                    take_profit=excluded.take_profit,
                    requested_risk_pct=excluded.requested_risk_pct,
                    parser_confidence=excluded.parser_confidence,
                    signal_age=excluded.signal_age,
                    risk_status=excluded.risk_status,
                    execution_status=excluded.execution_status,
                    outcome_status=excluded.outcome_status,
                    rejection_reasons=excluded.rejection_reasons,
                    updated_at=excluded.updated_at
                """,
                (
                    signal_id,
                    payload.get("source") or "private_signal",
                    payload.get("instrument") or payload.get("symbol"),
                    payload.get("direction"),
                    payload.get("entry_type"),
                    self._float_or_none(payload.get("stop_loss")),
                    self._float_or_none(payload.get("take_profit")),
                    self._float_or_none(payload.get("requested_risk_pct")),
                    self._float_or_none(payload.get("parser_confidence")),
                    self._float_or_none(payload.get("signal_age")),
                    utc.tm_wday,
                    utc.tm_hour,
                    now,
                    "REJECTED" if status == "REJECTED" else "ACCEPTED",
                    "REJECTED" if status == "REJECTED" else "PENDING",
                    outcome,
                    json.dumps(reasons),
                    now,
                ),
            )

    def record_rejection(self, signal_id: Optional[str], reasons: Iterable[str], stage: str) -> None:
        if not signal_id:
            return
        self._ensure_signal(signal_id)
        reasons_json = json.dumps(list(reasons))
        if stage == "risk":
            updates = "risk_status='REJECTED'"
        else:
            updates = "execution_status='REJECTED'"
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE provider_setups
                SET {updates},
                    outcome_status='REJECTED',
                    rejection_reasons=?,
                    updated_at=?
                WHERE signal_id=?
                """,
                (reasons_json, time.time(), signal_id),
            )

    def record_fill(self, payload: Dict[str, Any]) -> None:
        signal_id = self._signal_id(payload)
        if not signal_id:
            return
        self._ensure_signal(signal_id)
        fill_price = self._float_or_none(payload.get("fill_price"))
        stop_loss = self._float_or_none(payload.get("stop_loss"))
        take_profit = self._float_or_none(payload.get("take_profit"))
        rr = self._risk_reward_ratio(
            payload.get("direction"), fill_price, stop_loss, take_profit
        )
        risk_amount = self._float_or_none(
            payload.get("actual_risk_usd") or payload.get("risk_amount_usd")
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE provider_setups
                SET entry_price=?,
                    stop_loss=COALESCE(?, stop_loss),
                    take_profit=COALESCE(?, take_profit),
                    spread_bps=?,
                    risk_amount_usd=?,
                    risk_reward_ratio=?,
                    risk_status='APPROVED',
                    execution_status='FILLED',
                    outcome_status='OPEN',
                    updated_at=?
                WHERE signal_id=?
                """,
                (
                    fill_price,
                    stop_loss,
                    take_profit,
                    self._float_or_none(payload.get("spread_bps")),
                    risk_amount,
                    rr,
                    time.time(),
                    signal_id,
                ),
            )

    def record_close(self, signal_id: Optional[str], payload: Dict[str, Any]) -> None:
        if not signal_id:
            return
        self._ensure_signal(signal_id)
        pnl = self._float_or_none(payload.get("pnl"))
        risk_amount = self._stored_risk_amount(signal_id)
        pnl_r = pnl / risk_amount if pnl is not None and risk_amount and risk_amount > 0 else None
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE provider_setups
                SET outcome_status='CLOSED',
                    pnl=?,
                    pnl_r=?,
                    updated_at=?
                WHERE signal_id=?
                """,
                (pnl, pnl_r, time.time(), signal_id),
            )

    def summary(self, *, recent_limit: int = 25) -> dict:
        with self._connect() as conn:
            totals = self._row_to_dict(
                conn.execute(
                    """
                    SELECT
                        COUNT(*) AS tracked_setups,
                        SUM(CASE WHEN execution_status='FILLED' THEN 1 ELSE 0 END) AS filled_setups,
                        SUM(CASE WHEN outcome_status='CLOSED' THEN 1 ELSE 0 END) AS closed_setups,
                        SUM(CASE WHEN outcome_status='REJECTED' THEN 1 ELSE 0 END) AS rejected_setups,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS winning_setups,
                        AVG(pnl) AS avg_pnl,
                        AVG(pnl_r) AS avg_pnl_r
                    FROM provider_setups
                    """
                ).fetchone()
            )
            by_symbol = [
                self._stat_row(row)
                for row in conn.execute(
                    """
                    SELECT
                        instrument, direction,
                        COUNT(*) AS sample_size,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                        AVG(pnl) AS avg_pnl,
                        AVG(pnl_r) AS avg_pnl_r,
                        AVG(risk_reward_ratio) AS avg_risk_reward_ratio
                    FROM provider_setups
                    WHERE outcome_status='CLOSED'
                    GROUP BY instrument, direction
                    ORDER BY sample_size DESC, instrument ASC
                    """
                ).fetchall()
            ]
            by_hour = [
                self._stat_row(row)
                for row in conn.execute(
                    """
                    SELECT
                        instrument, direction, hour_utc,
                        COUNT(*) AS sample_size,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                        AVG(pnl) AS avg_pnl,
                        AVG(pnl_r) AS avg_pnl_r,
                        AVG(risk_reward_ratio) AS avg_risk_reward_ratio
                    FROM provider_setups
                    WHERE outcome_status='CLOSED'
                    GROUP BY instrument, direction, hour_utc
                    ORDER BY sample_size DESC, instrument ASC
                    LIMIT 20
                    """
                ).fetchall()
            ]
            recent = [
                self._setup_row(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM provider_setups
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(recent_limit), 250)),),
                ).fetchall()
            ]

        closed_count = int(totals.get("closed_setups") or 0)
        return {
            "learning_mode": "observation_only",
            "automation_sample_threshold": MIN_AUTOMATION_SAMPLE_SIZE,
            "automation_ready": closed_count >= MIN_AUTOMATION_SAMPLE_SIZE,
            "recommendation": self._recommendation(closed_count),
            "totals": self._rounded_totals(totals),
            "by_symbol_direction": by_symbol,
            "by_symbol_direction_hour": by_hour,
            "recent_setups": recent,
            "timestamp": time.time(),
        }

    def _ensure_signal(self, signal_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO provider_setups (signal_id, updated_at)
                VALUES (?, ?)
                """,
                (signal_id, time.time()),
            )

    def _stored_risk_amount(self, signal_id: str) -> Optional[float]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT risk_amount_usd FROM provider_setups WHERE signal_id=?",
                (signal_id,),
            ).fetchone()
        if not row:
            return None
        return self._float_or_none(row["risk_amount_usd"])

    def _recommendation(self, closed_count: int) -> str:
        if closed_count < MIN_AUTOMATION_SAMPLE_SIZE:
            remaining = MIN_AUTOMATION_SAMPLE_SIZE - closed_count
            return (
                f"Collect {remaining} more closed provider trades before allowing "
                "the learning agent to affect sizing or trade filters."
            )
        return "Enough closed samples exist for review; require manual approval before changing sizing."

    def _stat_row(self, row: sqlite3.Row) -> dict:
        data = self._row_to_dict(row)
        sample_size = int(data.get("sample_size") or 0)
        wins = int(data.get("wins") or 0)
        data["win_rate_pct"] = round((wins / sample_size) * 100, 2) if sample_size else 0.0
        for key in ("avg_pnl", "avg_pnl_r", "avg_risk_reward_ratio"):
            data[key] = self._round_or_none(data.get(key))
        return data

    def _setup_row(self, row: sqlite3.Row) -> dict:
        data = self._row_to_dict(row)
        data["rejection_reasons"] = self._loads(data.get("rejection_reasons"))
        for key in (
            "stop_loss",
            "take_profit",
            "requested_risk_pct",
            "parser_confidence",
            "signal_age",
            "entry_price",
            "spread_bps",
            "risk_amount_usd",
            "risk_reward_ratio",
            "pnl",
            "pnl_r",
        ):
            data[key] = self._round_or_none(data.get(key))
        return data

    def _rounded_totals(self, totals: dict) -> dict:
        rounded = dict(totals)
        for key in (
            "tracked_setups",
            "filled_setups",
            "closed_setups",
            "rejected_setups",
            "winning_setups",
        ):
            rounded[key] = int(rounded.get(key) or 0)
        for key in ("avg_pnl", "avg_pnl_r"):
            rounded[key] = self._round_or_none(rounded.get(key))
        closed = rounded["closed_setups"]
        wins = rounded["winning_setups"]
        rounded["win_rate_pct"] = round((wins / closed) * 100, 2) if closed else 0.0
        return rounded

    def _risk_reward_ratio(
        self,
        direction: Any,
        entry_price: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
    ) -> Optional[float]:
        if entry_price is None or stop_loss is None or take_profit is None:
            return None
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        if risk <= 0:
            return None
        if str(direction).upper() == "BUY" and not (stop_loss < entry_price < take_profit):
            return None
        if str(direction).upper() == "SELL" and not (take_profit < entry_price < stop_loss):
            return None
        return reward / risk

    def _signal_id(self, payload: Dict[str, Any]) -> Optional[str]:
        value = payload.get("signal_id") or payload.get("source_signal_id")
        if not value:
            original = payload.get("original_request") or {}
            value = original.get("signal_id") or original.get("source_signal_id")
        return str(value) if value else None

    def _row_to_dict(self, row: Optional[sqlite3.Row]) -> dict:
        if row is None:
            return {}
        return {key: row[key] for key in row.keys()}

    def _loads(self, value: Any) -> list:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return [str(value)]
        return parsed if isinstance(parsed, list) else [parsed]

    def _float_or_none(self, value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed

    def _round_or_none(self, value: Any, digits: int = 4) -> Optional[float]:
        parsed = self._float_or_none(value)
        return round(parsed, digits) if parsed is not None else None
