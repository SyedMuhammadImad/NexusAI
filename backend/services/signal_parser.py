"""
Deterministic trade-signal parser.

This parser intentionally does not use an LLM. Missing trade fields are left
empty so downstream validation can reject or hold the signal safely.
"""

from __future__ import annotations

import re
import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


NUMBER = r"([+-]?[0-9]+(?:\.[0-9]+)?)(?![\w.,])"
SYMBOL_RE = re.compile(
    r"\b(EUR\s*USDm?|GBP\s*USDm?|USD\s*JPYm?|XAU\s*USDm?|GOLD|BTC\s*USDm?|ETH\s*USDm?|US\s*OILm?|WTI)\b",
    re.IGNORECASE,
)
DIRECTION_RE = re.compile(r"\b(BUY|LONG|SELL|SHORT|EXIT|CLOSE)\b", re.IGNORECASE)
P2_SYMBOL_RE = re.compile(SYMBOL_RE.pattern.replace("XAU", "XAG\\s*USDm?|XAU"), re.IGNORECASE)
SL_RE = re.compile(
    rf"\b(?:SL|STOP\s*LOSS)\s*[:=@]?\s*{NUMBER}\b",
    re.IGNORECASE,
)
TP_RE = re.compile(
    rf"\b(?:TP|TAKE\s*PROFIT)([123](?=\s|[:=@]))?\s*[:=@]?\s*{NUMBER}",
    re.IGNORECASE,
)
ENTRY_RE = re.compile(
    rf"\b(?:ENTRY|ENTER|AT|CURRENT\s+RATE|RATE|CMP|@)\s*[:=@]?\s*{NUMBER}\b",
    re.IGNORECASE,
)
MARKET_ENTRY_RE = re.compile(r"\b(MARKET|NOW|CMP|CURRENT\s+RATE)\b", re.IGNORECASE)
RANGE_RE = re.compile(rf"\b{NUMBER}\s*[-–]\s*{NUMBER}\b")
RISK_RE = re.compile(rf"\bRISK\s*[:=@]?\s*{NUMBER}\s*%?\b", re.IGNORECASE)
PARSER_VERSION = "deterministic_v3"
FIELD_LABEL_RE = re.compile(
    r"\b(?:TP\d*|TAKE\s*PROFIT\d*|SL|STOP\s*LOSS|ENTRY|ENTER|(?:AT\s+)?CURRENT\s+RATE|RATE|CMP|AT)\b|@",
    re.IGNORECASE,
)
FIELD_VALUE_RE = re.compile(r"\s*[:=@]?\s*([+-]?[0-9]+(?:\.[0-9]+)?)(?=\s|$|[;!?])")


@dataclass
class ParsedTradeSignal:
    signal_id: str
    message_id: str
    group_id: str
    sender_id: str
    message_timestamp: float
    received_timestamp: float
    raw_message: str
    instrument: Optional[str] = None
    direction: Optional[str] = None
    entry_type: Optional[str] = None
    entry_price: Optional[float] = None
    entry_range: Optional[Tuple[float, float]] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    requested_risk_pct: Optional[float] = None
    parser_confidence: float = 0.0
    parser_version: str = PARSER_VERSION
    validation_status: str = "PENDING"
    rejection_reasons: List[str] = field(default_factory=list)

    @property
    def signal_age(self) -> float:
        return max(0.0, self.received_timestamp - self.message_timestamp)

    @property
    def primary_take_profit(self) -> Optional[float]:
        return self.take_profit_1 or self.take_profit_2 or self.take_profit_3

    def to_dict(self, include_raw: bool = False) -> dict:
        data = {
            "signal_id": self.signal_id,
            "message_id": self.message_id,
            "group_id": self.group_id,
            "sender_id": self.sender_id,
            "message_timestamp": self.message_timestamp,
            "received_timestamp": self.received_timestamp,
            "instrument": self.instrument,
            "direction": self.direction,
            "entry_type": self.entry_type,
            "entry_price": self.entry_price,
            "entry_range": list(self.entry_range) if self.entry_range else None,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "take_profit_3": self.take_profit_3,
            "requested_risk_pct": self.requested_risk_pct,
            "parser_confidence": round(self.parser_confidence, 4),
            "parser_version": self.parser_version,
            "signal_age": round(self.signal_age, 3),
            "validation_status": self.validation_status,
            "rejection_reasons": self.rejection_reasons,
        }
        if include_raw:
            data["raw_message"] = self.raw_message
        return data


class SignalParser:
    def parse(
        self,
        *,
        message_id: str,
        group_id: str,
        sender_id: str,
        text: str,
        message_timestamp: Optional[float] = None,
        received_timestamp: Optional[float] = None,
        p2: bool = False,
    ) -> ParsedTradeSignal:
        received = time.time() if received_timestamp is None else received_timestamp
        message_time = received if message_timestamp is None else message_timestamp
        raw = text or ""
        if len(raw) > 16000:
            raise ValueError("Signal text exceeds 16000 characters")
        identity = json.dumps([group_id, sender_id, message_id, message_timestamp, raw], ensure_ascii=True)
        signal = ParsedTradeSignal(
            signal_id=hashlib.sha256(identity.encode()).hexdigest(),
            message_id=message_id,
            group_id=group_id,
            sender_id=sender_id,
            message_timestamp=float(message_time),
            received_timestamp=float(received),
            raw_message=raw,
        )

        symbol = (P2_SYMBOL_RE if p2 else SYMBOL_RE).search(raw)
        if symbol:
            signal.instrument = self._normalize_symbol(symbol.group(1))

        direction = DIRECTION_RE.search(raw)
        if direction:
            signal.direction = self._normalize_direction(direction.group(1))

        entry = ENTRY_RE.search(raw)
        if entry:
            entry_label = entry.group(0).upper()
            signal.entry_type = "MARKET" if "CURRENT" in entry_label or "RATE" in entry_label or "CMP" in entry_label else "LIMIT"
            signal.entry_price = float(entry.group(1))
        elif MARKET_ENTRY_RE.search(raw):
            signal.entry_type = "MARKET"

        entry_range = RANGE_RE.search(raw)
        if entry_range and not signal.entry_price:
            low = float(entry_range.group(1))
            high = float(entry_range.group(2))
            signal.entry_type = "RANGE"
            signal.entry_range = (min(low, high), max(low, high))

        sl = SL_RE.search(raw)
        if sl:
            signal.stop_loss = float(sl.group(1))

        for match in TP_RE.finditer(raw):
            slot = match.group(1) or "1"
            value = float(match.group(2))
            if slot == "1":
                signal.take_profit_1 = value
            elif slot == "2":
                signal.take_profit_2 = value
            elif slot == "3":
                signal.take_profit_3 = value

        risk = RISK_RE.search(raw)
        if risk:
            signal.requested_risk_pct = float(risk.group(1))

        signal.parser_confidence = self._confidence(signal)
        signal.rejection_reasons = self.validate(signal, p2=p2)
        if p2:
            signal.parser_version = "deterministic_v3_p2"
        if message_timestamp is None:
            signal.rejection_reasons.append("MISSING_ORIGIN_TIMESTAMP")
        signal.validation_status = "REVIEW_REQUIRED" if signal.rejection_reasons else "VALID"
        return signal

    @staticmethod
    def validate(signal: ParsedTradeSignal, *, p2=False) -> list[str]:
        reasons = []
        if not signal.instrument:
            reasons.append("UNSUPPORTED_OR_MISSING_SYMBOL")
        symbols = {SignalParser()._normalize_symbol(x) for x in (P2_SYMBOL_RE if p2 else SYMBOL_RE).findall(signal.raw_message)}
        if len(symbols) > 1:
            reasons.append("AMBIGUOUS_SYMBOL")
        directions = {SignalParser()._normalize_direction(x) for x in DIRECTION_RE.findall(signal.raw_message)}
        if signal.direction not in {"BUY", "SELL"} or len(directions) != 1:
            reasons.append("INVALID_OR_AMBIGUOUS_DIRECTION")
        prices = (signal.entry_price, signal.stop_loss, signal.primary_take_profit)
        missing_market = p2 and signal.entry_type == "MARKET" and signal.entry_price is None
        if missing_market:
            if any(p is None or not math.isfinite(p) or p <= 0 for p in prices[1:]):
                reasons.append("MISSING_OR_INVALID_PRICE")
            elif not (signal.stop_loss < signal.primary_take_profit if signal.direction == "BUY" else signal.primary_take_profit < signal.stop_loss):
                reasons.append("INVALID_LEVEL_GEOMETRY")
        elif any(p is None or not math.isfinite(p) or p <= 0 for p in prices):
            reasons.append("MISSING_OR_INVALID_PRICE")
        else:
            entry, sl, tp = prices
            targets = [x for x in (signal.take_profit_1, signal.take_profit_2, signal.take_profit_3) if x is not None]
            if any(not math.isfinite(t) or t <= 0 or not (sl < entry < t if signal.direction == "BUY" else t < entry < sl) for t in targets):
                reasons.append("INVALID_LEVEL_GEOMETRY")
        if any(not math.isfinite(t) or t <= 0 for t in (signal.message_timestamp, signal.received_timestamp)) or signal.message_timestamp > signal.received_timestamp:
            reasons.append("INVALID_TIMESTAMP")
        if len(SL_RE.findall(signal.raw_message)) > 1 or len(ENTRY_RE.findall(signal.raw_message)) > 1:
            reasons.append("AMBIGUOUS_FIELDS")
        slots = [m.group(1) or "1" for m in TP_RE.finditer(signal.raw_message)]
        if len(slots) != len(set(slots)):
            reasons.append("DUPLICATE_TP_SLOT")
        labels = list(FIELD_LABEL_RE.finditer(signal.raw_message))
        for index, label in enumerate(labels):
            name = re.sub(r"\s+", "", label.group().upper())
            if name.startswith(("TP", "TAKEPROFIT")) and re.search(r"\d", name) and not re.search(r"(?<!\d)[123]$", name):
                reasons.append("UNSUPPORTED_TP_SLOT")
            end = labels[index + 1].start() if index + 1 < len(labels) else len(signal.raw_message)
            fragment = signal.raw_message[label.end():end]
            value = FIELD_VALUE_RE.match(fragment)
            if not value or len(value.group(1)) > 40:
                reasons.append("MALFORMED_FIELD")
                continue
            tail = fragment[value.end():].lstrip()
            if re.match(r"[+\-.,/0-9]", tail):
                reasons.append("AMBIGUOUS_NUMBER_FORMAT")
        if re.search(r"\b(?:cancel|ignore|do\s+not|don't)\b", signal.raw_message, re.I):
            reasons.append("NON_ACTIONABLE_TEXT")
        if signal.entry_range is not None:
            reasons.append("UNSUPPORTED_ENTRY_RANGE")
        if signal.requested_risk_pct is not None and (not math.isfinite(signal.requested_risk_pct) or not 0 < signal.requested_risk_pct <= 100):
            reasons.append("INVALID_REQUESTED_RISK")
        if len(re.findall(r"\bRISK\b", signal.raw_message, re.I)) != len(RISK_RE.findall(signal.raw_message)):
            reasons.append("MALFORMED_REQUESTED_RISK")
        return list(dict.fromkeys(reasons))

    def _normalize_symbol(self, symbol: str) -> str:
        value = re.sub(r"\s+", "", symbol.upper())
        if value == "GOLD":
            return "XAUUSD"
        if value == "WTI":
            return "USOIL"
        if value.endswith("M"):
            return value[:-1] + "m"
        return value

    def _normalize_direction(self, direction: str) -> str:
        value = direction.upper()
        if value in {"LONG"}:
            return "BUY"
        if value in {"SHORT"}:
            return "SELL"
        if value == "CLOSE":
            return "EXIT"
        return value

    def _confidence(self, signal: ParsedTradeSignal) -> float:
        score = 0.0
        score += 0.25 if signal.instrument else 0.0
        score += 0.25 if signal.direction else 0.0
        score += 0.15 if signal.entry_type else 0.0
        score += 0.20 if signal.stop_loss is not None else 0.0
        score += 0.15 if signal.primary_take_profit is not None else 0.0
        return min(score, 1.0)
