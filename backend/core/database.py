"""
Database — SQLite persistence using aiosqlite.

Stores:
  - trades: every filled order + P&L
  - agent_weights: orchestrator weights (survive restarts)
  - equity_curve: portfolio value snapshots
  - events: recent event log (last 5000)

SQLite is fine for paper trading. Migrate to TimescaleDB when you
have >1000 trades/day or need multi-process access.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "trading.db"


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id    TEXT UNIQUE,
                symbol      TEXT NOT NULL,
                direction   TEXT NOT NULL,
                entry_price REAL,
                exit_price  REAL,
                quantity    REAL,
                pnl         REAL DEFAULT 0,
                slippage_bps REAL DEFAULT 0,
                exit_reason TEXT,
                opened_at   REAL,
                closed_at   REAL,
                metadata    TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_weights (
                agent_id    TEXT PRIMARY KEY,
                weight      REAL NOT NULL,
                updated_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS equity_curve (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   REAL NOT NULL,
                equity      REAL NOT NULL,
                daily_pnl   REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                source      TEXT,
                payload     TEXT,
                timestamp   REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_closed ON trades(closed_at);
            CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_curve(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        """)
        await db.commit()
    logger.info(f"Database initialized: {DB_PATH}")


async def save_trade(trade: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO trades
            (order_id, symbol, direction, entry_price, exit_price,
             quantity, pnl, slippage_bps, exit_reason, opened_at, closed_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade.get("order_id"),
            trade.get("symbol"),
            trade.get("direction"),
            trade.get("entry_price"),
            trade.get("exit_price"),
            trade.get("quantity"),
            trade.get("pnl", 0),
            trade.get("slippage_bps", 0),
            trade.get("exit_reason"),
            trade.get("opened_at"),
            trade.get("closed_at", time.time()),
            json.dumps(trade.get("metadata", {})),
        ))
        await db.commit()


async def save_equity_snapshot(equity: float, daily_pnl: float = 0) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO equity_curve (timestamp, equity, daily_pnl) VALUES (?, ?, ?)",
            (time.time(), equity, daily_pnl)
        )
        await db.commit()


async def save_agent_weights(weights: Dict[str, float]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        for agent_id, weight in weights.items():
            await db.execute("""
                INSERT OR REPLACE INTO agent_weights (agent_id, weight, updated_at)
                VALUES (?, ?, ?)
            """, (agent_id, weight, time.time()))
        await db.commit()
    logger.debug(f"Agent weights persisted: {weights}")


async def load_agent_weights() -> Dict[str, float]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT agent_id, weight FROM agent_weights") as cur:
                rows = await cur.fetchall()
                weights = {row[0]: row[1] for row in rows}
                if weights:
                    logger.info(f"Loaded agent weights from DB: {weights}")
                return weights
    except Exception as e:
        logger.error(f"Failed to load agent weights: {e}")
        return {}


async def load_equity_curve(limit: int = 200) -> List[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT timestamp, equity, daily_pnl FROM equity_curve ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ) as cur:
                rows = await cur.fetchall()
                return [{"timestamp": r[0], "equity": r[1], "daily_pnl": r[2]} for r in reversed(rows)]
    except Exception:
        return []


async def get_trade_history(limit: int = 100, symbol: Optional[str] = None) -> List[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if symbol:
                async with db.execute(
                    "SELECT * FROM trades WHERE symbol=? ORDER BY closed_at DESC LIMIT ?",
                    (symbol, limit)
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute(
                    "SELECT * FROM trades ORDER BY closed_at DESC LIMIT ?", (limit,)
                ) as cur:
                    rows = await cur.fetchall()

            cols = ["id","order_id","symbol","direction","entry_price","exit_price",
                    "quantity","pnl","slippage_bps","exit_reason","opened_at","closed_at","metadata"]
            return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []


async def get_performance_stats() -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(pnl) as total_pnl,
                    AVG(pnl) as avg_pnl,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as gross_profit,
                    SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) as gross_loss,
                    MAX(pnl) as best_trade,
                    MIN(pnl) as worst_trade
                FROM trades WHERE closed_at IS NOT NULL
            """) as cur:
                row = await cur.fetchone()
                if not row or not row[0]:
                    return {"total_trades": 0}
                total, total_pnl, avg_pnl, wins, gp, gl, best, worst = row
                win_rate = (wins / total * 100) if total else 0
                pf = (gp / gl) if gl else 0
                return {
                    "total_trades": total,
                    "total_pnl": round(total_pnl or 0, 2),
                    "avg_pnl_per_trade": round(avg_pnl or 0, 2),
                    "win_rate_pct": round(win_rate, 1),
                    "profit_factor": round(pf, 2),
                    "best_trade": round(best or 0, 2),
                    "worst_trade": round(worst or 0, 2),
                }
    except Exception as e:
        logger.error(f"Stats query failed: {e}")
        return {}


async def save_event(event_type: str, source: str, payload: dict) -> None:
    """Save important events for audit trail."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO events (event_type, source, payload, timestamp) VALUES (?, ?, ?, ?)",
                (event_type, source, json.dumps(payload), time.time())
            )
            # Keep only last 5000 events
            await db.execute(
                "DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 5000)"
            )
            await db.commit()
    except Exception:
        pass  # Non-critical — don't let logging break trading


async def get_event_history(event_type: Optional[str] = None, limit: int = 100) -> List[dict]:
    """Load persisted audit events, newest first."""
    limit = max(1, min(int(limit), 1000))
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if event_type:
                async with db.execute(
                    """
                    SELECT id, event_type, source, payload, timestamp
                    FROM events
                    WHERE event_type = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (event_type, limit),
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute(
                    """
                    SELECT id, event_type, source, payload, timestamp
                    FROM events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ) as cur:
                    rows = await cur.fetchall()

        events = []
        for event_id, kind, source, payload, timestamp in rows:
            try:
                decoded_payload = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                decoded_payload = {"raw": payload}
            events.append({
                "id": event_id,
                "event_type": kind,
                "source": source,
                "payload": decoded_payload,
                "timestamp": timestamp,
            })
        return events
    except Exception as e:
        logger.error(f"Event history query failed: {e}")
        return []
