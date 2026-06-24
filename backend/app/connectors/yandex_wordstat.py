from datetime import date, datetime, time, timezone
from typing import Any

import httpx


class YandexWordstatConnector:
    """Read-only connector for Yandex Search API Wordstat methods."""

    dynamics_url = "https://searchapi.api.cloud.yandex.net/v2/wordstat/dynamics"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        access_token: str | None = None,
        folder_id: str | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self.folder_id = folder_id
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key or self.access_token)

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            auth_header = f"Api-Key {self.api_key}"
        elif self.access_token:
            auth_header = f"Bearer {self.access_token}"
        else:
            raise RuntimeError("Yandex Wordstat/Search API credentials are not configured")
        return {
            "Authorization": auth_header,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }

    def get_dynamics(
        self,
        *,
        phrase: str,
        period: str,
        from_date: date,
        to_date: date,
        regions: list[str] | None = None,
        devices: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.is_configured:
            raise RuntimeError("Yandex Wordstat/Search API credentials are not configured")

        api_from_date, api_to_date = _normalize_api_date_range(period=period, from_date=from_date, to_date=to_date)
        payload: dict[str, Any] = {
            "phrase": phrase,
            "period": period,
            "fromDate": _date_start_rfc3339(api_from_date),
            "toDate": _date_end_rfc3339(api_to_date),
            "regions": regions or [],
            "devices": devices or ["DEVICE_ALL"],
        }
        if self.folder_id:
            payload["folderId"] = self.folder_id

        response = httpx.post(self.dynamics_url, json=payload, headers=self._headers(), timeout=self.timeout_seconds)
        if response.status_code == 200:
            body = response.json()
            return list(body.get("results") or [])

        raise RuntimeError(_wordstat_error_message(response))


def _normalize_api_date_range(*, period: str, from_date: date, to_date: date) -> tuple[date, date]:
    """Yandex Wordstat requires monthly ranges to start from the first day of a month."""

    if period == "PERIOD_MONTHLY":
        from_date = from_date.replace(day=1)
        to_date = to_date.replace(day=1)
    return from_date, to_date


def _date_start_rfc3339(value: date) -> str:
    return datetime.combine(value, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _date_end_rfc3339(value: date) -> str:
    return datetime.combine(value, time.max.replace(microsecond=0), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _wordstat_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = response.text
    if isinstance(body, dict):
        message = body.get("message") or body.get("error") or body.get("detail") or body
    else:
        message = body
    return f"Yandex Wordstat API request failed with HTTP {response.status_code}: {message}"
