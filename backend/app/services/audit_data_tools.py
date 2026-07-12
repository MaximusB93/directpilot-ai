from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DirectCampaignPeriodStat, DirectSearchQueryPeriodStat
from app.schemas import AuditDataRequest, AuditDataRequestResult

MAX_AUDIT_DATA_REQUESTS = 15
MAX_REQUESTS_PER_CAMPAIGN = 4
MAX_TOOL_ROWS = 200


@dataclass(frozen=True)
class AuditDataTool:
    id: str
    supported_families: frozenset[str]
    supported_subtypes: frozenset[str]
    adapter: Callable[[Session, str, AuditDataRequest, int], list[dict[str, Any]]] | None
    maximum_rows: int
    permitted_fields: frozenset[str]
    timeout_seconds: int
    read_only: bool = True
    external_source: str | None = None


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _query_rows(db: Session, client_id: str, request: AuditDataRequest, limit: int) -> list[dict[str, Any]]:
    query = select(DirectSearchQueryPeriodStat).where(
        DirectSearchQueryPeriodStat.client_id == client_id,
        DirectSearchQueryPeriodStat.campaign_name == request.campaign_name,
    )
    date_from = _date(request.period.date_from)
    date_to = _date(request.period.date_to)
    if date_from:
        query = query.where(DirectSearchQueryPeriodStat.period_from >= date_from)
    if date_to:
        query = query.where(DirectSearchQueryPeriodStat.period_to <= date_to)
    rows = list(db.scalars(query.order_by(DirectSearchQueryPeriodStat.cost.desc()).limit(limit)))
    return [
        {
            "query": row.query,
            "ad_group_name": row.ad_group_name or "Группа без названия",
            "impressions": row.impressions,
            "clicks": row.clicks,
            "cost": round(row.cost or 0, 2),
            "conversions": row.goal_conversions,
            "cpa": row.goal_cpa,
        }
        for row in rows
    ]


def _ad_group_rows(db: Session, client_id: str, request: AuditDataRequest, limit: int) -> list[dict[str, Any]]:
    source_rows = _query_rows(db, client_id, request, MAX_TOOL_ROWS)
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
    for row in source_rows:
        name = str(row.get("ad_group_name") or "Группа без названия")
        item = groups[name]
        item["impressions"] += int(row.get("impressions") or 0)
        item["clicks"] += int(row.get("clicks") or 0)
        item["cost"] += float(row.get("cost") or 0)
        item["conversions"] += float(row.get("conversions") or 0)
    result = []
    for name, item in sorted(groups.items(), key=lambda pair: pair[1]["cost"], reverse=True)[:limit]:
        conversions = item["conversions"]
        result.append({
            "ad_group_name": name,
            **item,
            "cost": round(item["cost"], 2),
            "cpa": round(item["cost"] / conversions, 2) if conversions else None,
        })
    return result


def _goal_rows(db: Session, client_id: str, request: AuditDataRequest, limit: int) -> list[dict[str, Any]]:
    rows = list(db.scalars(
        select(DirectCampaignPeriodStat).where(
            DirectCampaignPeriodStat.client_id == client_id,
            DirectCampaignPeriodStat.campaign_name == request.campaign_name,
        ).order_by(DirectCampaignPeriodStat.period_to.desc()).limit(limit)
    ))
    return [
        {
            "campaign_name": row.campaign_name,
            "goal_ids": row.goal_ids or row.goal_id,
            "cost": round(row.cost or 0, 2),
            "clicks": row.clicks,
            "conversions": row.goal_conversions,
            "cpa": row.goal_cpa,
            "conversion_rate": row.conversion_rate,
        }
        for row in rows
    ]


SEARCH_FAMILIES = frozenset({"search"})
YAN_FAMILIES = frozenset({"yan"})
ALL_FAMILIES = frozenset({"search", "yan"})
SEARCH_SUBTYPES = frozenset({"search", "brand_search"})
YAN_SUBTYPES = frozenset({"yan_prospecting", "yan_retargeting"})

AUDIT_DATA_TOOLS: dict[str, AuditDataTool] = {
    "ad_groups": AuditDataTool("ad_groups", SEARCH_FAMILIES, SEARCH_SUBTYPES, _ad_group_rows, 100, frozenset({"ad_group_name", "impressions", "clicks", "cost", "conversions", "cpa"}), 10),
    "search_queries": AuditDataTool("search_queries", SEARCH_FAMILIES, SEARCH_SUBTYPES, _query_rows, 200, frozenset({"query", "ad_group_name", "impressions", "clicks", "cost", "conversions", "cpa"}), 15),
    "goals": AuditDataTool("goals", ALL_FAMILIES, SEARCH_SUBTYPES | YAN_SUBTYPES, _goal_rows, 100, frozenset({"campaign_name", "goal_ids", "clicks", "cost", "conversions", "cpa", "conversion_rate"}), 10),
}

for dimension, families, subtypes, external in [
    ("keywords", SEARCH_FAMILIES, SEARCH_SUBTYPES, None), ("ads", ALL_FAMILIES, SEARCH_SUBTYPES | YAN_SUBTYPES, None),
    ("landing_pages", ALL_FAMILIES, SEARCH_SUBTYPES | YAN_SUBTYPES, "safe_page_analyzer"),
    ("placements", YAN_FAMILIES, YAN_SUBTYPES, None), ("audiences", YAN_FAMILIES, YAN_SUBTYPES, None),
    ("retargeting_segments", YAN_FAMILIES, frozenset({"yan_retargeting"}), None),
    ("audience_exclusions", YAN_FAMILIES, frozenset({"yan_retargeting"}), None),
    ("devices", ALL_FAMILIES, SEARCH_SUBTYPES | YAN_SUBTYPES, None), ("geo", ALL_FAMILIES, SEARCH_SUBTYPES | YAN_SUBTYPES, None),
    ("demographics", ALL_FAMILIES, SEARCH_SUBTYPES | YAN_SUBTYPES, None), ("frequency", YAN_FAMILIES, YAN_SUBTYPES, None),
    ("conversion_sources", ALL_FAMILIES, SEARCH_SUBTYPES | YAN_SUBTYPES, "metrika"),
    ("lead_quality", ALL_FAMILIES, SEARCH_SUBTYPES | YAN_SUBTYPES, "crm"),
]:
    AUDIT_DATA_TOOLS[dimension] = AuditDataTool(dimension, families, subtypes, None, 100, frozenset(), 10, external_source=external)


def public_audit_tool_manifest() -> list[dict[str, Any]]:
    return [
        {
            "id": tool.id,
            "supported_campaign_families": sorted(tool.supported_families),
            "supported_campaign_subtypes": sorted(tool.supported_subtypes),
            "permitted_metrics": sorted(tool.permitted_fields),
            "maximum_rows": tool.maximum_rows,
            "supported_now": tool.adapter is not None,
            "requires_external_source": bool(tool.external_source),
            "read_only": True,
        }
        for tool in AUDIT_DATA_TOOLS.values()
    ]


def validate_audit_data_requests(requests: list[AuditDataRequest]) -> tuple[list[AuditDataRequest], list[AuditDataRequestResult]]:
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(requests, key=lambda item: (priority_rank[item.priority], not item.required_for_conclusion))
    accepted: list[AuditDataRequest] = []
    rejected: list[AuditDataRequestResult] = []
    campaign_counts: dict[str, int] = defaultdict(int)
    seen: set[tuple[str, str, str]] = set()
    for request in ordered:
        key = (request.hypothesis_id, request.campaign_name, request.dimension)
        if key in seen:
            continue
        seen.add(key)
        tool = AUDIT_DATA_TOOLS[request.dimension]
        if request.campaign_family == "unknown":
            status, code = "unsupported", "unsupported_campaign_type"
        elif request.campaign_family not in tool.supported_families or request.campaign_subtype not in tool.supported_subtypes:
            status, code = "not_applicable", "dimension_not_applicable"
        elif len(accepted) >= MAX_AUDIT_DATA_REQUESTS or campaign_counts[request.campaign_name] >= MAX_REQUESTS_PER_CAMPAIGN:
            status, code = "skipped_budget_limit", "audit_request_budget_exceeded"
        else:
            request.filters = {"campaign_name": request.campaign_name}
            request.metrics = [metric for metric in request.metrics if metric in tool.permitted_fields][:12]
            accepted.append(request)
            campaign_counts[request.campaign_name] += 1
            continue
        rejected.append(AuditDataRequestResult(
            request_id=request.request_id, hypothesis_id=request.hypothesis_id, dimension=request.dimension,
            status=status, summary="Запрос не выполнялся после backend-валидации.", error_code=code,
        ))
    return accepted, rejected


def collect_audit_data_requests(
    db: Session,
    client_id: str,
    requests: list[AuditDataRequest],
) -> tuple[list[AuditDataRequestResult], int]:
    results: list[AuditDataRequestResult] = []
    direct_api_calls = 0
    for request in requests:
        tool = AUDIT_DATA_TOOLS[request.dimension]
        if tool.adapter is None:
            results.append(AuditDataRequestResult(
                request_id=request.request_id, hypothesis_id=request.hypothesis_id, dimension=request.dimension,
                status="unavailable", source=tool.external_source, summary="Источник пока не подключён к read-only audit adapter.",
                limitations=["Вывод по этому измерению не формируется."], error_code="adapter_unavailable",
            ))
            continue
        try:
            rows = tool.adapter(db, client_id, request, min(tool.maximum_rows, MAX_TOOL_ROWS))
            results.append(AuditDataRequestResult(
                request_id=request.request_id, hypothesis_id=request.hypothesis_id, dimension=request.dimension,
                status="collected" if rows else "insufficient_data", source="directpilot_saved_read_only_stats",
                rows_analyzed=len(rows), data=rows,
                summary=f"Собрано строк: {len(rows)}." if rows else "Для запроса нет сохранённых строк.",
                limitations=[] if rows else ["Нужна повторная синхронизация или другой период."],
                error_code=None if rows else "no_saved_rows",
            ))
        except Exception:
            results.append(AuditDataRequestResult(
                request_id=request.request_id, hypothesis_id=request.hypothesis_id, dimension=request.dimension,
                status="failed", summary="Read-only adapter завершился ошибкой.", error_code="adapter_failed",
            ))
    return results, direct_api_calls
