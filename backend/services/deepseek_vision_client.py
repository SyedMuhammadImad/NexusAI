"""DeepSeek vision client for extracting trade signals from screenshots."""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Dict, Optional

import httpx


class DeepSeekVisionError(RuntimeError):
    pass


class DeepSeekVisionClient:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-v4-flash-vision-exp")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def extract_trade_signal(self, image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        if not self.configured:
            raise DeepSeekVisionError("DEEPSEEK_API_KEY is not configured")
        if not image_bytes:
            raise DeepSeekVisionError("empty image")

        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract one forex/commodity trade signal from this screenshot. "
                                "Return only JSON with keys: symbol, direction, entry_type, "
                                "entry_price, stop_loss, take_profit, raw_text, confidence. "
                                "Use BUY or SELL for direction. Use MARKET when the signal says "
                                "current rate/current price/current. Use null for missing numbers. "
                                "Do not add commentary."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise DeepSeekVisionError(f"DeepSeek vision request failed: HTTP {response.status_code}")

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise DeepSeekVisionError("DeepSeek response did not contain message content") from exc
        return self._parse_json_content(content)

    def _parse_json_content(self, content: Any) -> Dict[str, Any]:
        if not isinstance(content, str):
            raise DeepSeekVisionError("DeepSeek content was not text")
        cleaned = content.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            cleaned = fenced.group(1)
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start : end + 1]
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise DeepSeekVisionError("DeepSeek response was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise DeepSeekVisionError("DeepSeek JSON response must be an object")
        return parsed
