import pytest
from fastapi import HTTPException

from core import database
from core.database import get_event_history, init_db, save_event


def test_retired_control_access_rejects_development_without_token(monkeypatch):
    import legacy_application as main

    monkeypatch.setattr(main, "APP_ENV", "development")
    monkeypatch.setattr(main, "CONTROL_TOKEN", "")

    with pytest.raises(HTTPException):
        main.require_control_access(x_control_token="")


def test_control_access_requires_matching_token_in_production(monkeypatch):
    import legacy_application as main

    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "CONTROL_TOKEN", "secret")

    with pytest.raises(HTTPException) as exc:
        main.require_control_access(x_control_token="wrong")
    assert exc.value.status_code == 403

    main.require_control_access(x_control_token="secret")


@pytest.mark.asyncio
async def test_event_audit_persists_and_loads_events(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "trading.db")

    await init_db()
    await save_event("order.filled", "execution_agent", {"symbol": "BTC-USD"})

    events = await get_event_history(limit=10)

    assert len(events) == 1
    assert events[0]["event_type"] == "order.filled"
    assert events[0]["source"] == "execution_agent"
    assert events[0]["payload"] == {"symbol": "BTC-USD"}
