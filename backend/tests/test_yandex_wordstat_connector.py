from datetime import date
from typing import Any

import httpx

from app.connectors.yandex_wordstat import YandexWordstatConnector


def test_wordstat_connector_normalizes_monthly_from_date(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, json, headers, timeout):
        captured["payload"] = json
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(httpx, "post", fake_post)

    connector = YandexWordstatConnector(api_key="test-api-key", folder_id="folder-id")
    connector.get_dynamics(
        phrase="купить диван",
        period="PERIOD_MONTHLY",
        from_date=date(2026, 6, 24),
        to_date=date(2026, 8, 18),
        regions=["225"],
        devices=["DEVICE_ALL"],
    )

    assert captured["payload"]["fromDate"] == "2026-06-01T00:00:00Z"
    assert captured["payload"]["toDate"] == "2026-08-01T23:59:59Z"


def test_wordstat_connector_keeps_daily_dates(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, json, headers, timeout):
        captured["payload"] = json
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(httpx, "post", fake_post)

    connector = YandexWordstatConnector(api_key="test-api-key")
    connector.get_dynamics(
        phrase="купить диван",
        period="PERIOD_DAILY",
        from_date=date(2026, 6, 24),
        to_date=date(2026, 6, 25),
        regions=[],
        devices=["DEVICE_ALL"],
    )

    assert captured["payload"]["fromDate"] == "2026-06-24T00:00:00Z"
    assert captured["payload"]["toDate"] == "2026-06-25T23:59:59Z"
