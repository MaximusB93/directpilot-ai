from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectReadError
from app.models import DirectCampaignPeriodStat, DirectSearchQueryPeriodStat
from app.schemas import AuditDataRequest, AuditDataRequestResult
from app.services.yandex_direct_read import MAX_LIVE_REQUESTS_PER_ADVANCE, execute_direct_read
from app.services.yandex_direct_read_capabilities import (
    YANDEX_DIRECT_READ_CAPABILITIES,
    public_direct_read_manifest,
)

MAX_AUDIT_DATA_REQUESTS = 20
MAX_REQUESTS_PER_HYPOTHESIS = 4
MAX_TOOL_ROWS = 200

DIMENSION_ALIASES = {
    "audiences": "audience_targets",
}


def _capability_id(request: AuditDataRequest) -> str:
    return request.capability_id or DIMENSION_ALIASES.get(request.dimension, request.dimension)


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
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0}
    )
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


SAVED_ADAPTERS: dict[str, Callable[[Session, str, AuditDataRequest, int], list[dict[str, Any]]]] = {
    "ad_groups": _ad_group_rows,
    "search_queries": _query_rows,
    "goals": _goal_rows,
    "conversions_by_goal": _goal_rows,
}


def public_audit_tool_manifest() -> list[dict[str, Any]]:
    return public_direct_read_manifest()


def _rejected_result(
    request: AuditDataRequest,
    *,
    status: str,
    code: str,
    capability_id: str,
) -> AuditDataRequestResult:
    capability = YANDEX_DIRECT_READ_CAPABILITIES.get(capability_id)
    return AuditDataRequestResult(
        request_id=request.request_id,
        hypothesis_id=request.hypothesis_id,
        capability_id=capability_id,
        dimension=request.dimension,
        campaign_name=request.campaign_name,
        status=status,
        source_type=capability.source_type if capability else None,
        source_required=capability.source_required if capability else None,
        summary="Запрос не выполнялся после backend-валидации.",
        error_code=code,
    )


def validate_audit_data_requests(
    requests: list[AuditDataRequest],
    *,
    max_requests: int = MAX_AUDIT_DATA_REQUESTS,
) -> tuple[list[AuditDataRequest], list[AuditDataRequestResult]]:
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(requests, key=lambda item: (priority_rank[item.priority], not item.required_for_conclusion))
    accepted: list[AuditDataRequest] = []
    rejected: list[AuditDataRequestResult] = []
    hypothesis_counts: dict[str, int] = defaultdict(int)
    seen: set[tuple[str, str, str, str]] = set()
    for request in ordered:
        capability_id = _capability_id(request)
        capability = YANDEX_DIRECT_READ_CAPABILITIES.get(capability_id)
        key = (request.hypothesis_id, request.campaign_name, capability_id, request.data_preference)
        if key in seen:
            continue
        seen.add(key)
        if capability is None:
            status, code = "unsupported", "unknown_capability"
        elif not capability.read_only:
            status, code = "unsupported", "write_capability_forbidden"
        elif request.campaign_family == "unknown" and capability_id not in {"campaigns", "campaign_settings", "campaign_status"}:
            status, code = "unsupported", "unsupported_campaign_type"
        elif (
            request.campaign_family not in capability.supported_families
            or request.campaign_subtype not in capability.supported_subtypes
        ):
            status, code = "not_applicable", "dimension_not_applicable"
        elif len(accepted) >= max(1, int(max_requests)) or (
            hypothesis_counts[request.hypothesis_id] >= MAX_REQUESTS_PER_HYPOTHESIS
            and not request.request_id.startswith("policy_")
        ):
            status, code = "skipped_budget_limit", "audit_request_budget_exceeded"
        else:
            request.capability_id = capability_id
            request.filters = {"campaign_name": request.campaign_name}
            request.metrics = [metric for metric in request.metrics if metric in capability.allowed_metrics][:12]
            accepted.append(request)
            hypothesis_counts[request.hypothesis_id] += 1
            continue
        rejected.append(_rejected_result(
            request, status=status, code=code, capability_id=capability_id,
        ))
    return accepted, rejected


def _saved_result(
    db: Session,
    client_id: str,
    request: AuditDataRequest,
    *,
    warning: str | None = None,
) -> AuditDataRequestResult | None:
    capability_id = _capability_id(request)
    adapter = SAVED_ADAPTERS.get(capability_id)
    if adapter is None:
        return None
    capability = YANDEX_DIRECT_READ_CAPABILITIES[capability_id]
    rows = adapter(db, client_id, request, min(capability.maximum_limit, MAX_TOOL_ROWS))
    return AuditDataRequestResult(
        request_id=request.request_id,
        hypothesis_id=request.hypothesis_id,
        capability_id=capability_id,
        dimension=request.dimension,
        campaign_name=request.campaign_name,
        status="collected" if rows else "insufficient_data",
        source="directpilot_saved_stats",
        source_type="saved_data",
        live=False,
        rows_analyzed=len(rows),
        rows_total=len(rows),
        data=rows,
        summary=f"Собрано сохранённых строк: {len(rows)}." if rows else "Для запроса нет сохранённых строк.",
        limitations=[] if rows else ["Нужна повторная синхронизация или другой период."],
        warnings=[warning] if warning else [],
        error_code=None if rows else "no_saved_rows",
    )


def _clone_result(result: AuditDataRequestResult, request: AuditDataRequest) -> AuditDataRequestResult:
    payload = result.model_dump(mode="json")
    payload.update({
        "request_id": request.request_id,
        "hypothesis_id": request.hypothesis_id,
        "dimension": request.dimension,
        "campaign_name": request.campaign_name,
    })
    return AuditDataRequestResult.model_validate(payload)


def collect_audit_data_requests(
    db: Session,
    client_id: str,
    requests: list[AuditDataRequest],
    *,
    audit_job_id: str | None = None,
    max_live_requests: int = MAX_LIVE_REQUESTS_PER_ADVANCE,
    cache_policy: str = "prefer_cache",
    allow_saved_fallback: bool = True,
) -> tuple[list[AuditDataRequestResult], int]:
    if cache_policy == "fresh":
        allow_saved_fallback = False
    results: list[AuditDataRequestResult] = []
    direct_api_calls = 0
    deduplicated: dict[tuple[Any, ...], AuditDataRequestResult] = {}
    for request in requests:
        capability_id = _capability_id(request)
        capability = YANDEX_DIRECT_READ_CAPABILITIES[capability_id]
        dedupe_key = (
            capability_id,
            request.campaign_name,
            request.period.date_from,
            request.period.date_to,
            tuple(sorted(request.metrics)),
            request.data_preference,
        )
        if dedupe_key in deduplicated:
            cloned = _clone_result(deduplicated[dedupe_key], request)
            results.append(cloned)
            continue
        saved = None
        if request.data_preference == "saved_allowed" and cache_policy != "fresh":
            saved = _saved_result(db, client_id, request)
            if saved and saved.status == "collected":
                results.append(saved)
                deduplicated[dedupe_key] = saved
                continue
        if not capability.live_supported:
            result = AuditDataRequestResult(
                request_id=request.request_id,
                hypothesis_id=request.hypothesis_id,
                capability_id=capability_id,
                dimension=request.dimension,
                campaign_name=request.campaign_name,
                status="unavailable",
                source="unavailable",
                source_type=capability.source_type,
                source_required=capability.source_required,
                summary="Источник пока недоступен через read-only Direct API.",
                limitations=["Вывод по этому измерению не формируется."],
                error_code="adapter_unavailable",
            )
        else:
            estimated_calls = 3 if capability.service == "retargetinglists" else (2 if capability.service == "audiencetargets" else 1)
        if capability.live_supported and direct_api_calls + estimated_calls > max_live_requests:
            result = _rejected_result(
                request,
                status="skipped_budget_limit",
                code="live_request_budget_exceeded",
                capability_id=capability_id,
            )
        elif capability.live_supported:
            try:
                outcome = execute_direct_read(
                    db,
                    client_id,
                    request,
                    audit_job_id=audit_job_id,
                    allow_cache=cache_policy != "fresh",
                    cache_policy=cache_policy,
                )
                result = outcome.result
                result.live_attempted = not result.cached
                result.live_error_code = result.error_code if result.live_attempted else None
                direct_api_calls += outcome.api_calls
            except YandexDirectReadError as exc:
                direct_api_calls += int(getattr(exc, "api_calls", 0) or 0)
                result = AuditDataRequestResult(
                    request_id=request.request_id,
                    hypothesis_id=request.hypothesis_id,
                    capability_id=capability_id,
                    dimension=request.dimension,
                    campaign_name=request.campaign_name,
                    status="failed" if exc.retryable else "unavailable",
                    source="unavailable",
                    source_type=capability.source_type,
                    live_attempted=True,
                    live_error_code=exc.code,
                    summary=str(exc),
                    error_code=exc.code,
                    retryable=exc.retryable,
                )
            except Exception:
                result = AuditDataRequestResult(
                    request_id=request.request_id,
                    hypothesis_id=request.hypothesis_id,
                    capability_id=capability_id,
                    dimension=request.dimension,
                    campaign_name=request.campaign_name,
                    status="failed",
                    source="unavailable",
                    source_type=capability.source_type,
                    live_attempted=True,
                    live_error_code="adapter_failed",
                    summary="Read-only Direct adapter завершился ошибкой.",
                    error_code="adapter_failed",
                    retryable=True,
                )
        if result.live_attempted and result.status in {"failed", "unavailable", "insufficient_data", "partial"}:
            result.source = result.source or "yandex_direct_live"
            result.freshness = result.freshness or "live_failed"
        if (
            allow_saved_fallback
            and request.data_preference == "live_preferred"
            and result.status in {"failed", "unavailable", "insufficient_data"}
        ):
            saved = _saved_result(
                db,
                client_id,
                request,
                warning=f"Live Direct недоступен ({result.error_code or result.status}); использованы сохранённые данные.",
            )
            if saved and saved.status == "collected":
                saved.live_attempted = result.live_attempted
                saved.live_error_code = result.live_error_code or result.error_code
                saved.saved_fallback = True
                result = saved
        results.append(result)
        deduplicated[dedupe_key] = result
    return results, direct_api_calls


def estimated_live_calls(request: AuditDataRequest) -> int:
    capability = YANDEX_DIRECT_READ_CAPABILITIES.get(_capability_id(request))
    if capability is None or not capability.live_supported:
        return 0
    if capability.service == "retargetinglists":
        return 3
    if capability.service == "audiencetargets":
        return 2
    return 1


def select_live_request_batch(
    requests: list[AuditDataRequest],
    *, max_live_calls: int = MAX_LIVE_REQUESTS_PER_ADVANCE,
) -> tuple[list[AuditDataRequest], list[AuditDataRequest]]:
    """Select a stable prefix-like batch without dropping deferred requests."""

    selected: list[AuditDataRequest] = []
    pending: list[AuditDataRequest] = []
    calls = 0
    for request in requests:
        estimated = estimated_live_calls(request)
        if selected and estimated and calls + estimated > max_live_calls:
            pending.append(request)
            continue
        if estimated > max_live_calls:
            pending.append(request)
            continue
        selected.append(request)
        calls += estimated
    return selected, pending
