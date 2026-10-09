"""Local historical chat archive. No broker, event bus or execution dependencies."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sqlite3
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path, PurePosixPath

from services.signal_parser import SignalParser
from services.trader_learning_store import TraderLearningStore

MAX_UPLOAD = 100 * 1024 * 1024
MAX_TEXT = 5 * 1024 * 1024
HEADER = re.compile(r"^\[?(\d{1,2}[/.]\d{1,2}[/.]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\]?\s*(?:-\s*)?(.*)$", re.I)
ATTACHMENT = re.compile(r"<attached:\s*([^>]+)>")


def parse_transcript(text: str, date_order: str, utc_offset: int) -> list[dict]:
    if date_order not in {"DMY", "MDY"} or not -720 <= utc_offset <= 840:
        raise ValueError("Choose DMY or MDY and a UTC offset between -720 and 840 minutes.")
    messages = []
    for raw_line in text.splitlines():
        line = raw_line.replace("\u200e", "").replace("\u200f", "").replace("\u202f", " ").replace("\xa0", " ")
        match = HEADER.match(line)
        if not match:
            if messages:
                messages[-1]["text"] += "\n" + line
                messages[-1]["raw_record"] += "\n" + raw_line
                messages[-1]["raw_body"] += "\n" + raw_line
            continue
        date, clock, body = match.groups()
        parts = re.split(r"[/.]", date)
        first, second, year = map(int, parts)
        year = year + 2000 if year < 100 else year
        day, month = (first, second) if date_order == "DMY" else (second, first)
        clock = clock.strip().upper()
        fmt = "%I:%M:%S %p" if re.search(r"[AP]M$", clock) else "%H:%M:%S"
        if clock.count(":") == 1:
            fmt = fmt.replace(":%S", "")
        try:
            parsed_clock = datetime.strptime(clock, fmt)
            timestamp = datetime(year, month, day, parsed_clock.hour, parsed_clock.minute, parsed_clock.second,
                                 tzinfo=timezone(timedelta(minutes=utc_offset))).timestamp()
        except ValueError as exc:
            raise ValueError(f"Invalid chat timestamp: {date}, {clock}. Check date order.") from exc
        sender, sep, body_text = body.partition(": ")
        raw_match = HEADER.match(raw_line.lstrip("\u200e\u200f"))
        raw_parts = re.split(r":(?: |\u00a0)", raw_match[3], maxsplit=1) if raw_match else []
        messages.append({"timestamp": timestamp, "local_time": f"{date}, {clock}",
                         "sender": sender if sep else "System", "text": body_text if sep else body,
                         "raw_record": raw_line,
                         "original_timestamp": f"{raw_match[1]}, {raw_match[2]}" if raw_match else None,
                         "raw_sender": raw_parts[0] if len(raw_parts) == 2 else "System",
                         "raw_evidence_parsed": bool(raw_match and (not sep or len(raw_parts) == 2)),
                         "raw_body": raw_parts[-1] if raw_parts else raw_line})
    if not messages:
        raise ValueError("No timestamped WhatsApp messages found in the text file.")
    return messages


def historical_parser_text(raw: str) -> str:
    raw = raw.replace("\u200e", "").replace("\u200f", "").replace("\u202f", " ").replace("\xa0", " ")
    text = ATTACHMENT.sub("", raw).replace("*", "").strip()
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    text = re.sub(r"\bshortsell\b", "SELL", text, flags=re.I)
    text = re.sub(r"\bcrude\s+oil\b", "USOIL", text, flags=re.I)
    text = re.sub(r"\bcurrent\s+price\b", "current rate", text, flags=re.I)
    return text


def classify(message: dict, group: str) -> dict:
    raw = message["text"]
    text = historical_parser_text(raw)
    parsed = SignalParser().parse(message_id=message["id"], group_id=group, sender_id=message["sender"],
                                  text=text, message_timestamp=message["timestamp"], received_timestamp=message["timestamp"])
    if re.search(r"\b(?:SILVER|XAG\s*USD)\b", text, re.I) and not parsed.instrument:
        parsed.instrument = "XAGUSD"
    signal = parsed.to_dict()
    reasons = []
    kind = "discussion"
    if re.search(r"\b(?:cancel|ignore|do not take)\b", text, re.I):
        kind = "cancellation"
    elif re.search(r"\b(?:bring|move|trail|change|update|set)\b.*\b(?:stop\s*loss|SL|TP|take profit)\b|\b(?:close|exit|book)\b", text, re.I | re.S):
        kind = "update"
    elif re.search(r"\b(?:hit|profitable|booked|profit\s+on|loss\s+on|target\s+achieved)\b", text, re.I) and not (parsed.direction in {"BUY", "SELL"} and parsed.stop_loss and parsed.primary_take_profit):
        kind = "reported_result"
    if parsed.instrument and parsed.direction in {"BUY", "SELL"} and kind == "discussion":
        kind = "signal"
        for key, label in (("entry_price", "Historical entry price"), ("stop_loss", "Stop loss"), ("take_profit_1", "Take profit")):
            if not signal.get(key) or not math.isfinite(signal[key]) or signal[key] <= 0:
                reasons.append(f"{label} missing or invalid")
        if not reasons:
            entry, sl, tp = signal["entry_price"], signal["stop_loss"], signal["take_profit_1"]
            if not (sl < entry < tp if parsed.direction == "BUY" else tp < entry < sl):
                reasons.append("Entry, stop loss and target conflict with the direction")
        if re.search(r"\d\.\s+\d|\d+\.\d+,\d", text):
            reasons.append("Ambiguous number formatting")
        if re.search(r"\bBUY\b", text, re.I) and re.search(r"\bSELL\b", text, re.I):
            reasons.append("Multiple trade directions")
        covered = {"MISSING_OR_INVALID_PRICE", "INVALID_LEVEL_GEOMETRY"}
        reasons.extend("Parser: " + reason for reason in parsed.rejection_reasons if reason not in covered)
    elif ATTACHMENT.search(raw) and kind == "discussion":
        kind = "media"
    return {**message, "kind": kind, "signal": signal if kind == "signal" else None,
            "symbol": parsed.instrument, "reasons": reasons,
            "review_status": ("needs_review" if reasons else "ready") if kind == "signal" else "context",
            "attachments": ATTACHMENT.findall(raw), "candidate_ids": [], "outcome_verified": False}


def parser_differences(row: dict, group: str) -> dict:
    if row.get("kind") != "signal":
        return {}
    old = row.get("signal") or {}
    new = classify(row, group).get("signal") or {}
    differences = {key: {"stored": old.get(key), "reparsed": new.get(key)}
            for key in ("entry_price", "stop_loss", "take_profit_1", "take_profit_2", "take_profit_3")
            if old.get(key) != new.get(key)}
    new_reasons = sorted(set(new.get("rejection_reasons", [])) - set(old.get("rejection_reasons", [])))
    if new_reasons:
        differences["additional_validation_reasons"] = {"stored": [], "reparsed": new_reasons}
    return differences


class ChatImportService:
    def __init__(self, root: Path | None = None, learning_store: TraderLearningStore | None = None):
        self.root = root or Path(__file__).resolve().parents[1] / "data" / "chat_imports"
        self.root.mkdir(parents=True, exist_ok=True)
        self.learning_store = learning_store
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, filename TEXT, created REAL, metadata TEXT, archive BLOB);
                CREATE TABLE IF NOT EXISTS messages (id TEXT, import_id TEXT, ordinal INTEGER, payload TEXT,
                    PRIMARY KEY(import_id, id));
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.root / "archive.sqlite3", timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def import_file(self, content: bytes, filename: str, date_order=None, utc_offset=None, group="REDACTED_SOURCE") -> dict:
        time_confirmed = date_order is not None and utc_offset is not None
        # Preserve legacy review behavior, but never treat its defaults as UTC evidence.
        date_order = "DMY" if date_order is None else date_order
        utc_offset = 300 if utc_offset is None else utc_offset
        if len(content) > MAX_UPLOAD:
            raise ValueError("Archive exceeds the 100 MB upload limit.")
        group = group.strip()
        if not group or len(group) > 120:
            raise ValueError("Group name must contain 1 to 120 characters.")
        archive = content
        media = []
        if filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    entries = zf.infolist()
                    if len(entries) > 10000 or sum(e.file_size for e in entries) > 300 * 1024 * 1024:
                        raise ValueError("Expanded archive is too large.")
                    for entry in entries:
                        path = PurePosixPath(entry.filename.replace("\\", "/"))
                        if path.is_absolute() or ".." in path.parts or ":" in entry.filename or entry.flag_bits & 1:
                            raise ValueError("Unsafe or encrypted archive entry.")
                    texts = [e for e in entries if e.filename.lower().endswith(".txt") and not e.filename.startswith("__MACOSX/")]
                    if len(texts) != 1 or texts[0].file_size > MAX_TEXT:
                        raise ValueError("Archive must contain exactly one chat .txt file, up to 5 MB.")
                    text_bytes = zf.read(texts[0])
                    media = [e.filename for e in entries if e.filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and e.file_size <= 15 * 1024 * 1024]
                    if len({PurePosixPath(n).name for n in media}) != len(media):
                        raise ValueError("Archive has ambiguous duplicate image filenames.")
                    archive = content
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                raise ValueError("Invalid or unsupported ZIP archive.") from exc
        elif filename.lower().endswith(".txt") and len(content) <= MAX_TEXT:
            text_bytes = content
        else:
            raise ValueError("Upload a .zip export or UTF-8 .txt file (text limit 5 MB).")
        try:
            text = text_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Chat text must use UTF-8 encoding.") from exc
        import_id = hashlib.sha256(content + f"{date_order}:{utc_offset}:{group}:{time_confirmed}".encode()).hexdigest()
        transcript = text.replace("\r\n", "\n").replace("\r", "\n")
        fingerprint = hashlib.sha256(transcript.encode()).hexdigest()
        with self.connect() as conn:
            existing = conn.execute("SELECT metadata FROM imports WHERE id=?", (import_id,)).fetchone()
            if not existing:
                legacy_id = hashlib.sha256(content + f"{date_order}:{utc_offset}:{group}".encode()).hexdigest()
                existing = conn.execute("SELECT metadata FROM imports WHERE id=?", (legacy_id,)).fetchone()
        if existing and json.loads(existing[0]).get("parser_version") == 3:
            return {**json.loads(existing[0]), "duplicate": True}
        messages = parse_transcript(text, date_order, utc_offset)
        if len(messages) > 20000:
            raise ValueError("Import limit is 20,000 messages per archive.")
        rows, occurrences, prior = [], {}, []
        for message in messages:
            identity_content = [group, message["original_timestamp"], message["raw_sender"], message["raw_body"]]
            base = json.dumps(identity_content, ensure_ascii=False)
            occurrence = occurrences.get(base, 0)
            occurrences[base] = occurrence + 1
            message["historical_message_id"] = hashlib.sha256(json.dumps(
                ["historical-message.v1", *identity_content, occurrence], ensure_ascii=False).encode()).hexdigest()
            message["id"] = message["historical_message_id"]
            message["identity_content"] = identity_content
            message["occurrence"] = occurrence
            row = classify(message, group)
            row["available_media"] = [name for name in media if PurePosixPath(name).name in row["attachments"]]
            if row["attachments"] and len(row["available_media"]) < len(row["attachments"]):
                row["reasons"].append("One or more attached files are unavailable")
                if row["kind"] == "signal":
                    row["review_status"] = "needs_review"
            if row["kind"] in {"update", "reported_result", "cancellation"}:
                candidates = list(islice((p["id"] for p in reversed(prior) if p["sender"] == row["sender"]
                    and 0 <= row["timestamp"] - p["timestamp"] <= 86400
                    and (not row["symbol"] or p["symbol"] == row["symbol"])), 21))
                row["candidate_ids"] = candidates[:20]
                row["candidate_links_truncated"] = len(candidates) > 20
            if row["kind"] == "signal":
                prior.append(row)
            rows.append(row)
        counts = {kind: sum(r["kind"] == kind for r in rows) for kind in ("signal", "update", "reported_result", "cancellation", "media", "discussion")}
        metadata = {"id": import_id, "filename": Path(filename).name, "group": group, "date_order": date_order,
                    "utc_offset": utc_offset, "messages": len(rows), "duplicates_removed": len(messages) - len(rows),
                    "images": len(media), "counts": counts, "created": time.time(),
                    "ready": sum(r["review_status"] == "ready" for r in rows),
                    "needs_review": sum(r["review_status"] == "needs_review" for r in rows), "execution_enabled": False, "parser_version": 3,
                    "archive_hash": hashlib.sha256(content).hexdigest(), "transcript_fingerprint": fingerprint,
                    "identity_version": "historical-message.v1", "transcript_normalization": "utf8-bom-newlines.v1",
                    "time_evidence_confirmed": time_confirmed, "container_format": "zip" if filename.lower().endswith(".zip") else "txt"}
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT metadata FROM imports WHERE id=?", (import_id,)).fetchone()
            if existing:
                return {**json.loads(existing[0]), "duplicate": True}
            duplicate = conn.execute("SELECT id FROM imports WHERE json_extract(metadata,'$.transcript_fingerprint')=? AND json_extract(metadata,'$.group')=? ORDER BY created,id LIMIT 1", (fingerprint, group)).fetchone()
            metadata["duplicate_of"] = duplicate[0] if duplicate else None
            conn.execute("INSERT INTO imports VALUES (?, ?, ?, ?, ?)", (import_id, metadata["filename"], metadata["created"], json.dumps(metadata), archive))
            for i, row in enumerate(rows):
                saved = conn.execute("SELECT payload FROM messages WHERE import_id=? AND id=?", (import_id, row["id"])).fetchone()
                if saved and (json.loads(saved[0])["review_status"] == "approved" or json.loads(saved[0]).get("review_history")):
                    continue
                conn.execute("INSERT INTO messages VALUES (?, ?, ?, ?) ON CONFLICT(import_id,id) DO UPDATE SET payload=excluded.payload",
                             (row["id"], import_id, i, json.dumps(row)))
        return metadata

    def historical_record(self, import_id: str, message_id: str):
        with self.connect() as conn:
            conn.execute("BEGIN")
            imported = conn.execute("SELECT metadata FROM imports WHERE id=?", (import_id,)).fetchone()
            message = conn.execute("SELECT payload FROM messages WHERE import_id=? AND id=?", (import_id, message_id)).fetchone()
            if not imported or not message:
                raise KeyError("Import or message not found")
            return json.loads(imported[0]), json.loads(message[0])

    def list_imports(self):
        with self.connect() as conn:
            return [json.loads(r[0]) for r in conn.execute("SELECT metadata FROM imports ORDER BY created DESC LIMIT 100")]

    def messages(self, import_id: str, kind="all", search="", offset=0, limit=100):
        with self.connect() as conn:
            imported = conn.execute("SELECT metadata FROM imports WHERE id=?", (import_id,)).fetchone()
            if not imported:
                raise KeyError("Import not found")
            rows = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM messages WHERE import_id=? ORDER BY ordinal", (import_id,))]
        group = json.loads(imported[0])["group"]
        for row in rows:
            differences = parser_differences(row, group)
            row["parser_differences"] = differences
            row["parser_review_required"] = bool(differences)
        rows = [r for r in rows if (kind == "all" or r["kind"] == kind or r["review_status"] == kind)
                and search.casefold() in (r["text"] + r["sender"]).casefold()]
        return {"messages": rows[offset:offset + limit], "total": len(rows), "execution_enabled": False}

    def approve(self, import_id: str, message_id: str):
        if self.learning_store is None:
            raise ValueError("Learning store unavailable")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stored = conn.execute("SELECT payload FROM messages WHERE import_id=? AND id=?", (import_id, message_id)).fetchone()
            if not stored:
                raise KeyError("Message not found")
            row = json.loads(stored[0])
            if row["review_status"] not in {"ready", "approved"}:
                raise ValueError("Only complete, consistent signals can be approved for learning.")
            imported = conn.execute("SELECT metadata FROM imports WHERE id=?", (import_id,)).fetchone()
            if not row.get("review_history") and row["review_status"] != "approved" and parser_differences(row, json.loads(imported[0])["group"]):
                raise ValueError("Parser changes require explicit price review and a correction note")
            signal_id = "chat-" + message_id
            prior_approval = conn.execute("SELECT payload FROM messages WHERE id=? AND json_extract(payload, '$.review_status')='approved' LIMIT 1", (message_id,)).fetchone()
            if prior_approval:
                approved = json.loads(prior_approval[0])
                row.update(signal=approved["signal"], review_history=approved.get("review_history", []), review_status="approved", reasons=[])
                conn.execute("UPDATE messages SET payload=? WHERE import_id=? AND id=?", (json.dumps(row), import_id, message_id))
                return {"status": "approved", "signal_id": signal_id, "message": row, "execution_enabled": False}
            signal = {**row["signal"], "signal_id": signal_id, "validation_status": "IMPORTED",
                      "entry_provenance": row.get("entry_provenance")}
            self.learning_store.record_signal(signal_id=signal_id, source="historical_chat_reviewed", message_id=message_id,
                raw_message=row["text"], parsed_signal=signal, market_snapshot={}, validation_status="IMPORTED", rejection_reasons=[])
            self.learning_store.record_status(signal_id, execution_status="NOT_APPLICABLE", outcome_status="UNVERIFIED")
            row["review_status"] = "approved"
            conn.execute("UPDATE messages SET payload=? WHERE import_id=? AND id=?", (json.dumps(row), import_id, message_id))
        return {"status": "approved", "signal_id": signal_id, "message": row, "execution_enabled": False}

    def correct(self, import_id: str, message_id: str, fields: dict):
        """Keep manual source corrections separate from the original transcript."""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stored = conn.execute("SELECT payload FROM messages WHERE import_id=? AND id=?", (import_id, message_id)).fetchone()
            if not stored:
                raise KeyError("Message not found")
            row = json.loads(stored[0])
            if row["kind"] != "signal" or row["review_status"] == "approved":
                raise ValueError("Corrections are available for unapproved signal candidates only.")
            note = str(fields.get("note", "")).strip()
            if not 5 <= len(note) <= 1000:
                raise ValueError("Add a source note of 5 to 1000 characters for the correction.")
            revised = dict(row["signal"])
            for key in ("entry_price", "stop_loss", "take_profit_1"):
                try:
                    value = float(fields[key])
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError("Entry, stop loss and take profit must be numbers.") from exc
                if not math.isfinite(value) or value <= 0:
                    raise ValueError("Trade prices must be positive, finite numbers.")
                revised[key] = value
            if not (revised["stop_loss"] < revised["entry_price"] < revised["take_profit_1"] if revised["direction"] == "BUY"
                    else revised["take_profit_1"] < revised["entry_price"] < revised["stop_loss"]):
                raise ValueError("Entry, stop loss and target conflict with the direction.")
            row.setdefault("review_history", []).append({"timestamp": time.time(), "note": note, "previous_signal": row["signal"], "previous_reasons": row["reasons"]})
            row.update(signal=revised, reasons=[], review_status="ready")
            conn.execute("UPDATE messages SET payload=? WHERE import_id=? AND id=?", (json.dumps(row), import_id, message_id))
        return row

    def media(self, import_id: str, name: str):
        with self.connect() as conn:
            row = conn.execute("SELECT archive FROM imports WHERE id=?", (import_id,)).fetchone()
        if not row or not row[0] or not zipfile.is_zipfile(io.BytesIO(row[0])):
            raise KeyError("Image not found")
        if PurePosixPath(name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise KeyError("Image not found")
        with zipfile.ZipFile(io.BytesIO(row[0])) as zf:
            info = zf.getinfo(name)
            if info.file_size > 15 * 1024 * 1024:
                raise ValueError("Image exceeds size limit")
            return zf.read(info)
