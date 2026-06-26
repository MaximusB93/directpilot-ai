from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.models import ClientAccount
from app.services.connected_accounts import get_yandex_access_token_for_account
from app.services.openrouter import generate_openrouter_response
from app.services.yandex_metrika import parse_goal_ids

MAX_RANGE_DAYS = 31
DEFAULT_SEARCH_QUERY_LIMIT = 500


def _today() -> date:
    return datetime.now(UTC).date()


def _date_from_preset(preset: str) -> tuple[date, date, str]:
    end = _today() - timedelta(days=1)
    normalized = (preset or "yesterday").strip().lower()
    if normalized in {"yesterday", "1", "1d"}:
        return end, end, "yesterday"
    if normalized in {"7", "7d", "last7"}:
        return end - timedelta(days=6), end, "7d"
    if normalized in {"14", "14d", "last14"}:
        return end - timedelta(days=13), end, "14d"
    if normalized in {"30", "30d", "last30"}:
        return end - timedelta(days=29), end, "30d"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported period preset")


def resolve_period(*, preset: str = "yesterday", date_from: str | None = None, date_to: str | None = None) -> tuple[date, date, str]:
    if date_from or date_to:
        if not date_from or not date_to:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date_from and date_to must be provided together")
        try:
            start = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dates must use YYYY-MM-DD format") from exc
        label = "custom"
    else:
        start, end, label = _date_from_preset(preset)
    if end < start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date_to must be greater than or equal to date_from")
    if end >= _today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use only completed days. date_to must be yesterday or earlier")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Range is too long. Maximum is {MAX_RANGE_DAYS} days")
    return start, end, label


def _int(value: str | None) -> int:
    return int(float(value or 0)) if value not in {None, "", "--"} else 0


def _float(value: str | None) -> float:
    return float(value or 0) if value not in {None, "", "--"} else 0.0


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _direct_goal_conversion_value(row: dict[str, str], goal_ids: list[str]) -> float | None:
    normalized_goal_ids = {str(item).strip() for item in goal_ids if str(item).strip()}
    if not normalized_goal_ids:
        return _float(row.get("Conversions"))
    total = 0.0
    found = False
    for key, value in row.items():
        parts = key.split("_")
        if len(parts) < 2 or parts[0] != "Conversions" or parts[1] not in normalized_goal_ids:
            continue
        found = True
        total += _float(value)
    if found:
        return total
    if row.get("_TotalConversions") is not None and row.get("Conversions") not in {None, "", "--"}:
        return _float(row.get("Conversions"))
    return None


def _is_network_campaign(name: str) -> bool:
    normalized = (name or "").lower()
    return any(token in normalized for token in ["рся", "ретаргет", "интерес", "товарная", "мк", "смарт"])


def _issue_flags(*, campaign_name: str, cost: float, impressions: int, clicks: int, ctr: float, conversions: float | None, cpa: float | None, target_cpa: int | None) -> list[str]:
    used_conversions = conversions or 0
    flags: list[str] = []
    if impressions < 100 or clicks < 10:
        flags.append("low_data")
    if cost > 0 and used_conversions == 0 and clicks >= 10:
        flags.append("spend_without_conversions")
    if target_cpa and cpa is not None and cpa > target_cpa * 1.25:
        flags.append("high_cpa")
    if impressions >= 500 and ctr < 1.0:
        flags.append("low_ctr")
    if used_conversions > 0 and target_cpa and cpa is not None and cpa <= target_cpa:
        flags.append("promising_campaign")
    if _is_network_campaign(campaign_name) and "spend_without_conversions" in flags:
        flags.append("network_segment_check")
    return flags or ["ok"]


def _severity(flags: list[str]) -> str:
    if any(item in flags for item in ["spend_without_conversions", "high_cpa"]):
        return "critical"
    if any(item in flags for item in ["low_ctr", "network_segment_check"]):
        return "warning"
    if "promising_campaign" in flags:
        return "opportunity"
    if "low_data" in flags:
        return "info"
    return "ok"


def _drilldown(flags: list[str], campaign_name: str) -> dict[str, Any]:
    network = _is_network_campaign(campaign_name)
    if network:
        next_level = ["placements", "audiences", "retargeting_segments", "creatives", "devices", "geo", "goals"]
        needed = ["placement report", "audience/segment stats", "ad/creative stats", "device and geo breakdown", "goal tracking check"]
    else:
        next_level = ["query_report", "keywords", "ad_groups", "ads", "goals", "landing"]
        needed = ["search query report", "keyword stats", "ad group split", "ad relevance", "goal tracking check", "landing conversion path"]
    if "promising_campaign" in flags:
        next_level = ["lead_quality", "7_14_30_day_stability", "budget_dry_run", *next_level[:2]]
        needed = ["lead quality from CRM", "7/14/30 day trend", "incremental budget estimate", *needed[:2]]
    return {"nextLevel": next_level, "neededData": needed, "safeActions": ["manual_review", "dry_run_only"]}


def _aggregate_values(items: list[dict[str, Any]]) -> dict[str, Any]:
    cost = sum(float(item.get("cost") or 0) for item in items)
    impressions = sum(int(item.get("impressions") or 0) for item in items)
    clicks = sum(int(item.get("clicks") or 0) for item in items)
    conversions = sum(float(item.get("goalConversions") or 0) for item in items)
    return {
        "cost": _round(cost),
        "impressions": impressions,
        "clicks": clicks,
        "ctr": _round(clicks / impressions * 100) if impressions else 0.0,
        "avgCpc": _round(cost / clicks) if clicks else 0.0,
        "goalConversions": _round(conversions),
        "goalCpa": _round(cost / conversions) if conversions else None,
        "conversionRate": _round(conversions / clicks * 100) if clicks else 0.0,
    }


def _group_campaign_rows(rows: list[dict[str, str]], goal_ids: list[str], target_cpa: int | None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        campaign_id = str(row.get("CampaignId") or "")
        campaign_name = str(row.get("CampaignName") or "")
        key = campaign_id or campaign_name
        conversions = _direct_goal_conversion_value(row, goal_ids)
        grouped[key].append(
            {
                "date": row.get("Date"),
                "campaignId": campaign_id,
                "campaignName": campaign_name,
                "cost": _float(row.get("Cost")),
                "impressions": _int(row.get("Impressions")),
                "clicks": _int(row.get("Clicks")),
                "ctr": _float(row.get("Ctr")),
                "avgCpc": _float(row.get("AvgCpc")),
                "goalConversions": conversions,
            }
        )
    campaigns: list[dict[str, Any]] = []
    for key, items in grouped.items():
        totals = _aggregate_values(items)
        name = items[0].get("campaignName") or key
        flags = _issue_flags(
            campaign_name=name,
            cost=float(totals.get("cost") or 0),
            impressions=int(totals.get("impressions") or 0),
            clicks=int(totals.get("clicks") or 0),
            ctr=float(totals.get("ctr") or 0),
            conversions=totals.get("goalConversions"),
            cpa=totals.get("goalCpa"),
            target_cpa=target_cpa,
        )
        campaigns.append(
            {
                "campaignId": items[0].get("campaignId") or key,
                "campaignName": name,
                **totals,
                "issueFlags": flags,
                "severity": _severity(flags),
                "drilldown": _drilldown(flags, name),
            }
        )
    severity_rank = {"critical": 0, "warning": 1, "info": 2, "opportunity": 3, "ok": 4}
    return sorted(campaigns, key=lambda item: (severity_rank.get(item["severity"], 9), -(item.get("cost") or 0)))


def _group_daily(rows: list[dict[str, str]], goal_ids: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("Date") or "")].append(
            {
                "cost": _float(row.get("Cost")),
                "impressions": _int(row.get("Impressions")),
                "clicks": _int(row.get("Clicks")),
                "goalConversions": _direct_goal_conversion_value(row, goal_ids),
            }
        )
    return [{"date": key, **_aggregate_values(items)} for key, items in sorted(grouped.items())]


def _pct_delta(current: float | None, previous: float | None) -> float | None:
    current_value = float(current or 0)
    previous_value = float(previous or 0)
    if previous_value == 0:
        return 0.0 if current_value == 0 else None
    return _round((current_value - previous_value) / previous_value * 100)


def _split_previous_range(date_from: date, date_to: date) -> tuple[date, date]:
    days = (date_to - date_from).days + 1
    previous_to = date_from - timedelta(days=1)
    previous_from = previous_to - timedelta(days=days - 1)
    return previous_from, previous_to


def _changes(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "costDeltaPct": _pct_delta(current.get("cost"), previous.get("cost")),
        "clicksDeltaPct": _pct_delta(current.get("clicks"), previous.get("clicks")),
        "impressionsDeltaPct": _pct_delta(current.get("impressions"), previous.get("impressions")),
        "ctrDeltaPct": _pct_delta(current.get("ctr"), previous.get("ctr")),
        "avgCpcDeltaPct": _pct_delta(current.get("avgCpc"), previous.get("avgCpc")),
        "goalConversionsDeltaPct": _pct_delta(current.get("goalConversions"), previous.get("goalConversions")),
        "goalCpaDeltaPct": _pct_delta(current.get("goalCpa"), previous.get("goalCpa")),
    }


def _build_search_query_drilldown(rows: list[dict[str, str]], goal_ids: list[str], limit: int = 12) -> dict[str, Any]:
    insights = []
    for row in rows:
        conversions = _direct_goal_conversion_value(row, goal_ids)
        cost = _float(row.get("Cost"))
        clicks = _int(row.get("Clicks"))
        query = str(row.get("Query") or "")
        if not query:
            continue
        candidate = cost > 0 and clicks >= 3 and (conversions or 0) == 0
        insights.append(
            {
                "query": query,
                "campaign": row.get("CampaignName"),
                "adGroup": row.get("AdGroupName"),
                "cost": _round(cost),
                "clicks": clicks,
                "impressions": _int(row.get("Impressions")),
                "ctr": _float(row.get("Ctr")),
                "goalConversions": conversions,
                "candidateNegativeKeyword": query if candidate else None,
                "reason": "Расход и клики без конверсий по выбранным целям" if candidate else None,
            }
        )
    insights.sort(key=lambda item: (0 if item.get("candidateNegativeKeyword") else 1, -(item.get("cost") or 0)))
    return {
        "rows": len(rows),
        "candidateNegativeKeywords": sum(1 for item in insights if item.get("candidateNegativeKeyword")),
        "insights": insights[:limit],
    }


def _client_connector(db: Session, client: ClientAccount) -> tuple[YandexDirectConnector, list[str]]:
    if not client.yandex_account_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Yandex account is not bound to this client")
    token = get_yandex_access_token_for_account(db, client.yandex_account_id)
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Yandex OAuth token is not connected for this client")
    goal_ids = parse_goal_ids(client.conversion_goal_ids, fallback=client.main_goal_id)
    return YandexDirectConnector(access_token=token, client_login=client.direct_login), goal_ids


def build_live_period_summary(db: Session, client_id: str, *, preset: str = "yesterday", date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    client = db.get(ClientAccount, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    start, end, label = resolve_period(preset=preset, date_from=date_from, date_to=date_to)
    connector, goal_ids = _client_connector(db, client)
    rows = connector.get_campaign_daily_range_report(date_from=start, date_to=end, goal_ids=goal_ids or None, processing_mode="auto", max_wait_seconds=25)
    campaigns = _group_campaign_rows(rows, goal_ids, client.target_cpa)
    daily = _group_daily(rows, goal_ids)
    totals = _aggregate_values(campaigns)
    previous_from, previous_to = _split_previous_range(start, end)
    previous_rows: list[dict[str, str]] = []
    if label != "yesterday":
        try:
            previous_rows = connector.get_campaign_daily_range_report(date_from=previous_from, date_to=previous_to, goal_ids=goal_ids or None, processing_mode="auto", max_wait_seconds=25)
        except Exception:
            previous_rows = []
    previous_totals = _aggregate_values(_group_campaign_rows(previous_rows, goal_ids, client.target_cpa)) if previous_rows else {}
    return {
        "source": "yandex_direct_live_range_report",
        "client": {"id": client.id, "name": client.name, "targetCpa": client.target_cpa},
        "period": {
            "preset": label,
            "dateFrom": start.isoformat(),
            "dateTo": end.isoformat(),
            "days": (end - start).days + 1,
            "previousDateFrom": previous_from.isoformat(),
            "previousDateTo": previous_to.isoformat(),
        },
        "selectedGoalIds": goal_ids,
        "hasGoalData": any(item.get("goalConversions") is not None for item in campaigns),
        "totals": totals,
        "previousTotals": previous_totals,
        "changes": _changes(totals, previous_totals) if previous_totals else {},
        "daily": daily,
        "campaigns": campaigns,
        "insights": {
            "criticalCampaigns": [item for item in campaigns if item["severity"] == "critical"][:8],
            "warningCampaigns": [item for item in campaigns if item["severity"] == "warning"][:8],
            "opportunityCampaigns": [item for item in campaigns if item["severity"] == "opportunity"][:8],
            "lowDataCampaigns": [item for item in campaigns if item["severity"] == "info"][:8],
        },
        "message": "Live range summary loaded from Yandex Direct. Read-only; no changes were applied.",
    }


def _build_ai_prompt(summary: dict[str, Any], search_drilldown: dict[str, Any]) -> str:
    compact_summary = {
        "source": summary.get("source"),
        "client": summary.get("client"),
        "period": summary.get("period"),
        "selectedGoalIds": summary.get("selectedGoalIds"),
        "totals": summary.get("totals"),
        "previousTotals": summary.get("previousTotals"),
        "changes": summary.get("changes"),
        "daily": (summary.get("daily") or [])[-31:],
        "campaigns": (summary.get("campaigns") or [])[:20],
        "insights": summary.get("insights"),
        "searchQueryDrilldown": search_drilldown,
    }
    return f"""
Ты DirectPilot AI, senior PPC/marketing analyst по Яндекс.Директу.
Проанализируй выбранный период по live read-only данным Яндекс.Директа.

Обязательный формат ответа на русском:
1. Короткий вывод по аккаунту за период.
2. Динамика: сравни выбранный период с предыдущим равным периодом, если previousTotals доступны.
3. Общие показатели без динамики: расход, показы, клики, CTR, CPC, конверсии по выбранным целям, CPA, CR.
4. Кампании: критичные, предупреждения, возможности. Не смешивай РСЯ/ретаргет с поиском.
5. Нижние уровни: для поиска — запросы/ключи/группы/объявления/цели/посадочная; для РСЯ/ретаргета — площадки/аудитории/сегменты/креативы/устройства/гео/цели.
6. Рекомендации: только как dry-run/manual review, без применения изменений.
7. Missing data/limitations.

Правила безопасности:
- Не предлагай автоматическое применение без approval.
- Не выдумывай посадочные страницы, CRM-качество, гео, устройства, площадки, если их нет в данных.
- Если поисковые запросы загружены, используй их только как черновик гипотез и минус-слов.

Данные:
{json.dumps(compact_summary, ensure_ascii=False)}
""".strip()


async def build_live_period_ai_analysis(db: Session, client_id: str, *, preset: str = "14d", date_from: str | None = None, date_to: str | None = None, model: str | None = None, max_tokens: int = 3500) -> dict[str, Any]:
    summary = build_live_period_summary(db, client_id, preset=preset, date_from=date_from, date_to=date_to)
    client = db.get(ClientAccount, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    connector, goal_ids = _client_connector(db, client)
    period = summary["period"]
    search_rows: list[dict[str, str]] = []
    try:
        search_rows = connector.get_search_query_report(
            date_from=date.fromisoformat(period["dateFrom"]),
            date_to=date.fromisoformat(period["dateTo"]),
            limit=DEFAULT_SEARCH_QUERY_LIMIT,
            goal_ids=goal_ids or None,
            processing_mode="offline",
            max_wait_seconds=25,
        )
    except Exception:
        search_rows = []
    search_drilldown = _build_search_query_drilldown(search_rows, goal_ids)
    prompt = _build_ai_prompt(summary, search_drilldown)
    result = await generate_openrouter_response(model or "openrouter/auto", prompt, max_tokens=max_tokens)
    return {
        "source": "openrouter_with_live_yandex_direct_range",
        "period": summary["period"],
        "summary": summary,
        "searchQueryDrilldown": search_drilldown,
        "answer": result.get("content") or "",
        "model": result.get("model") or model or "openrouter/auto",
        "safety": {"readOnly": True, "canApplyAutomatically": False, "message": "Yandex Direct write API was not called."},
    }
