import csv
import time
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

    def _headers(self, *, reports: bool = False, processing_mode: str = "auto") -> dict[str, str]:
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
                    "processingMode": processing_mode,
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
        date_range_type: str = "CUSTOM_DATE",
        goal_ids: list[str] | None = None,
        processing_mode: str = "auto",
        max_wait_seconds: int = 20,
    ) -> list[dict[str, str]]:
        if not self.is_configured:
            return []

        date_range_type = date_range_type.upper()
        selection_criteria: dict[str, str] = {}
        report_period = date_range_type
        if date_range_type == "CUSTOM_DATE":
            if date_to is None:
                date_to = datetime.now(UTC).date()
            if date_from is None:
                date_from = date_to - timedelta(days=days - 1)
            selection_criteria = {"DateFrom": date_from.isoformat(), "DateTo": date_to.isoformat()}
            report_period = f"{date_from.isoformat()} {date_to.isoformat()}"

        payload = _build_campaign_report_payload(
            selection_criteria=selection_criteria,
            report_period=report_period,
            date_range_type=date_range_type,
            limit=limit,
            goal_ids=goal_ids,
        )
        rows = self._request_report_with_retries(
            payload=payload,
            processing_mode=processing_mode.lower(),
            max_wait_seconds=max_wait_seconds,
        )
        if goal_ids:
            total_payload = _build_campaign_report_payload(
                selection_criteria=selection_criteria,
                report_period=f"{report_period} totals",
                date_range_type=date_range_type,
                limit=limit,
                goal_ids=None,
            )
            total_rows = self._request_report_with_retries(
                payload=total_payload,
                processing_mode=processing_mode.lower(),
                max_wait_seconds=max_wait_seconds,
            )
            rows = _merge_total_conversion_fallback(rows, total_rows)
        return rows

    def get_search_query_report(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        days: int = 30,
        limit: int = 1000,
        date_range_type: str = "CUSTOM_DATE",
        goal_ids: list[str] | None = None,
        processing_mode: str = "offline",
        max_wait_seconds: int = 20,
    ) -> list[dict[str, str]]:
        if not self.is_configured:
            return []

        date_range_type = date_range_type.upper()
        selection_criteria: dict[str, str] = {}
        report_period = date_range_type
        if date_range_type == "CUSTOM_DATE":
            if date_to is None:
                date_to = datetime.now(UTC).date()
            if date_from is None:
                date_from = date_to - timedelta(days=days - 1)
            selection_criteria = {"DateFrom": date_from.isoformat(), "DateTo": date_to.isoformat()}
            report_period = f"{date_from.isoformat()} {date_to.isoformat()}"

        payload = _build_search_query_report_payload(
            selection_criteria=selection_criteria,
            report_period=report_period,
            date_range_type=date_range_type,
            limit=limit,
            goal_ids=goal_ids,
        )
        rows = self._request_report_with_retries(
            payload=payload,
            processing_mode=processing_mode.lower(),
            max_wait_seconds=max_wait_seconds,
        )
        if goal_ids:
            total_payload = _build_search_query_report_payload(
                selection_criteria=selection_criteria,
                report_period=f"{report_period} totals",
                date_range_type=date_range_type,
                limit=limit,
                goal_ids=None,
            )
            total_rows = self._request_report_with_retries(
                payload=total_payload,
                processing_mode=processing_mode.lower(),
                max_wait_seconds=max_wait_seconds,
            )
            rows = _merge_total_conversion_fallback_by_keys(rows, total_rows, ["CampaignId", "AdGroupId", "Query"])
        return rows

    def _request_report_with_retries(
        self,
        *,
        payload: dict[str, Any],
        processing_mode: str,
        max_wait_seconds: int,
    ) -> list[dict[str, str]]:
        started_at = time.monotonic()
        while True:
            response = httpx.post(
                self.reports_url,
                json=payload,
                headers=self._headers(reports=True, processing_mode=processing_mode),
                timeout=60,
            )
            if response.status_code == 200:
                return _parse_tsv_report(response.text)
            if response.status_code in {201, 202}:
                retry_in = _retry_in_seconds(response)
                elapsed = time.monotonic() - started_at
                if elapsed + retry_in > max_wait_seconds:
                    raise RuntimeError(
                        "Yandex Direct report is being generated offline. "
                        f"Repeat the same request later. Retry after {retry_in} seconds."
                    )
                time.sleep(retry_in)
                continue
            if response.status_code >= 400:
                raise RuntimeError(_format_direct_error(response))
            response.raise_for_status()


def _normalize_goal_ids(goal_ids: list[str] | None) -> list[int | str]:
    normalized: list[int | str] = []
    for item in goal_ids or []:
        value = str(item).strip()
        if not value:
            continue
        normalized.append(int(value) if value.isdigit() else value)
    return normalized


def _build_campaign_report_payload(
    *,
    selection_criteria: dict[str, str],
    report_period: str,
    date_range_type: str,
    limit: int,
    goal_ids: list[str] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "SelectionCriteria": selection_criteria,
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
        "ReportName": f"DirectPilot Campaign Report {report_period}",
        "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
        "DateRangeType": date_range_type,
        "Format": "TSV",
        "IncludeVAT": "YES",
        "IncludeDiscount": "YES",
        "Page": {"Limit": limit},
    }
    normalized_goals = _normalize_goal_ids(goal_ids)
    if normalized_goals:
        params["Goals"] = normalized_goals
    return {"params": params}


def _build_search_query_report_payload(
    *,
    selection_criteria: dict[str, str],
    report_period: str,
    date_range_type: str,
    limit: int,
    goal_ids: list[str] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "SelectionCriteria": selection_criteria,
        "FieldNames": [
            "CampaignId",
            "CampaignName",
            "AdGroupId",
            "AdGroupName",
            "Query",
            "Impressions",
            "Clicks",
            "Cost",
            "Ctr",
            "AvgCpc",
            "Conversions",
            "CostPerConversion",
            "ConversionRate",
        ],
        "OrderBy": [{"Field": "Cost", "SortOrder": "DESCENDING"}],
        "ReportName": f"DirectPilot Search Query Report {report_period}",
        "ReportType": "SEARCH_QUERY_PERFORMANCE_REPORT",
        "DateRangeType": date_range_type,
        "Format": "TSV",
        "IncludeVAT": "YES",
        "IncludeDiscount": "YES",
        "Page": {"Limit": limit},
    }
    normalized_goals = _normalize_goal_ids(goal_ids)
    if normalized_goals:
        params["Goals"] = normalized_goals
    return {"params": params}


def _merge_total_conversion_fallback(goal_rows: list[dict[str, str]], total_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return _merge_total_conversion_fallback_by_keys(goal_rows, total_rows, ["CampaignId"])


def _merge_total_conversion_fallback_by_keys(
    goal_rows: list[dict[str, str]],
    total_rows: list[dict[str, str]],
    keys: list[str],
) -> list[dict[str, str]]:
    def row_key(item: dict[str, str]) -> tuple[str, ...]:
        return tuple(str(item.get(key) or "") for key in keys)

    totals_by_key = {row_key(item): item for item in total_rows}
    merged: list[dict[str, str]] = []
    for row in goal_rows:
        total = totals_by_key.get(row_key(row), {})
        merged.append(
            {
                **row,
                "_TotalConversions": total.get("Conversions", row.get("_TotalConversions", "")),
                "_TotalCostPerConversion": total.get("CostPerConversion", row.get("_TotalCostPerConversion", "")),
                "_TotalConversionRate": total.get("ConversionRate", row.get("_TotalConversionRate", "")),
            }
        )
    return merged


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


def _format_direct_error(response: httpx.Response) -> str:
    request_id = response.headers.get("RequestId") or response.headers.get("requestId") or response.headers.get("X-Request-Id")
    detail = response.text.strip()
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error") or payload
        if isinstance(error, dict):
            detail = (
                error.get("error_detail")
                or error.get("error_string")
                or error.get("error_description")
                or error.get("message")
                or str(error)
            )
        else:
            detail = str(error)
    suffix = f" RequestId: {request_id}." if request_id else ""
    return f"Yandex Direct API returned {response.status_code}: {detail}.{suffix}"


def _retry_in_seconds(response: httpx.Response) -> int:
    try:
        return max(1, min(int(response.headers.get("retryIn", "5")), 10))
    except ValueError:
        return 5
