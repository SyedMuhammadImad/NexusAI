import pytest

from services.image_signal_service import ImageSignalService
from services.image_signal_store import ImageSignalStore
from services.signal_parser import SignalParser


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
)


class FakeVisionClient:
    async def extract_trade_signal(self, image_bytes, mime_type):
        return {
            "symbol": "EUR USD",
            "direction": "BUY",
            "entry_type": "MARKET",
            "entry_price": None,
            "stop_loss": 1.1584,
            "take_profit": 1.16,
            "raw_text": "EUR USD Buy on current rate Stoploss: 1.15840 Take profit: 1.16000",
            "confidence": 0.94,
        }


@pytest.mark.asyncio
async def test_image_signal_service_parses_and_stores_execution_upload(tmp_path):
    service = ImageSignalService(
        vision_client=FakeVisionClient(),
        store=ImageSignalStore(db_path=str(tmp_path / "images.sqlite3")),
        parser=SignalParser(),
        symbol_resolver=lambda symbol: "EURUSDm" if symbol == "EURUSD" else symbol,
        image_dir=tmp_path / "images",
    )

    result = await service.parse_upload(
        image_bytes=PNG_1X1,
        filename="signal.png",
        content_type="image/png",
    )

    assert result["status"] == "PARSED"
    assert result["accepted_for_submission"] is True
    assert result["signal"]["instrument"] == "EURUSDm"
    assert result["signal"]["direction"] == "BUY"
    assert result["signal"]["stop_loss"] == 1.1584
    assert result["signal"]["take_profit_1"] == 1.16

    stored = service.stored_payload_for_submission(result["image_id"])
    assert "BUY EURUSD" in stored["text"]
    assert "SL 1.1584" in stored["text"]


@pytest.mark.asyncio
async def test_image_signal_service_rejects_unsupported_upload(tmp_path):
    service = ImageSignalService(
        vision_client=FakeVisionClient(),
        store=ImageSignalStore(db_path=str(tmp_path / "images.sqlite3")),
        image_dir=tmp_path / "images",
    )

    with pytest.raises(ValueError, match="unsupported image type"):
        await service.parse_upload(
            image_bytes=b"not an image",
            filename="signal.txt",
            content_type="text/plain",
        )
