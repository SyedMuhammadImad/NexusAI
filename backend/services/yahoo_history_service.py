"""Historical reference prices for learning. This module never submits trades."""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import time
from pathlib import Path

import httpx

from services.chat_import_service import ChatImportService

SYMBOLS = {
    "EURUSD": ("EURUSD=X", False), "GBPUSD": ("GBPUSD=X", False),
    "USDJPY": ("JPY=X", False), "XAUUSD": ("GC=F", True),
    "XAGUSD": ("SI=F", True), "USOIL": ("CL=F", True),
    "BTCUSD": ("BTC-USD", False), "ETHUSD": ("ETH-USD", False),
}
INTERVAL_SECONDS = 300


def canonical_symbol(symbol):
    value = str(symbol or "").upper().replace("-", "").replace(" ", "")
    return value[:-1] if value.endswith("M") else value


def valid_geometry(signal):
    values = [signal.get(key) for key in ("entry_price", "stop_loss", "take_profit_1")]
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in values):
        return None
    entry, stop, target = values
    return stop < entry < target if signal.get("direction") == "BUY" else target < entry < stop


def completed_candle(candles, timestamp):
    """Use only a completed bar, never the later close of the containing bar."""
    times = [c["timestamp"] + INTERVAL_SECONDS for c in candles]
    index = bisect.bisect_right(times, timestamp) - 1
    if index < 0 or timestamp - times[index] >= INTERVAL_SECONDS:
        return None
    return candles[index]


class YahooHistoryService:
    def __init__(self, chat: ChatImportService, client=None):
        self.chat = chat
        self.client = client
        with chat.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS yahoo_candle_cache (cache_key TEXT PRIMARY KEY, payload TEXT);
                CREATE TABLE IF NOT EXISTS yahoo_enrichment_runs (import_id TEXT PRIMARY KEY, payload TEXT);
            """)

    def fetch(self, ticker, start, end):
        params = {"period1": int(start), "period2": int(end), "interval": "5m", "includePrePost": "true"}
        key = hashlib.sha256(json.dumps([ticker, params], sort_keys=True).encode()).hexdigest()
        with self.chat.connect() as conn:
            row = conn.execute("SELECT payload FROM yahoo_candle_cache WHERE cache_key=?", (key,)).fetchone()
        if row:
            return json.loads(row[0])
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        if self.client:
            response = self.client.get(url, params=params)
        else:
            with httpx.Client(timeout=25, headers={"User-Agent": "NexusAI historical research"}) as client:
                response = client.get(url, params=params)
        response.raise_for_status()
        chart = response.json().get("chart", {})
        if chart.get("error") or not chart.get("result"):
            raise ValueError("Yahoo returned no historical data for this range")
        result = chart["result"][0]
        meta = result.get("meta", {})
        if meta.get("symbol") != ticker or meta.get("dataGranularity") != "5m":
            raise ValueError("Yahoo symbol or candle interval did not match the request")
        quote = result["indicators"]["quote"][0]
        candles = []
        for index, timestamp in enumerate(result.get("timestamp", [])):
            candle = {"timestamp": timestamp}
            for key_name in ("open", "high", "low", "close", "volume"):
                series = quote.get(key_name) or []
                candle[key_name] = series[index] if index < len(series) else None
            prices = [candle[k] for k in ("open", "high", "low", "close")]
            if any(not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in prices):
                continue
            if not candle["low"] <= min(candle["open"], candle["close"]) <= max(candle["open"], candle["close"]) <= candle["high"]:
                continue
            if candle["volume"] is not None and (not math.isfinite(candle["volume"]) or candle["volume"] < 0):
                candle["volume"] = None
            candles.append(candle)
        candles.sort(key=lambda candle: candle["timestamp"])
        if not candles:
            raise ValueError("Yahoo returned no valid candles")
        data = {"ticker": ticker, "instrument_type": meta.get("instrumentType"), "currency": meta.get("currency"),
                "interval": "5m", "source": "Yahoo Finance", "url": str(response.url), "fetched_at": time.time(), "candles": candles}
        with self.chat.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO yahoo_candle_cache VALUES (?, ?)", (key, json.dumps(data, allow_nan=False)))
        return data

    def latest(self, import_id):
        with self.chat.connect() as conn:
            row = conn.execute("SELECT payload FROM yahoo_enrichment_runs WHERE import_id=?", (import_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def enrich(self, import_id):
        messages = self.chat.messages(import_id, kind="signal", limit=20000)["messages"]
        groups = {}
        for row in messages:
            mapping = SYMBOLS.get(canonical_symbol(row["symbol"]))
            if mapping:
                groups.setdefault(mapping[0], []).append(row)
        histories, errors = {}, {}
        for ticker, rows in groups.items():
            start = min(r["timestamp"] for r in rows) // 86400 * 86400 - 86400
            end = (max(r["timestamp"] for r in rows) // 86400 + 1) * 86400
            try:
                histories[ticker] = self.fetch(ticker, start, end)
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                errors[ticker] = f"Historical data unavailable ({type(exc).__name__})"
        results = []
        for row in messages:
            mapping = SYMBOLS.get(canonical_symbol(row["symbol"]))
            note = "Unsupported Yahoo symbol"
            reference = None
            if mapping:
                ticker, proxy = mapping
                history = histories.get(ticker)
                candle = completed_candle(history["candles"], row["timestamp"]) if history else None
                note = errors.get(ticker, "No completed candle within five minutes of the signal")
                if candle:
                    reference = {"source": "Yahoo Finance", "ticker": ticker, "is_proxy": proxy,
                        "instrument_type": history["instrument_type"], "interval": "5m", "candle": candle,
                        "candle_end": candle["timestamp"] + INTERVAL_SECONDS, "signal_timestamp": row["timestamp"],
                        "age_seconds": row["timestamp"] - candle["timestamp"] - INTERVAL_SECONDS,
                        "reference_entry": candle["close"], "method": "last_completed_candle_close",
                        "exact_fill": False, "fetched_at": history["fetched_at"]}
                    note = "Futures proxy only; cannot replace an Exness spot/CFD entry" if proxy else "Matched historical reference"
            with self.chat.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                fresh = conn.execute("SELECT payload FROM messages WHERE import_id=? AND id=?", (import_id, row["id"])).fetchone()
                current = json.loads(fresh[0])
                current["market_reference"] = reference
                current["enrichment_note"] = note
                # Preserve the original/corrected entry and all non-entry rejection reasons.
                if reference and not reference["is_proxy"] and not current["signal"].get("entry_price") and current["review_status"] != "approved":
                    proposed = {**current["signal"], "entry_price": reference["reference_entry"]}
                    if valid_geometry(proposed) is True:
                        current.setdefault("review_history", []).append({"timestamp": time.time(),
                            "note": "Yahoo last completed 5m candle close; estimated entry, not a broker fill",
                            "previous_signal": current["signal"], "previous_reasons": current["reasons"]})
                        current["signal"] = proposed
                        current["entry_provenance"] = reference
                        current["reasons"] = [reason for reason in current["reasons"] if reason != "Historical entry price missing or invalid"]
                        current["review_status"] = "needs_review" if current["reasons"] else "ready"
                        current["enrichment_note"] = "Entry estimated from the last completed Yahoo 5m candle"
                    else:
                        current["enrichment_note"] = "Yahoo reference conflicts with signal levels or levels are incomplete"
                conn.execute("UPDATE messages SET payload=? WHERE import_id=? AND id=?", (json.dumps(current, allow_nan=False), import_id, row["id"]))
                results.append({"message_id": row["id"], "symbol": row["symbol"], "time": row["local_time"],
                    "status": current["review_status"], "note": current["enrichment_note"],
                    "estimated_entry": current.get("entry_provenance", {}).get("reference_entry"),
                    "reference_entry": reference["reference_entry"] if reference else None, "is_proxy": reference["is_proxy"] if reference else None})
        report = {"import_id": import_id, "timestamp": time.time(), "execution_enabled": False,
                  "provider_errors": errors, "results": results, "matched": sum(r["reference_entry"] is not None for r in results),
                  "estimated_entries": sum(r["estimated_entry"] is not None for r in results),
                  "remaining_review": sum(r["status"] == "needs_review" for r in results)}
        with self.chat.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO yahoo_enrichment_runs VALUES (?, ?)", (import_id, json.dumps(report)))
        return report

    def prepare_training(self, import_id):
        if self.chat.learning_store is None:
            raise ValueError("Learning store unavailable")
        rows = self.chat.messages(import_id, kind="signal", limit=20000)["messages"]
        accepted = rejected = excluded = 0
        for row in rows:
            signal = row["signal"]
            geometry = valid_geometry(signal)
            provenance = row.get("entry_provenance")
            if geometry is True and row["review_status"] in {"ready", "approved"}:
                self.chat.approve(import_id, row["id"])
                accepted += 1
            elif geometry is False and not provenance and row["reasons"] == ["Entry, stop loss and target conflict with the direction"]:
                # A validation-rejected source example is not a losing trade label.
                signal_id = "chat-" + row["id"]
                self.chat.learning_store.record_signal(signal_id=signal_id, source="historical_chat_validation",
                    message_id=row["id"], raw_message=row["text"], parsed_signal=signal, market_snapshot={},
                    validation_status="REJECTED", rejection_reasons=row["reasons"])
                self.chat.learning_store.record_status(signal_id, execution_status="NOT_APPLICABLE", outcome_status="UNVERIFIED")
                rejected += 1
            else:
                excluded += 1
        return {"accepted": accepted, "validation_rejected": rejected, "excluded_unresolved": excluded,
                "target": "signal_validation_acceptance", "execution_enabled": False}
