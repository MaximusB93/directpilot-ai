import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from typing import Any

import httpx


@dataclass(frozen=True)
class YandexDirectAccount:
    login: str | None = None
    agency_client_id: str | None = None


class YandexDirectConnector:
    """Read-only connector for Yandex Direct API v5."""

    campaigns_url = "https://api.direct.yandex.com/json/v5/campaigns"
    reports_url = "https://api.direct.yandex.com/json/v5/reports"

    def __init__(self, access_token: str | None = None, client_login: str | None = None) -> None:
        self.access_token = access_token
        self.client_login = client_login

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)

    def _headers(self, *, reports: bool = False) -> dict[str, str]:
        if not self.access_token:
            raise RuntimeError("Yandex Direct access token is not configured")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept-Language": "ru",
            "Content-Type": "application/json; charset=utf-8",
        }
        if reports:
            headers.update(
                {
                    "processingMode": "online",
                    "returnMoneyInMicros": "false",
                    "skipReportHeader": "true",
                    "skipReportSummary": "true",
                }
            )
        if self.client_login:
            headers["Client-Login"] = self.client_login
        return headers

    def list_campaigns(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []

        payload = {
            "method": "get",
            "params": {
                "SelectionCriteria": {},
                "FieldNames": ["Id", "Name", "Status", "Type", "State"],
                "Page": {"Limit": limit},
            },
        }
        response = httpx.post(self.campaigns_url, json=payload, headers=self._headers(), timeout=30)
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            error = body["error"]
            message = error.get("error_detail") or error.get("error_string") or error.get("error_code") or "Direct API error"
            raise RuntimeError(str(message))
        return body.get("result", {}).get("Campaigns", [])

    def get_campaign_report(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        days: int = 30,
        limit: int = 1000,
    ) -> list[dict[str, str]]:
        if not self.is_configured:
            return []

        if date_to is None:
            date_to = datetime.now(UTC).date()
        if date_from is None:
            date_from = date_to - timedelta(days=days - 1)

        payload = {
            "params": {
                "SelectionCriteria": {
                    "DateFrom": date_from.isoformat(),
                    "DateTo": date_to.isoformat(),
                },
                "FieldNames": [
                    "CampaignId",
                    "CampaignName",
                    "Impressions",
                    "Clicks",
                    "Cost",
                    "Ctr",
                    "AvgCpc",
                    "Conversions",
                    "CostPerConversion",
                    "ConversionRate",
                ],
                "OrderBy": [{"Field": "CampaignId"}],
                "ReportName": f"DirectPilot Campaign Report {date_from.isoformat()} {date_to.isoformat()}",
                "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
                "DateRangeType": "CUSTOM_DATE",
                "Format": "TSV",
                "IncludeVAT": "YES",
                "IncludeDiscount": "YES",
                "Page": {"Limit": limit},
            }
        }
        response = httpx.post(self.reports_url, json=payload, headers=self._headers(reports=True), timeout=60)
        if response.status_code in {201, 202}:
            retry_in = response.headers.get("retryIn")
            suffix = f" Retry after {retry_in} seconds." if retry_in else ""
            raise RuntimeError(f"Yandex Direct report is being generated offline.{suffix}")
        response.raise_for_status()
        return _parse_tsv_report(response.text)


def _parse_tsv_report(report_text: str) -> list[dict[str, str]]:
    stripped = report_text.strip()
    if not stripped:
        return []
    reader = csv.DictReader(StringIO(stripped), delimiter="\t")
    if reader.fieldnames is None:
        return []
    rows: list[dict[str, str]] = []
    for row in reader:
        if not row or row.get(reader.fieldnames[0], "").startswith("Total rows"):
            continue
        rows.append({key: value for key, value in row.items() if key is not None})
    return rows
