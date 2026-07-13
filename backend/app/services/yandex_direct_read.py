from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector, YandexDirectReadError
from app.knowledge.yandex_direct_api import DIRECT_NORMALIZATION_VERSION
from app.models import ClientAccount, ConnectedAccount, DirectCampaignPeriodStat, DirectReadCache, DirectReportJob
from app.schemas import AuditDataRequest, AuditDataRequestResult
from app.services.connected_accounts import get_yandex_access_token_for_account
from app.services.yandex_direct_read_capabilities import (
    DirectReadCapability,
    YANDEX_DIRECT_READ_CAPABILITIES,
    validate_capability_definition,
)
from app.services.yandex_metrika import parse_goal_ids

logger = logging.getLogger(__name__)

MAX_LIVE_REQUESTS_PER_ADVANCE = 5
MAX_PROCESSING_REPORTS_PER_ACCOUNT = 2
MAX_REPORT_REQUESTS_PER_ACCOUNT_WINDOW = 20
REPORT_RATE_WINDOW = timedelta(seconds=10)
MAX_NORMALIZED_ROWS = 2000
MAX_NORMALIZED_TEXT = 1200
MAX_REPORT_GOALS = 10
REPORT_PAGE_SIZE = 500
ALL_CAMPAIGNS_SENTINEL = "__all_campaigns__"
REPORT_JOB_TTL = timedelta(hours=2)


@dataclass(frozen=True)
class DirectReadOutcome:
    result: AuditDataRequestResult
    api_calls: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _login_hash(value: str | None) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def _request_hash(spec: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dump(spec).encode("utf-8")).hexdigest()


def _snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return value.replace("-", "_").lower()


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized_key = _snake_case(key_text)
            if normalized_key in {
                "id", "campaign_id", "ad_group_id", "ad_id", "criterion_id",
                "retargeting_list_id", "sitelink_set_id", "region_ids",
                "location_of_presence_id",
            }:
                continue
            compact_key = normalized_key.replace("_", "")
            if (
                compact_key in {
                    "authorization", "apikey", "accesstoken", "refreshtoken", "oauthtoken",
                    "clientlogin", "password", "secret",
                }
                or compact_key.endswith("token")
            ):
                continue
            safe[normalized_key] = _safe_value(item)
        return safe
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:MAX_NORMALIZED_TEXT]
    return value


def _normalize_rows(rows: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], bool]:
    bounded = rows[: min(limit, MAX_NORMALIZED_ROWS)]
    return [_safe_value(row) for row in bounded], len(rows) > len(bounded)


def _period(request: AuditDataRequest) -> dict[str, str | int | None]:
    date_to = request.period.date_to or _now().date().isoformat()
    if request.period.date_from:
        date_from = request.period.date_from
    else:
        days = max(1, min(int(request.period.days or 30), 365))
        date_from = (_now().date() - timedelta(days=days - 1)).isoformat()
    return {"date_from": date_from, "date_to": date_to, "days": request.period.days}


def _base_result(
    request: AuditDataRequest,
    capability: DirectReadCapability,
    *,
    status: str,
    source: str | None = None,
    summary: str = "",
    **kwargs: Any,
) -> AuditDataRequestResult:
    return AuditDataRequestResult(
        request_id=request.request_id,
        hypothesis_id=request.hypothesis_id,
        capability_id=capability.id,
        dimension=request.dimension,
        campaign_name=request.campaign_name,
        status=status,
        source=source,
        source_type=capability.source_type,
        source_required=capability.source_required,
        capability_schema_version=capability.capability_schema_version,
        direct_api_knowledge_version=capability.knowledge_version,
        normalization_version=DIRECT_NORMALIZATION_VERSION,
        period=_period(request),
        summary=summary,
        **kwargs,
    )


def _resolve_campaign_ids(db: Session, client_id: str, campaign_name: str) -> list[str]:
    if campaign_name == ALL_CAMPAIGNS_SENTINEL:
        return []
    rows = db.execute(
        select(DirectCampaignPeriodStat.campaign_id).where(
            DirectCampaignPeriodStat.client_id == client_id,
            DirectCampaignPeriodStat.campaign_name == campaign_name,
        ).distinct()
    ).all()
    ids = sorted({str(row[0]) for row in rows if row[0]})
    if not ids:
        raise YandexDirectReadError("direct_no_data", "Campaign was not found in trusted synced data.")
    if len(ids) > 1:
        raise YandexDirectReadError("ambiguous_campaign", "Several campaign IDs have the same name.")
    return ids


def _trusted_spec(
    client: ClientAccount,
    capability: DirectReadCapability,
    request: AuditDataRequest,
    campaign_ids: list[str],
) -> dict[str, Any]:
    requested_metrics = sorted(set(request.metrics) & set(capability.allowed_metrics))
    return {
        "client_login_hash": _login_hash(client.direct_login),
        "capability_id": capability.id,
        "capability_schema_version": capability.capability_schema_version,
        "direct_api_knowledge_version": capability.knowledge_version,
        "normalization_version": DIRECT_NORMALIZATION_VERSION,
        "source_type": capability.source_type,
        "service": capability.service,
        "report_type": capability.report_type,
        "api_fields": list(capability.api_fields),
        "campaign_ids": campaign_ids,
        "campaign_family": request.campaign_family,
        "campaign_subtype": request.campaign_subtype,
        "period": _period(request),
        "goal_ids": parse_goal_ids(client.conversion_goal_ids, fallback=client.main_goal_id),
        "metrics": requested_metrics,
        "filters": {"campaign_name": request.campaign_name},
        "limit": min(capability.maximum_limit, MAX_NORMALIZED_ROWS),
    }


def split_report_goal_ids(goal_ids: list[str], maximum: int = MAX_REPORT_GOALS) -> list[list[str]]:
    normalized = list(dict.fromkeys(str(item).strip() for item in goal_ids if str(item).strip()))
    return [normalized[index:index + maximum] for index in range(0, len(normalized), maximum)] or [[]]


def _service_params(capability: DirectReadCapability, campaign_ids: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {
        "SelectionCriteria": {},
        "FieldNames": list(capability.api_fields),
    }
    service = capability.service
    if service == "campaigns":
        params["SelectionCriteria"] = {"Ids": [int(item) for item in campaign_ids]} if campaign_ids else {}
    elif service in {"adgroups", "ads", "keywords", "bidmodifiers"}:
        params["SelectionCriteria"] = {"CampaignIds": [int(item) for item in campaign_ids]}
    elif service == "audiencetargets":
        raise YandexDirectReadError("direct_live_dependency_required", "Trusted ad group IDs are required.")
    elif service == "retargetinglists":
        params["SelectionCriteria"] = {}
    for key, values in capability.extra_params:
        params[key] = list(values)
    return params


def _report_spec(
    capability: DirectReadCapability,
    trusted: dict[str, Any],
    request_hash: str,
) -> dict[str, Any]:
    validate_capability_definition(capability)
    period = trusted["period"]
    selection: dict[str, Any] = {
        "DateFrom": period["date_from"],
        "DateTo": period["date_to"],
    }
    if trusted["campaign_ids"]:
        selection["Filter"] = [{"Field": "CampaignId", "Operator": "IN", "Values": trusted["campaign_ids"]}]
    spec: dict[str, Any] = {
        "SelectionCriteria": selection,
        "FieldNames": list(capability.api_fields),
        "ReportName": f"DirectPilot Audit {capability.id} {request_hash[:16]}",
        "ReportType": capability.report_type,
        "DateRangeType": "CUSTOM_DATE",
        "Format": "TSV",
        "IncludeVAT": "YES",
        "IncludeDiscount": "YES",
        "Page": {"Limit": min(REPORT_PAGE_SIZE, int(trusted["limit"])), "Offset": 0},
    }
    if "Cost" in capability.api_fields:
        spec["OrderBy"] = [{"Field": "Cost", "SortOrder": "DESCENDING"}]
    elif "CampaignId" in capability.api_fields:
        spec["OrderBy"] = [{"Field": "CampaignId"}]
    if trusted["goal_ids"] and capability.goal_ids_supported:
        batches = split_report_goal_ids([str(item) for item in trusted["goal_ids"]])
        spec["Goals"] = [int(item) if str(item).isdigit() else str(item) for item in batches[0]]
        spec["AttributionModels"] = ["AUTO"]
        if len(batches) > 1:
            spec["_GoalBatches"] = batches
            spec["_GoalBatchIndex"] = 0
    return spec


def _report_page_spec(stored_spec: dict[str, Any], report_job: DirectReportJob, maximum_rows: int) -> dict[str, Any]:
    spec = {key: value for key, value in stored_spec.items() if not key.startswith("_")}
    batches = stored_spec.get("_GoalBatches") or []
    if batches:
        index = int(stored_spec.get("_GoalBatchIndex") or 0)
        batch = batches[min(index, len(batches) - 1)]
        spec["Goals"] = [int(item) if str(item).isdigit() else str(item) for item in batch]
    spec["Page"] = {
        "Limit": min(REPORT_PAGE_SIZE, max(1, int(maximum_rows))),
        "Offset": int(report_job.next_offset or 0),
    }
    return spec


def _report_row_key(row: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    metric_prefixes = (
        "impressions", "clicks", "cost", "ctr", "avg_cpc", "conversions",
        "cost_per_conversion", "conversion_rate", "revenue", "goals_roi",
    )
    dimensions = [
        (str(key), str(value)) for key, value in row.items()
        if not str(key).startswith(metric_prefixes)
    ]
    return tuple(sorted(dimensions))


def _merge_report_rows(existing: list[dict[str, Any]], page: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {_report_row_key(row): dict(row) for row in existing}
    for row in page:
        key = _report_row_key(row)
        if key in merged:
            merged[key].update(row)
        else:
            merged[key] = dict(row)
    return list(merged.values())


def _account_client_ids(db: Session, account_id: str) -> list[str]:
    return list(db.scalars(select(ClientAccount.id).where(ClientAccount.yandex_account_id == account_id)))


def _account_recent_report_attempts(db: Session, client_ids: list[str], now: datetime) -> int:
    jobs = list(db.scalars(select(DirectReportJob).where(
        DirectReportJob.client_id.in_(client_ids),
        DirectReportJob.updated_at >= now - REPORT_RATE_WINDOW,
    )))
    return sum(int(item.attempts or 0) for item in jobs)


def _cache_result(
    db: Session,
    *,
    client_id: str,
    capability: DirectReadCapability,
    request_hash: str,
    source: str,
    rows: list[dict[str, Any]],
    period: dict[str, Any],
    partial: bool,
    warnings: list[str],
    original_status: str,
    error_code: str | None = None,
) -> None:
    now = _now()
    cached = db.scalar(select(DirectReadCache).where(
        DirectReadCache.client_id == client_id,
        DirectReadCache.request_hash == request_hash,
    ))
    if cached is None:
        cached = DirectReadCache(client_id=client_id, request_hash=request_hash, capability_id=capability.id)
        db.add(cached)
    cached.source = source
    cached.original_status = original_status
    cached.error_code = error_code
    cached.capability_schema_version = capability.capability_schema_version
    cached.direct_api_knowledge_version = capability.knowledge_version
    cached.normalization_version = DIRECT_NORMALIZATION_VERSION
    cached.source_type = capability.source_type
    cached.report_type = capability.report_type
    cached.service = capability.service
    cached.api_fields_hash = hashlib.sha256(_json_dump(list(capability.api_fields)).encode("utf-8")).hexdigest()
    cached.result_json = _json_dump(rows)
    cached.period_json = _json_dump(period)
    cached.rows_count = len(rows)
    cached.partial = partial
    cached.warnings_json = _json_dump(warnings)
    cached.fetched_at = now
    ttl = min(120, capability.cache_ttl_seconds) if original_status == "insufficient_data" else capability.cache_ttl_seconds
    cached.expires_at = now + timedelta(seconds=ttl)
    db.flush()


def _cached_outcome(
    db: Session,
    client_id: str,
    request: AuditDataRequest,
    capability: DirectReadCapability,
    request_hash: str,
) -> DirectReadOutcome | None:
    cached = db.scalar(select(DirectReadCache).where(
        DirectReadCache.client_id == client_id,
        DirectReadCache.request_hash == request_hash,
        DirectReadCache.expires_at > _now(),
    ))
    if cached is None:
        return None
    rows = _json_load(cached.result_json, [])
    logger.info(
        "DIRECT_READ_CACHE_HIT capability_id=%s request_hash=%s rows=%s",
        capability.id, request_hash, len(rows),
    )
    original_status = cached.original_status or ("insufficient_data" if not rows else "collected")
    status = "cached" if original_status == "collected" else original_status
    return DirectReadOutcome(_base_result(
        request,
        capability,
        status=status,
        source="yandex_direct_cached_live",
        live=True,
        cached=True,
        request_hash=request_hash,
        freshness="cached_fresh",
        fetched_at=cached.fetched_at.isoformat(),
        rows_analyzed=len(rows),
        rows_total=cached.rows_count,
        truncated=cached.partial,
        data=rows,
        warnings=_json_load(cached.warnings_json, []),
        summary=f"Получено из свежего кеша: {len(rows)} строк." if rows else "Свежий кеш подтверждает отсутствие строк по запросу.",
        error_code=cached.error_code,
    ))


def _completed_outcome(
    db: Session,
    client_id: str,
    request: AuditDataRequest,
    capability: DirectReadCapability,
    trusted: dict[str, Any],
    request_hash: str,
    rows: list[dict[str, Any]],
    source: str,
    *,
    api_calls: int,
    forced_partial: bool = False,
) -> DirectReadOutcome:
    normalized, truncated = _normalize_rows(rows, int(trusted["limit"]))
    truncated = truncated or forced_partial
    now = _now()
    warnings = ["Результат ограничен безопасным лимитом строк."] if truncated else []
    status = "partial" if truncated else ("collected" if normalized else "insufficient_data")
    _cache_result(
        db,
        client_id=client_id,
        capability=capability,
        request_hash=request_hash,
        source=source,
        rows=normalized,
        period=trusted["period"],
        partial=truncated,
        warnings=warnings,
        original_status=status,
        error_code=None if normalized else "direct_no_data",
    )
    return DirectReadOutcome(_base_result(
        request,
        capability,
        status=status,
        source=source,
        live=True,
        request_hash=request_hash,
        freshness="live",
        fetched_at=now.isoformat(),
        rows_analyzed=len(normalized),
        rows_total=len(rows),
        truncated=truncated,
        data=normalized,
        warnings=warnings,
        summary=f"Получено live-строк: {len(normalized)}." if normalized else "Яндекс.Директ не вернул строк по запросу.",
        error_code=None if normalized else "direct_no_data",
    ), api_calls=api_calls)


def _report_outcome(
    db: Session,
    client_id: str,
    connector: YandexDirectConnector,
    request: AuditDataRequest,
    capability: DirectReadCapability,
    trusted: dict[str, Any],
    request_hash: str,
    *,
    audit_job_id: str | None,
    cache_policy: str,
    account_id: str,
) -> DirectReadOutcome:
    now = _now()
    report_job = db.scalar(select(DirectReportJob).where(
        DirectReportJob.client_id == client_id,
        DirectReportJob.request_hash == request_hash,
    ))
    if cache_policy == "fresh" and report_job and report_job.audit_job_id != audit_job_id:
        if report_job.status in {"queued", "requested", "processing"}:
            return DirectReadOutcome(_base_result(
                request,
                capability,
                status="processing",
                source="yandex_direct_live_report",
                live=True,
                request_hash=request_hash,
                retryable=True,
                next_retry_at=(now + timedelta(seconds=5)).isoformat(),
                summary="Другой fresh-аудит формирует такой же отчёт; текущий аудит дождётся своей live-попытки.",
                error_code="fresh_report_busy",
            ))
        db.delete(report_job)
        db.flush()
        report_job = None
    if report_job and report_job.expires_at:
        expires_at = report_job.expires_at
        expires_at = expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
        if expires_at <= now:
            db.delete(report_job)
            db.flush()
            report_job = None
    if report_job and report_job.status == "completed":
        rows = _json_load(report_job.result_snapshot_json, [])
        return _completed_outcome(
            db, client_id, request, capability, trusted, request_hash, rows, "yandex_direct_cached_live",
            api_calls=0, forced_partial=bool(report_job.partial),
        )
    if report_job and report_job.status in {"queued", "requested", "processing"} and report_job.next_retry_at:
        retry_at = report_job.next_retry_at
        retry_at = retry_at.replace(tzinfo=UTC) if retry_at.tzinfo is None else retry_at
        if retry_at > now:
            return DirectReadOutcome(_base_result(
                request,
                capability,
                status="processing",
                source="yandex_direct_live_report",
                live=True,
                request_hash=request_hash,
                retryable=True,
                next_retry_at=retry_at.isoformat(),
                summary="Яндекс.Директ формирует дополнительный отчёт.",
                error_code="direct_report_processing",
            ))
    if report_job and report_job.status == "failed" and report_job.next_retry_at:
        retry_at = report_job.next_retry_at
        retry_at = retry_at.replace(tzinfo=UTC) if retry_at.tzinfo is None else retry_at
        if retry_at > now:
            return DirectReadOutcome(_base_result(
                request,
                capability,
                status="failed",
                source="unavailable",
                request_hash=request_hash,
                retryable=True,
                next_retry_at=retry_at.isoformat(),
                summary=report_job.error_message or "Временная ошибка отчёта Яндекс.Директа.",
                error_code=report_job.error_code or "direct_temporary_error",
            ))
    if report_job is None:
        account_client_ids = _account_client_ids(db, account_id)
        active_count = len(list(db.scalars(select(DirectReportJob.id).where(
            DirectReportJob.client_id.in_(account_client_ids),
            DirectReportJob.status.in_(("queued", "requested", "processing")),
            or_(DirectReportJob.expires_at.is_(None), DirectReportJob.expires_at > now),
        ))))
        if active_count >= MAX_PROCESSING_REPORTS_PER_ACCOUNT:
            return DirectReadOutcome(_base_result(
                request, capability, status="processing", source="yandex_direct_live_report", live=True,
                request_hash=request_hash, retryable=True,
                next_retry_at=(now + timedelta(seconds=5)).isoformat(),
                summary="Достигнут безопасный лимит параллельных отчётов.",
                error_code="direct_report_queue_full",
            ))
        report_spec = _report_spec(capability, trusted, request_hash)
        report_job = DirectReportJob(
            audit_job_id=audit_job_id,
            client_id=client_id,
            capability_id=capability.id,
            request_hash=request_hash,
            report_name=report_spec["ReportName"],
            report_spec_json=_json_dump(report_spec),
            status="queued",
            expires_at=now + REPORT_JOB_TTL,
        )
        db.add(report_job)
        db.flush()
    account_client_ids = _account_client_ids(db, account_id)
    if _account_recent_report_attempts(db, account_client_ids, now) >= MAX_REPORT_REQUESTS_PER_ACCOUNT_WINDOW:
        return DirectReadOutcome(_base_result(
            request,
            capability,
            status="processing",
            source="yandex_direct_live_report",
            live=True,
            request_hash=request_hash,
            retryable=True,
            next_retry_at=(now + REPORT_RATE_WINDOW).isoformat(),
            summary="Shared Reports API request budget for this Yandex account is temporarily exhausted.",
            error_code="direct_report_account_rate_budget",
        ))
    stored_report_spec = _json_load(report_job.report_spec_json, {})
    report_spec = _report_page_spec(stored_report_spec, report_job, int(trusted["limit"]))
    report_job.status = "requested"
    report_job.attempts += 1
    started_at = perf_counter()
    try:
        response = connector.request_report(
            report_spec,
            processing_mode="offline" if capability.report_type == "SEARCH_QUERY_PERFORMANCE_REPORT" else "auto",
        )
    except YandexDirectReadError as exc:
        report_job.status = "failed"
        report_job.error_code = exc.code
        report_job.error_message = str(exc)[:500]
        report_job.next_retry_at = now + timedelta(seconds=min(300, 2 ** min(report_job.attempts, 8))) if exc.retryable else None
        raise
    elapsed_ms = round((perf_counter() - started_at) * 1000)
    if response["status"] == "processing":
        retry_after = max(1, min(int(response.get("retry_after_seconds") or 1), 300))
        report_job.status = "processing"
        report_job.retry_after_seconds = retry_after
        report_job.next_retry_at = now + timedelta(seconds=retry_after)
        logger.info(
            "DIRECT_READ_REQUEST_PROCESSING audit_job_id=%s capability_id=%s request_hash=%s "
            "source_type=report elapsed_ms=%s status=processing",
            audit_job_id, capability.id, request_hash, elapsed_ms,
        )
        return DirectReadOutcome(_base_result(
            request,
            capability,
            status="processing",
            source="yandex_direct_live_report",
            live=True,
            request_hash=request_hash,
            retryable=True,
            next_retry_at=report_job.next_retry_at.isoformat(),
            summary="Яндекс.Директ формирует дополнительный отчёт.",
            error_code="direct_report_processing",
        ), api_calls=1)
    rows = list(response.get("rows") or [])
    normalized, _ = _normalize_rows(rows, REPORT_PAGE_SIZE)
    accumulated = _json_load(report_job.result_snapshot_json, [])
    accumulated = _merge_report_rows(accumulated, normalized)
    report_job.pages_completed = int(report_job.pages_completed or 0) + 1
    report_job.rows_collected = len(accumulated)
    report_job.rows_count = len(accumulated)
    report_job.result_snapshot_json = _json_dump(accumulated)
    limited_by = response.get("limited_by")
    if limited_by is not None:
        report_job.limited_by = int(limited_by)
    row_limit_reached = bool(limited_by is not None and len(accumulated) >= int(trusted["limit"]))
    batches = stored_report_spec.get("_GoalBatches") or []
    batch_index = int(stored_report_spec.get("_GoalBatchIndex") or 0)
    if limited_by is not None and not row_limit_reached:
        report_job.status = "processing"
        report_job.partial = True
        report_job.next_offset = int(limited_by)
        report_job.next_retry_at = now
        return DirectReadOutcome(_base_result(
            request,
            capability,
            status="processing",
            source="yandex_direct_live_report",
            live=True,
            request_hash=request_hash,
            retryable=True,
            next_retry_at=now.isoformat(),
            rows_analyzed=len(accumulated),
            rows_total=len(accumulated),
            truncated=True,
            summary=f"Получена страница {report_job.pages_completed}; продолжение отчёта сохранено.",
            error_code="direct_report_pagination_pending",
        ), api_calls=1)
    if batches and batch_index + 1 < len(batches) and not row_limit_reached:
        stored_report_spec["_GoalBatchIndex"] = batch_index + 1
        report_job.report_spec_json = _json_dump(stored_report_spec)
        report_job.status = "processing"
        report_job.partial = True
        report_job.next_offset = 0
        report_job.next_retry_at = now
        return DirectReadOutcome(_base_result(
            request,
            capability,
            status="processing",
            source="yandex_direct_live_report",
            live=True,
            request_hash=request_hash,
            retryable=True,
            next_retry_at=now.isoformat(),
            rows_analyzed=len(accumulated),
            rows_total=len(accumulated),
            truncated=True,
            summary=f"Получена партия целей {batch_index + 1} из {len(batches)}.",
            error_code="direct_report_goal_batch_pending",
        ), api_calls=1)
    report_job.status = "completed"
    report_job.row_limit_reached = row_limit_reached
    report_job.partial = row_limit_reached
    report_job.next_offset = 0
    report_job.next_retry_at = None
    report_job.completed_at = now
    report_job.expires_at = now + timedelta(seconds=capability.cache_ttl_seconds)
    logger.info(
        "DIRECT_READ_REQUEST_COMPLETED audit_job_id=%s capability_id=%s request_hash=%s "
        "source_type=report elapsed_ms=%s rows=%s status=completed",
        audit_job_id, capability.id, request_hash, elapsed_ms, len(accumulated),
    )
    return _completed_outcome(
        db, client_id, request, capability, trusted, request_hash, accumulated,
        "yandex_direct_live_report", api_calls=1, forced_partial=row_limit_reached,
    )


def execute_direct_read(
    db: Session,
    client_id: str,
    request: AuditDataRequest,
    *,
    audit_job_id: str | None = None,
    allow_cache: bool = True,
    cache_policy: str = "prefer_cache",
) -> DirectReadOutcome:
    capability_id = request.capability_id or request.dimension
    capability = YANDEX_DIRECT_READ_CAPABILITIES.get(capability_id)
    if capability is None:
        raise YandexDirectReadError("direct_capability_not_allowed", "Unknown semantic Direct capability.")
    if not capability.read_only:
        raise YandexDirectReadError("direct_write_forbidden", "Only read-only Direct capabilities are allowed.")
    try:
        validate_capability_definition(capability)
    except ValueError as exc:
        raise YandexDirectReadError("direct_invalid_field_combination", str(exc)) from exc
    if not capability.live_supported:
        return DirectReadOutcome(_base_result(
            request,
            capability,
            status="unavailable",
            source="unavailable",
            summary="Источник не относится к доступным read-only данным Яндекс.Директа.",
            limitations=["Для вывода нужен дополнительный источник данных."],
            error_code="adapter_unavailable",
        ))
    client = db.get(ClientAccount, client_id)
    if client is None:
        raise YandexDirectReadError("direct_no_data", "Client was not found.")
    campaign_ids = _resolve_campaign_ids(db, client_id, request.campaign_name)
    trusted = _trusted_spec(client, capability, request, campaign_ids)
    request_hash = _request_hash(trusted)
    if allow_cache and cache_policy != "fresh":
        cached = _cached_outcome(db, client_id, request, capability, request_hash)
        if cached:
            return cached
    if cache_policy == "cache_only":
        return DirectReadOutcome(_base_result(
            request,
            capability,
            status="insufficient_data",
            source="cache_only",
            request_hash=request_hash,
            freshness="cache_miss",
            summary="В кеше нет подходящих данных; live API отключён политикой cache_only.",
            limitations=["Для получения свежих данных запустите аудит с политикой fresh."],
            error_code="cache_miss",
        ))
    if not client.yandex_account_id or not client.direct_login:
        raise YandexDirectReadError("direct_auth_error", "Yandex account is not bound to this client.")
    account = db.get(ConnectedAccount, client.yandex_account_id)
    if account is None or account.provider != "yandex" or account.status != "connected":
        raise YandexDirectReadError("direct_auth_error", "Bound Yandex account is unavailable.")
    if not client.organization_id or account.organization_id != client.organization_id:
        raise YandexDirectReadError("direct_permission_denied", "Bound Yandex account belongs to another organization.")
    token = get_yandex_access_token_for_account(db, client.yandex_account_id)
    if not token:
        raise YandexDirectReadError("direct_auth_error", "Yandex OAuth token is unavailable.")
    connector = YandexDirectConnector(access_token=token, client_login=client.direct_login)
    logger.info(
        "DIRECT_READ_REQUEST_STARTED audit_job_id=%s capability_id=%s client_login_hash=%s "
        "request_hash=%s source_type=%s",
        audit_job_id, capability.id, _login_hash(client.direct_login), request_hash, capability.source_type,
    )
    try:
        if capability.source_type == "report":
            return _report_outcome(
                db, client_id, connector, request, capability, trusted, request_hash,
                audit_job_id=audit_job_id, cache_policy=cache_policy,
                account_id=client.yandex_account_id,
            )
        started_at = perf_counter()
        api_calls = 1
        if capability.service in {"audiencetargets", "retargetinglists"}:
            group_rows = connector.paginate_service_get(
                "adgroups",
                {"SelectionCriteria": {"CampaignIds": [int(item) for item in campaign_ids]}, "FieldNames": ["Id"]},
                maximum_rows=1000,
                page_size=500,
            )
            ad_group_ids = [int(item["Id"]) for item in group_rows if str(item.get("Id") or "").isdigit()]
            if ad_group_ids:
                target_rows = connector.paginate_service_get(
                    "audiencetargets",
                    {
                        "SelectionCriteria": {"AdGroupIds": ad_group_ids},
                        "FieldNames": ["Id", "AdGroupId", "RetargetingListId", "State", "StrategyPriority"],
                    },
                    maximum_rows=int(trusted["limit"]),
                    page_size=min(200, int(trusted["limit"])),
                )
                api_calls += 1
            else:
                target_rows = []
            if capability.service == "audiencetargets":
                rows = target_rows
            else:
                list_ids = sorted({
                    int(item["RetargetingListId"])
                    for item in target_rows
                    if str(item.get("RetargetingListId") or "").isdigit()
                })
                if list_ids:
                    rows = connector.paginate_service_get(
                        "retargetinglists",
                        {
                            "SelectionCriteria": {"Ids": list_ids},
                            "FieldNames": list(capability.api_fields),
                        },
                        maximum_rows=int(trusted["limit"]),
                        page_size=min(200, int(trusted["limit"])),
                    )
                    api_calls += 1
                else:
                    rows = []
        else:
            params = _service_params(capability, campaign_ids)
            rows = connector.paginate_service_get(
                capability.service or "",
                params,
                maximum_rows=int(trusted["limit"]),
                page_size=min(200, int(trusted["limit"])),
            )
        logger.info(
            "DIRECT_READ_REQUEST_COMPLETED audit_job_id=%s capability_id=%s request_hash=%s "
            "source_type=service_get elapsed_ms=%s rows=%s status=completed",
            audit_job_id, capability.id, request_hash, round((perf_counter() - started_at) * 1000), len(rows),
        )
        return _completed_outcome(
            db, client_id, request, capability, trusted, request_hash, rows, "yandex_direct_live_service", api_calls=api_calls,
        )
    except YandexDirectReadError as exc:
        logger.warning(
            "DIRECT_READ_REQUEST_FAILED audit_job_id=%s capability_id=%s client_login_hash=%s "
            "request_hash=%s source_type=%s error_code=%s",
            audit_job_id, capability.id, _login_hash(client.direct_login), request_hash,
            capability.source_type, exc.code,
        )
        return DirectReadOutcome(_base_result(
            request,
            capability,
            status="unavailable" if not exc.retryable else "failed",
            source="unavailable",
            request_hash=request_hash,
            summary=str(exc),
            error_code=exc.code,
            retryable=exc.retryable,
        ))
