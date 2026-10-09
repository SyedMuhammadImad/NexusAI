"""Image signal parsing service for execution-upload workflow."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from services.deepseek_vision_client import DeepSeekVisionClient, DeepSeekVisionError
from services.image_signal_store import ImageSignalStore
from services.signal_parser import ParsedTradeSignal, SignalParser


SUPPORTED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_IMAGE_BYTES = 32 * 1024 * 1024
DEFAULT_IMAGE_DIR = Path(__file__).resolve().parents[1] / "data" / "private_signal_images"


class ImageSignalService:
    def __init__(
        self,
        *,
        vision_client: Optional[DeepSeekVisionClient] = None,
        store: Optional[ImageSignalStore] = None,
        parser: Optional[SignalParser] = None,
        symbol_resolver: Optional[Callable[[str], str]] = None,
        image_dir: Optional[str | Path] = None,
    ):
        self.vision_client = vision_client or DeepSeekVisionClient()
        self.store = store or ImageSignalStore()
        self.parser = parser or SignalParser()
        self.symbol_resolver = symbol_resolver or (lambda symbol: symbol)
        self.image_dir = Path(image_dir or DEFAULT_IMAGE_DIR)
        self.image_dir.mkdir(parents=True, exist_ok=True)

    async def parse_upload(
        self,
        *,
        image_bytes: bytes,
        filename: str,
        content_type: Optional[str],
        source: str = "ui_execution_upload",
    ) -> dict:
        mime_type = self._detect_mime_type(image_bytes, content_type)
        self._validate_image(image_bytes, mime_type)
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        existing = self.store.get_by_hash(image_hash)
        image_id = existing.get("image_id") if existing else str(uuid.uuid4())
        image_path = self.image_dir / f"{image_hash}{SUPPORTED_MIME_TYPES[mime_type]}"
        if not image_path.exists():
            image_path.write_bytes(image_bytes)

        extracted = await self.vision_client.extract_trade_signal(image_bytes, mime_type)
        normalized_text = self._normalized_text(extracted)
        signal = self.parser.parse(
            message_id=f"image-{image_hash[:16]}",
            group_id="ui-image-upload",
            sender_id="dashboard-user",
            text=normalized_text,
            message_timestamp=time.time(),
            received_timestamp=time.time(),
        )
        if signal.instrument:
            signal.instrument = self.symbol_resolver(signal.instrument)
        reasons = self._basic_rejection_reasons(signal, extracted)
        status = "PARSED" if not reasons else "REJECTED"
        signal.validation_status = status
        signal.rejection_reasons = reasons

        raw_text = str(extracted.get("raw_text") or normalized_text)
        self.store.upsert_parse_result(
            image_id=image_id,
            image_hash=image_hash,
            image_path=str(image_path),
            mime_type=mime_type,
            source=source,
            raw_extracted_text=raw_text,
            extracted_json=extracted,
            normalized_text=normalized_text,
            parsed_signal=signal.to_dict(include_raw=False),
            status=status,
            rejection_reasons=reasons,
        )
        return self._public_parse_result(
            image_id=image_id,
            image_hash=image_hash,
            status=status,
            signal=signal,
            raw_text=raw_text,
            normalized_text=normalized_text,
            extracted=extracted,
            rejection_reasons=reasons,
            filename=filename,
        )

    def stored_payload_for_submission(self, image_id: str) -> dict:
        record = self.store.get(image_id)
        if not record:
            raise KeyError("image signal not found")
        if record.get("status") not in {"PARSED", "SUBMIT_FAILED"}:
            raise ValueError(f"image signal status is {record.get('status')}; only PARSED can be submitted")
        normalized_text = record.get("normalized_text")
        if not normalized_text:
            raise ValueError("image signal has no normalized text")
        return {
            "message_id": f"ui-image-{image_id}",
            "text": normalized_text,
            "raw_record": record,
        }

    def mark_submitted(self, image_id: str, result: Dict[str, Any]) -> None:
        status = "SUBMITTED" if result.get("accepted") else "SUBMIT_FAILED"
        self.store.update_submit_result(image_id, result, status)

    def recent(self, limit: int = 25) -> list[dict]:
        rows = self.store.recent(limit=limit)
        public = []
        for row in rows:
            public.append(
                {
                    "image_id": row.get("image_id"),
                    "image_hash": row.get("image_hash"),
                    "source": row.get("source"),
                    "status": row.get("status"),
                    "parsed_signal": row.get("parsed_signal_json") or {},
                    "rejection_reasons": row.get("rejection_reasons_json") or [],
                    "submitted_at": row.get("submitted_at"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                }
            )
        return public

    def _detect_mime_type(self, image_bytes: bytes, content_type: Optional[str]) -> str:
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return "image/webp"
        if image_bytes.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        clean_type = str(content_type or "").split(";")[0].strip().lower()
        if clean_type in SUPPORTED_MIME_TYPES:
            return clean_type
        return "application/octet-stream"

    def _validate_image(self, image_bytes: bytes, mime_type: str) -> None:
        if not image_bytes:
            raise ValueError("empty image upload")
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("image exceeds 32 MiB limit")
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise ValueError("unsupported image type; upload JPEG, PNG, WebP, or GIF")

    def _normalized_text(self, extracted: Dict[str, Any]) -> str:
        symbol = self._clean_symbol(extracted.get("symbol"))
        direction = str(extracted.get("direction") or "").upper()
        entry_type = str(extracted.get("entry_type") or "MARKET").upper()
        stop_loss = self._number_or_none(extracted.get("stop_loss"))
        take_profit = self._number_or_none(extracted.get("take_profit"))
        entry_price = self._number_or_none(extracted.get("entry_price"))

        parts = [direction, symbol]
        if entry_type == "MARKET":
            parts.append("market")
        elif entry_price is not None:
            parts.extend(["entry", self._format_number(entry_price)])
        if stop_loss is not None:
            parts.extend(["SL", self._format_number(stop_loss)])
        if take_profit is not None:
            parts.extend(["TP", self._format_number(take_profit)])
        return " ".join(part for part in parts if part).strip()

    def _basic_rejection_reasons(
        self,
        signal: ParsedTradeSignal,
        extracted: Dict[str, Any],
    ) -> list[str]:
        reasons = []
        if not signal.instrument:
            reasons.append("missing instrument")
        if signal.direction not in {"BUY", "SELL"}:
            reasons.append("direction must be BUY or SELL")
        if signal.entry_type != "MARKET":
            reasons.append("only MARKET/current-rate screenshots are supported for execution upload")
        if signal.stop_loss is None:
            reasons.append("missing stop loss")
        if signal.primary_take_profit is None:
            reasons.append("missing take profit")
        confidence = self._number_or_none(extracted.get("confidence"))
        if confidence is not None and confidence < 0.70:
            reasons.append(f"vision confidence {confidence:.2f} < 0.70")
        return reasons

    def _public_parse_result(
        self,
        *,
        image_id: str,
        image_hash: str,
        status: str,
        signal: ParsedTradeSignal,
        raw_text: str,
        normalized_text: str,
        extracted: Dict[str, Any],
        rejection_reasons: list[str],
        filename: str,
    ) -> dict:
        return {
            "image_id": image_id,
            "image_hash": image_hash,
            "filename": filename,
            "status": status,
            "accepted_for_submission": status == "PARSED",
            "signal": signal.to_dict(include_raw=False),
            "raw_text": raw_text,
            "normalized_text": normalized_text,
            "vision_confidence": self._number_or_none(extracted.get("confidence")),
            "rejection_reasons": rejection_reasons,
        }

    def _clean_symbol(self, value: Any) -> str:
        raw = re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()
        if raw == "GOLD":
            return "XAUUSD"
        if raw == "WTI":
            return "USOIL"
        return raw

    def _number_or_none(self, value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed

    def _format_number(self, value: float) -> str:
        return f"{value:.8f}".rstrip("0").rstrip(".")
