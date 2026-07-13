import asyncio
import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompt_loader import get_system_prompt_metadata
from app.core.config import (
    AI_AUDIT_FINAL_MAX_TOKENS,
    AI_AUDIT_HELPER_MODEL,
    AI_AUDIT_MAX_OUTPUT_TOKENS,
    AI_AUDIT_PLANNER_MAX_TOKENS,
    AI_AUDIT_PLANNER_READ_TIMEOUT_SECONDS,
    AI_AUDIT_VERIFICATION_MAX_TOKENS,
    AI_AUDIT_VERIFICATION_READ_TIMEOUT_SECONDS,
    normalize_ai_audit_request_options,
)
from app.models import AiAuditJob, ClientAccount
from app.schemas import (
    AiAuditCreateRequest,
    AiAuditJobResponse,
    AiAuditResult,
    AuditDataRequest,
    AuditHypothesisVerification,
    AuditHypothesisVerificationSet,
    AuditInvestigationHypothesis,
    AuditInvestigationPlan,
)
from app.services.audit_data_tools import (
    MAX_AUDIT_DATA_REQUESTS,
    collect_audit_data_requests,
    public_audit_tool_manifest,
    validate_audit_data_requests,
)
from app.services.ai_prompt_debug import build_prompt_debug_snapshot, estimate_tokens
from app.services.ai_recommendations import build_client_ai_context_from_db
from app.services.direct_analyst_playbook import build_direct_analyst_instructions
from app.services.knowledge_base import select_knowledge_snippets
from app.services.openrouter import (
    DEFAULT_SYSTEM_PROMPT,
    OPENROUTER_AUDIT_TIMEOUT,
    generate_openrouter_response,
    redact_openrouter_debug_payload,
)

logger = logging.getLogger(__name__)

TERMINAL_AUDIT_STATUSES = {"completed", "failed", "cancelled"}
POLL_AFTER_MS = 1800
CONTEXT_TOKEN_TARGET = 12000
DRILLDOWN_TOKEN_TARGET = 18000
AUDIT_STAGE_LEASE_SECONDS = {
    "create_investigation_plan": 75,
    "verify_hypotheses": 85,
    "generate_answer": 180,
}
AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS = {
    "create_investigation_plan": 55,
    "verify_hypotheses": 65,
    "generate_answer": 165,
}
AUDIT_STAGE_PROVIDER_TIMEOUTS = {
    "create_investigation_plan": httpx.Timeout(
        connect=10.0,
        read=AI_AUDIT_PLANNER_READ_TIMEOUT_SECONDS,
        write=10.0,
        pool=10.0,
    ),
    "verify_hypotheses": httpx.Timeout(
        connect=10.0,
        read=AI_AUDIT_VERIFICATION_READ_TIMEOUT_SECONDS,
        write=10.0,
        pool=10.0,
    ),
    "generate_answer": OPENROUTER_AUDIT_TIMEOUT,
}
HEAVY_AUDIT_MARKERS = (
    "полный аудит",
    "аудит всего аккаунта",
    "аудит по чеклисту",
    "аудит по чек-листу",
    "проведи аудит",
    "все критические проблемы",
    "покажи критические проблемы",
    "комплексный анализ",
    "полный разбор кампаний",
)


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


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _as_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def requires_staged_audit(message: str) -> bool:
    normalized = " ".join(str(message or "").lower().replace("ё", "е").split())
    return any(marker in normalized for marker in HEAVY_AUDIT_MARKERS)


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else round(parsed, 2)


def _flags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:100] for item in value[:10]]
    if isinstance(value, str):
        return [item.strip()[:100] for item in value.split(",") if item.strip()][:10]
    return []


def _safe_business_fields(value: Any) -> dict[str, str]:
    fields = value if isinstance(value, dict) else {}
    allowed = {
        "brand_name",
        "business_niche",
        "product_summary",
        "target_audience",
        "geography",
        "seasonality",
        "main_offers",
        "conversion_actions",
        "average_order_value",
        "lead_value_notes",
        "business_constraints",
        "negative_topics",
        "landing_page_notes",
        "competitor_notes",
        "manual_notes",
    }
    return {key: str(fields[key])[:1200] for key in allowed if str(fields.get(key) or "").strip()}


def _draft_action_snapshot(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    return {
        "severity": item.get("severity"),
        "campaign": item.get("campaign_name"),
        "issue": str(item.get("issue") or "")[:500],
        "evidence": str(item.get("evidence") or "")[:700],
        "draftAction": str(item.get("draft_action") or "")[:700],
        "requiresApproval": True,
        "canApplyAutomatically": False,
    }


def _campaign_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("campaign_name") or item.get("campaignName") or item.get("name") or "Кампания без названия",
        "type": item.get("campaign_type") or item.get("campaignType") or "unknown",
        "severity": item.get("severity") or "ok",
        "cost": _number(item.get("cost")),
        "impressions": _number(item.get("impressions")),
        "clicks": _number(item.get("clicks")),
        "ctr": _number(item.get("ctr")),
        "cpc": _number(item.get("cpc") or item.get("avg_cpc")),
        "goalConversions": _number(item.get("conversions_used") or item.get("goal_conversions")),
        "goalCpa": _number(item.get("cpa_used") or item.get("goal_cpa")),
        "conversionRate": _number(item.get("conversion_rate")),
        "flags": _flags(item.get("issue_flags")),
        "diagnostic": item.get("diagnostic_explanation"),
        "recommendedFocus": item.get("recommended_focus"),
    }


def _parse_iso_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _analysis_period(context: dict[str, Any], requested_period: str) -> dict[str, Any]:
    dynamics = context.get("campaign_dynamics_analysis") if isinstance(context.get("campaign_dynamics_analysis"), dict) else {}
    dynamics_period = dynamics.get("period") if isinstance(dynamics.get("period"), dict) else {}
    windows = dynamics_period.get("windows") if isinstance(dynamics_period.get("windows"), dict) else {}
    requested_key = {"last_7_days": "last7", "last_14_days": "last14", "last_30_days": "last30"}.get(requested_period, "last30")
    comparison_key = {"last7": "previous7", "last14": "previous14"}.get(requested_key)
    selected = windows.get(requested_key) if isinstance(windows.get(requested_key), dict) else {}
    comparison = windows.get(comparison_key) if comparison_key and isinstance(windows.get(comparison_key), dict) else {}
    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    summary_period = summary.get("period") if isinstance(summary.get("period"), dict) else {}
    date_from = selected.get("dateFrom") or summary_period.get("from")
    date_to = selected.get("dateTo") or summary_period.get("to")
    parsed_from = _parse_iso_date(date_from)
    parsed_to = _parse_iso_date(date_to)
    days = (parsed_to.date() - parsed_from.date()).days + 1 if parsed_from and parsed_to else None
    comparison_from = comparison.get("dateFrom")
    comparison_to = comparison.get("dateTo")
    if not comparison_from and parsed_from and days:
        comparison_to_date = parsed_from.date() - timedelta(days=1)
        comparison_from_date = comparison_to_date - timedelta(days=days - 1)
        comparison_from = comparison_from_date.isoformat()
        comparison_to = comparison_to_date.isoformat()
    expected_days = {"last_7_days": 7, "last_14_days": 14, "last_30_days": 30}.get(requested_period)
    data_quality = dynamics.get("dataQuality") or {}
    data_rows = int(data_quality.get("rows") or 0)
    missing_days = data_quality.get("missingDays") or []
    latest_sync = context.get("latest_sync_job") if isinstance(context.get("latest_sync_job"), dict) else {}
    client = context.get("client") if isinstance(context.get("client"), dict) else {}
    return {
        "preset": requested_period,
        "dateFrom": str(date_from)[:10] if date_from else None,
        "dateTo": str(date_to)[:10] if date_to else None,
        "days": days,
        "comparisonDateFrom": str(comparison_from)[:10] if comparison_from else None,
        "comparisonDateTo": str(comparison_to)[:10] if comparison_to else None,
        "source": "synced_campaign_daily_stats" if data_rows else ("synced_campaign_period_stats" if date_from else "unavailable"),
        "lastSyncedAt": client.get("last_synced_at") or latest_sync.get("finished_at") or latest_sync.get("created_at"),
        "requestedMatchesAvailableData": bool(
            date_from
            and date_to
            and (expected_days is None or days == expected_days)
            and not missing_days
        ),
    }


def _coverage_item(
    *,
    available: bool,
    total: int | None = None,
    analyzed: int = 0,
    source: str | None = None,
    period: dict[str, Any] | None = None,
    reason: str | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "available": available,
        "total": total,
        "analyzed": analyzed,
        "source": source,
        "period": period,
        "reason": reason,
        "limitations": limitations or [],
    }


def _data_coverage(
    context: dict[str, Any],
    *,
    analysis_period: dict[str, Any],
    campaigns_total: int,
    campaigns_analyzed: int,
    search_total: int,
    search_analyzed: int,
) -> dict[str, Any]:
    period = {"dateFrom": analysis_period.get("dateFrom"), "dateTo": analysis_period.get("dateTo")}
    goals = context.get("goals") if isinstance(context.get("goals"), dict) else {}
    not_collected = lambda: _coverage_item(available=False, reason="not_collected", period=period)
    return {
        "account": _coverage_item(available=campaigns_total > 0, total=1 if campaigns_total else 0, analyzed=1 if campaigns_analyzed else 0, source="performance_summary", period=period),
        "campaigns": _coverage_item(available=campaigns_total > 0, total=campaigns_total, analyzed=campaigns_analyzed, source="direct_campaign_stats", period=period),
        "adGroups": not_collected(),
        "keywords": not_collected(),
        "searchQueries": _coverage_item(available=search_total > 0, total=search_total, analyzed=search_analyzed, source="direct_search_query_stats" if search_total else None, period=period, reason=None if search_total else "not_collected"),
        "placements": not_collected(),
        "audiences": not_collected(),
        "adsAndCreatives": not_collected(),
        "demographics": not_collected(),
        "devices": not_collected(),
        "geo": not_collected(),
        "goals": _coverage_item(available=bool(goals.get("selected_goal_ids")), total=len(goals.get("selected_goal_ids") or []), analyzed=len(goals.get("selected_goal_ids") or []) if goals.get("has_goal_data") else 0, source="yandex_direct_goals" if goals.get("has_goal_data") else None, period=period, reason=None if goals.get("has_goal_data") else "goal_data_unavailable"),
        "crmLeadQuality": not_collected(),
    }


def _query_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": item.get("query"),
        "campaign": item.get("campaign") or item.get("campaign_name"),
        "adGroup": item.get("adGroup") or item.get("ad_group_name"),
        "cost": _number(item.get("cost")),
        "clicks": _number(item.get("clicks")),
        "goalConversions": _number(item.get("goalConversions") or item.get("goal_conversions")),
        "flags": _flags(item.get("issueFlags") or item.get("issue_flags")),
        "reason": item.get("reason") or item.get("recommendation_reason"),
        "confidence": item.get("confidence"),
        "draftNegativeKeyword": item.get("recommendedNegativeKeyword") or item.get("recommended_negative_keyword"),
    }


def _campaign_classification(name: str, explicit_type: str | None = None) -> dict[str, str]:
    normalized = f"{explicit_type or ''} {name}".lower().replace("ё", "е")
    is_retargeting = any(marker in normalized for marker in ("ретарг", "retarget", "ремаркет"))
    is_yan = any(marker in normalized for marker in ("рся", "yan", "сети", "network"))
    is_brand = any(marker in normalized for marker in ("бренд", "brand"))
    if is_yan:
        return {"campaign_name": name, "campaign_family": "yan", "campaign_subtype": "yan_retargeting" if is_retargeting else "yan_prospecting"}
    if any(marker in normalized for marker in ("поиск", "search")) or is_brand:
        return {"campaign_name": name, "campaign_family": "search", "campaign_subtype": "brand_search" if is_brand else "search"}
    return {"campaign_name": name, "campaign_family": "unknown", "campaign_subtype": "unknown"}


def classify_audit_campaigns(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    result = []
    seen = set()
    for items in (snapshot.get("campaignGroups") or {}).values():
        for item in items or []:
            name = str(item.get("name") or "Кампания без названия")
            if name in seen:
                continue
            seen.add(name)
            result.append(_campaign_classification(name, item.get("type")))
    return result


def _request(
    hypothesis_id: str,
    classification: dict[str, str],
    dimension: str,
    reason: str,
    period: dict[str, Any],
    *,
    priority: str = "medium",
    required: bool = False,
) -> AuditDataRequest:
    metrics_by_dimension = {
        "search_queries": ["query", "impressions", "clicks", "cost", "conversions", "cpa"],
        "ad_groups": ["ad_group_name", "impressions", "clicks", "cost", "conversions", "cpa"],
        "goals": ["goal_ids", "clicks", "cost", "conversions", "cpa", "conversion_rate"],
        "placements": ["impressions", "clicks", "cost", "conversions", "cpa"],
        "audiences": ["impressions", "clicks", "cost", "conversions", "cpa"],
        "retargeting_segments": ["impressions", "clicks", "cost", "conversions", "cpa"],
    }
    return AuditDataRequest(
        request_id=f"req_{hypothesis_id}_{dimension}",
        hypothesis_id=hypothesis_id,
        campaign_name=classification["campaign_name"],
        campaign_family=classification["campaign_family"],
        campaign_subtype=classification["campaign_subtype"],
        dimension=dimension,
        reason=reason,
        period={
            "date_from": period.get("dateFrom"), "date_to": period.get("dateTo"), "days": period.get("days"),
            "comparison_date_from": period.get("comparisonDateFrom"), "comparison_date_to": period.get("comparisonDateTo"),
        },
        filters={"campaign_name": classification["campaign_name"]},
        metrics=metrics_by_dimension.get(dimension, ["impressions", "clicks", "cost", "conversions", "cpa"]),
        priority=priority,
        required_for_conclusion=required,
    )


def build_rule_based_investigation_plan(snapshot: dict[str, Any]) -> AuditInvestigationPlan:
    classifications = {item["campaign_name"]: item for item in classify_audit_campaigns(snapshot)}
    candidates = []
    for group_name in ("critical", "warning"):
        candidates.extend((snapshot.get("campaignGroups") or {}).get(group_name) or [])
    period = snapshot.get("analysisPeriod") or {}
    hypotheses = []
    for index, item in enumerate(candidates[:5], start=1):
        name = str(item.get("name") or "Кампания без названия")
        classification = classifications[name]
        flags = item.get("flags") or []
        fact = str(item.get("diagnostic") or f"Сигналы: {', '.join(flags) or 'требуется проверка'}")[:700]
        hypothesis_id = f"hyp_{index:03d}"
        requests = [_request(hypothesis_id, classification, "goals", "Проверить выбранные цели и CPA по ним.", period, priority="high", required=True)]
        if classification["campaign_subtype"] in {"search", "brand_search"}:
            requests.extend([
                _request(hypothesis_id, classification, "search_queries", "Проверить интент и расход поисковых запросов.", period, priority="high", required=True),
                _request(hypothesis_id, classification, "ad_groups", "Локализовать проблему по группам объявлений.", period),
            ])
            hypothesis = "Качество поискового трафика или отдельных групп может объяснять отклонение метрик."
        elif classification["campaign_subtype"] == "yan_retargeting":
            requests.extend([
                _request(hypothesis_id, classification, "retargeting_segments", "Сравнить сегменты и окна ретаргетинга.", period, priority="high", required=True),
                _request(hypothesis_id, classification, "placements", "Проверить площадки с расходом без целевых конверсий.", period),
            ])
            hypothesis = "Сегменты ретаргетинга или площадки могут снижать эффективность кампании."
        elif classification["campaign_family"] == "yan":
            requests.extend([
                _request(hypothesis_id, classification, "placements", "Проверить площадки с неэффективным расходом.", period, priority="high", required=True),
                _request(hypothesis_id, classification, "audiences", "Сравнить доступные аудитории.", period),
            ])
            hypothesis = "Качество площадок или аудиторий может объяснять отклонение метрик."
        else:
            hypothesis = "Тип кампании не определён; сначала нужны безопасные данные по целям."
        hypotheses.append(AuditInvestigationHypothesis(
            hypothesis_id=hypothesis_id,
            campaign_name=name,
            campaign_family=classification["campaign_family"],
            campaign_subtype=classification["campaign_subtype"],
            observed_fact=fact,
            hypothesis=hypothesis,
            data_requests=requests[:4],
        ))
    return AuditInvestigationPlan(hypotheses=hypotheses)


def build_investigation_planner_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build the small, non-sensitive context used only by the optional AI planner."""

    selected_campaigns: list[dict[str, Any]] = []
    for group_name in ("critical", "warning"):
        for campaign in (snapshot.get("campaignGroups") or {}).get(group_name) or []:
            if len(selected_campaigns) >= 5:
                break
            selected_campaigns.append({"group": group_name, **dict(campaign)})
    selected_names = {str(item.get("name") or "") for item in selected_campaigns}
    classifications = [
        item
        for item in (snapshot.get("campaignClassifications") or [])
        if str(item.get("campaign_name") or "") in selected_names
    ]
    tracking = snapshot.get("trackingStatus") or {}
    return {
        "analysisPeriod": snapshot.get("analysisPeriod") or {},
        "accountTotals": snapshot.get("accountTotals") or {},
        "targetKpis": snapshot.get("targetKpis") or {},
        "campaigns": selected_campaigns,
        "campaignClassifications": classifications,
        "dataCoverage": snapshot.get("dataCoverage") or {},
        "ruleBasedInvestigationPlan": snapshot.get("ruleBasedInvestigationPlan") or {},
        "publicToolManifest": public_audit_tool_manifest(),
        "missingData": (snapshot.get("missingData") or [])[:10],
        "trackingWarnings": (tracking.get("warnings") or [])[:10],
    }


def should_call_ai_investigation_planner(
    base_plan: AuditInvestigationPlan,
    snapshot: dict[str, Any],
) -> bool:
    if not base_plan.hypotheses:
        return False
    if all(item.campaign_family == "unknown" for item in base_plan.hypotheses):
        return False
    requests = [request for item in base_plan.hypotheses for request in item.data_requests]
    if len(requests) >= MAX_AUDIT_DATA_REQUESTS:
        return False
    supported_dimensions = {
        str(item.get("id"))
        for item in public_audit_tool_manifest()
        if item.get("supported_now")
    }
    if not any(request.dimension in supported_dimensions for request in requests):
        return False
    groups = snapshot.get("campaignGroups") or {}
    return bool((groups.get("critical") or []) + (groups.get("warning") or []))


def build_investigation_plan_prompt(snapshot: dict[str, Any], base_plan: AuditInvestigationPlan) -> str:
    planner_context = build_investigation_planner_context(snapshot)
    return f"""Дополни безопасный read-only investigation plan. Не формируй аудит или рекомендации.
Backend-план обязателен: не удаляй required_for_conclusion запросы. Разрешено кратко уточнить reason/priority,
убрать только необязательный нерелевантный запрос или добавить dimension из publicToolManifest.
Максимум 5 гипотез, 4 data requests на гипотезу и {MAX_AUDIT_DATA_REQUESTS} запросов всего.
Не передавай campaign ID, endpoint, token или credentials. Верни только JSON AuditInvestigationPlan без Markdown.

Planner context:
{json.dumps(planner_context, ensure_ascii=False, separators=(',', ':'))}"""


def _merge_investigation_plans(
    proposed: AuditInvestigationPlan,
    snapshot: dict[str, Any],
    fallback: AuditInvestigationPlan,
) -> AuditInvestigationPlan:
    classifications = {item["campaign_name"]: item for item in (snapshot.get("campaignClassifications") or [])}
    proposed_by_campaign = {item.campaign_name: item for item in proposed.hypotheses}
    normalized: list[AuditInvestigationHypothesis] = []
    for hypothesis_index, base_hypothesis in enumerate(fallback.hypotheses[:5], start=1):
        classification = classifications.get(base_hypothesis.campaign_name)
        if not classification:
            continue
        proposed_hypothesis = proposed_by_campaign.get(base_hypothesis.campaign_name)
        proposed_requests = {
            request.dimension: request
            for request in (proposed_hypothesis.data_requests if proposed_hypothesis else [])
        }
        requests: list[AuditDataRequest] = []
        included_dimensions: set[str] = set()
        for base_request in base_hypothesis.data_requests:
            proposed_request = proposed_requests.get(base_request.dimension)
            if proposed_hypothesis and not base_request.required_for_conclusion and not proposed_request:
                continue
            payload = base_request.model_dump()
            if proposed_request:
                payload["reason"] = str(proposed_request.reason)[:500]
                payload["priority"] = proposed_request.priority
            payload.update({
                "request_id": f"req_{hypothesis_index:03d}_{len(requests) + 1:02d}",
                "hypothesis_id": f"hyp_{hypothesis_index:03d}",
                "campaign_name": base_hypothesis.campaign_name,
                "campaign_family": classification["campaign_family"],
                "campaign_subtype": classification["campaign_subtype"],
                "filters": {"campaign_name": base_hypothesis.campaign_name},
            })
            requests.append(AuditDataRequest.model_validate(payload))
            included_dimensions.add(base_request.dimension)
        for proposed_request in proposed_hypothesis.data_requests if proposed_hypothesis else []:
            if proposed_request.dimension in included_dimensions or len(requests) >= 4:
                continue
            payload = proposed_request.model_dump()
            payload.update({
                "request_id": f"req_{hypothesis_index:03d}_{len(requests) + 1:02d}",
                "hypothesis_id": f"hyp_{hypothesis_index:03d}",
                "campaign_name": base_hypothesis.campaign_name,
                "campaign_family": classification["campaign_family"],
                "campaign_subtype": classification["campaign_subtype"],
                "filters": {"campaign_name": base_hypothesis.campaign_name},
                "required_for_conclusion": False,
            })
            requests.append(AuditDataRequest.model_validate(payload))
            included_dimensions.add(proposed_request.dimension)
        normalized.append(AuditInvestigationHypothesis(
            hypothesis_id=f"hyp_{hypothesis_index:03d}",
            campaign_name=base_hypothesis.campaign_name,
            campaign_family=classification["campaign_family"],
            campaign_subtype=classification["campaign_subtype"],
            observed_fact=base_hypothesis.observed_fact,
            hypothesis=(
                str(proposed_hypothesis.hypothesis)[:700]
                if proposed_hypothesis
                else base_hypothesis.hypothesis
            ),
            data_requests=requests,
        ))
    return AuditInvestigationPlan(hypotheses=normalized) if normalized else fallback


def _parse_investigation_plan(
    answer: str,
    snapshot: dict[str, Any],
    fallback: AuditInvestigationPlan,
) -> tuple[AuditInvestigationPlan, bool]:
    try:
        proposed = AuditInvestigationPlan.model_validate_json(answer)
        if not proposed.hypotheses:
            return fallback, False
        return _merge_investigation_plans(proposed, snapshot, fallback), True
    except (TypeError, ValueError):
        return fallback, False


def _normalized_investigation_plan(answer: str, snapshot: dict[str, Any], fallback: AuditInvestigationPlan) -> AuditInvestigationPlan:
    return _parse_investigation_plan(answer, snapshot, fallback)[0]


def build_verification_prompt(snapshot: dict[str, Any]) -> str:
    return f"""Проверь максимум 5 гипотез только по собранным read-only данным. Ответ должен быть кратким.
Верни только JSON объекта
{{"verifications":[{{"hypothesis_id":"hyp_001","status":"confirmed|partially_confirmed|rejected|unverified|not_applicable","verification_summary":"...","supporting_evidence":[],"contradicting_evidence":[],"limitations":[],"remaining_data_needed":[]}}]}}.
Не подтверждай гипотезу из-за правдоподобия. unavailable/insufficient_data означает unverified; все not_applicable означает not_applicable.
Investigation plan: {json.dumps(snapshot.get('investigationPlan') or {}, ensure_ascii=False)}
Data request results: {json.dumps(snapshot.get('drilldownResults') or [], ensure_ascii=False)}"""


def _verification_fallback(snapshot: dict[str, Any]) -> AuditHypothesisVerificationSet:
    results = snapshot.get("drilldownResults") or []
    verifications = []
    for hypothesis in (snapshot.get("investigationPlan") or {}).get("hypotheses", []):
        related = [item for item in results if item.get("hypothesis_id") == hypothesis.get("hypothesis_id")]
        statuses = {item.get("status") for item in related}
        status_value = "not_applicable" if statuses == {"not_applicable"} else "unverified"
        verifications.append(AuditHypothesisVerification(
            hypothesis_id=hypothesis.get("hypothesis_id"), status=status_value,
            verification_summary="AI-проверка недоступна; backend не считает гипотезу подтверждённой.",
            limitations=[item.get("summary") for item in related if item.get("status") != "collected" and item.get("summary")][:5],
            remaining_data_needed=[item.get("dimension") for item in related if item.get("status") != "collected"][:5],
        ))
    return AuditHypothesisVerificationSet(verifications=verifications)


def _parse_verifications(answer: str, snapshot: dict[str, Any]) -> tuple[AuditHypothesisVerificationSet, bool]:
    try:
        parsed = AuditHypothesisVerificationSet.model_validate_json(answer)
    except ValueError:
        return _verification_fallback(snapshot), False
    hypotheses = (snapshot.get("investigationPlan") or {}).get("hypotheses", [])
    expected = {item.get("hypothesis_id") for item in hypotheses}
    request_required = {
        request.get("request_id"): bool(request.get("required_for_conclusion"))
        for hypothesis in hypotheses
        for request in hypothesis.get("data_requests", [])
    }
    safe = []
    for item in parsed.verifications:
        if item.hypothesis_id not in expected:
            continue
        related = [result for result in (snapshot.get("drilldownResults") or []) if result.get("hypothesis_id") == item.hypothesis_id]
        collected = [result for result in related if result.get("status") == "collected"]
        missing_required = any(
            request_required.get(result.get("request_id")) and result.get("status") != "collected"
            for result in related
        )
        if not collected:
            item.status = "not_applicable" if related and all(result.get("status") == "not_applicable" for result in related) else "unverified"
        elif item.status == "confirmed" and missing_required:
            item.status = "partially_confirmed"
            item.limitations.append("Backend не получил все обязательные data requests; статус понижен до partially_confirmed.")
        safe.append(item)
    if not safe:
        return _verification_fallback(snapshot), False
    return AuditHypothesisVerificationSet(verifications=safe), True


def _normalized_verifications(answer: str, snapshot: dict[str, Any]) -> AuditHypothesisVerificationSet:
    return _parse_verifications(answer, snapshot)[0]


def _second_round_requests(snapshot: dict[str, Any]) -> list[AuditDataRequest]:
    runtime = _audit_runtime(snapshot)
    if int(runtime.get("investigationRound") or 1) >= 2 or int(runtime.get("requestsCount") or 0) >= 15:
        return []
    critical_names = {str(item.get("name")) for item in (snapshot.get("campaignGroups") or {}).get("critical", [])}
    required_request_ids = {
        request.get("request_id")
        for hypothesis in (snapshot.get("investigationPlan") or {}).get("hypotheses", [])
        for request in hypothesis.get("data_requests", [])
        if request.get("required_for_conclusion")
    }
    insufficient_hypotheses = {
        item.get("hypothesis_id")
        for item in (snapshot.get("drilldownResults") or [])
        if item.get("status") == "insufficient_data" and item.get("request_id") in required_request_ids
    }
    plan_hypotheses = {
        item.get("hypothesis_id"): item
        for item in (snapshot.get("investigationPlan") or {}).get("hypotheses", [])
    }
    eligible_campaigns = {
        item.get("campaign_name")
        for hypothesis_id, item in plan_hypotheses.items()
        if hypothesis_id in insufficient_hypotheses and item.get("campaign_name") in critical_names
    }
    if not eligible_campaigns:
        return []
    existing = {
        (item.get("campaign_name"), item.get("dimension"))
        for item in (snapshot.get("validatedDataRequests") or [])
    }
    candidates = []
    for hypothesis in (snapshot.get("ruleBasedInvestigationPlan") or {}).get("hypotheses", []):
        if hypothesis.get("campaign_name") not in eligible_campaigns:
            continue
        for request in hypothesis.get("data_requests", []):
            key = (request.get("campaign_name"), request.get("dimension"))
            if key in existing or not (request.get("required_for_conclusion") or request.get("priority") == "high"):
                continue
            candidates.append(AuditDataRequest.model_validate(request))
    remaining = max(0, 15 - int(runtime.get("requestsCount") or 0))
    accepted, rejected = validate_audit_data_requests(candidates[:remaining])
    if rejected:
        snapshot["drilldownResults"] = (snapshot.get("drilldownResults") or []) + [item.model_dump(mode="json") for item in rejected]
    return accepted


def build_compact_audit_context(
    context: dict[str, Any],
    *,
    requested_period: str = "last_30_days",
    options: dict[str, Any] | None = None,
    token_target: int = CONTEXT_TOKEN_TARGET,
) -> dict[str, Any]:
    options = options or {}
    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    campaigns = context.get("campaigns") if isinstance(context.get("campaigns"), list) else []
    groups = {key: [] for key in ["critical", "warning", "opportunity", "low_data", "stable"]}
    for raw_item in campaigns:
        if not isinstance(raw_item, dict):
            continue
        item = _campaign_snapshot(raw_item)
        flags = set(item.get("flags") or [])
        severity = str(item.get("severity") or "ok")
        if "low_data" in flags:
            group = "low_data"
        elif severity == "critical":
            group = "critical"
        elif severity == "warning":
            group = "warning"
        elif "promising_campaign" in flags or severity == "info":
            group = "opportunity"
        else:
            group = "stable"
        groups[group].append(item)
    for items in groups.values():
        items.sort(key=lambda item: float(item.get("cost") or 0), reverse=True)
        del items[5:]

    search = context.get("search_query_insights") if isinstance(context.get("search_query_insights"), dict) else {}
    search_items = search.get("insights") if isinstance(search.get("insights"), list) else []
    query_risks = [_query_snapshot(item) for item in search_items[:10] if isinstance(item, dict)] if options.get("include_search_queries", True) else []
    dynamics = context.get("campaign_dynamics_analysis") if isinstance(context.get("campaign_dynamics_analysis"), dict) else {}
    business = context.get("business_context") if isinstance(context.get("business_context"), dict) else {}
    audit = context.get("yandex_direct_audit") if isinstance(context.get("yandex_direct_audit"), dict) else {}
    goals = context.get("goals") if isinstance(context.get("goals"), dict) else {}
    diagnostics = context.get("sync_diagnostics") if isinstance(context.get("sync_diagnostics"), dict) else {}
    warnings = [str(item)[:500] for item in (context.get("warnings") or [])[:10]]
    missing_data = [str(item)[:500] for item in (dynamics.get("missingData") or [])[:10]]
    if business.get("status") == "empty":
        missing_data.append("Контекст бизнеса не заполнен.")
    if not goals.get("has_goal_data"):
        missing_data.append("Нет подтверждённых конверсий по выбранным целям.")
    analysis_period = _analysis_period(context, requested_period)
    if not analysis_period.get("requestedMatchesAvailableData"):
        warnings.append("Запрошенный период не полностью совпадает с доступными данными; указан фактический диапазон анализа.")
    campaigns_analyzed = sum(len(items) for items in groups.values())
    data_coverage = _data_coverage(
        context,
        analysis_period=analysis_period,
        campaigns_total=len(campaigns),
        campaigns_analyzed=campaigns_analyzed,
        search_total=int(search.get("totalQueries") or len(search_items)),
        search_analyzed=len(query_risks),
    )

    snapshot = {
        "client": {
            "name": (context.get("client") or {}).get("name"),
            "directLogin": (context.get("client") or {}).get("direct_login"),
            "targetCpa": (context.get("client") or {}).get("target_cpa"),
        },
        "businessContext": {
            "status": business.get("status"),
            "fields": _safe_business_fields(business.get("fields")),
        },
        "analysisPeriod": analysis_period,
        "dataCoverage": data_coverage,
        "accountTotals": summary.get("totals") or {},
        "targetKpis": {"targetCpa": (context.get("client") or {}).get("target_cpa")},
        "selectedGoals": {
            "ids": goals.get("selected_goal_ids") or [],
            "hasGoalData": bool(goals.get("has_goal_data")),
            "message": goals.get("source_message"),
        },
        "campaignGroups": groups,
        "trackingStatus": {
            "syncDiagnostics": diagnostics,
            "warnings": list(dict.fromkeys(warnings)),
        },
        "searchQueryRisks": query_risks,
        "periodComparison": {
            "dataQuality": dynamics.get("dataQuality") or {},
            "worstCampaigns": [_campaign_snapshot(item) for item in (dynamics.get("worstCampaigns") or [])[:5] if isinstance(item, dict)],
            "bestCampaigns": [_campaign_snapshot(item) for item in (dynamics.get("bestCampaigns") or [])[:5] if isinstance(item, dict)],
        } if options.get("include_dynamics", True) else {},
        "auditFramework": {
            "score": audit.get("score"),
            "grade": audit.get("grade"),
            "criticalIssues": (audit.get("criticalIssues") or [])[:5],
            "quickWins": (audit.get("quickWins") or [])[:5],
            "limitations": (audit.get("limitations") or [])[:10],
        },
        "draftActions": [
            compact
            for compact in (_draft_action_snapshot(item) for item in (context.get("optimization_plan") or [])[:10])
            if compact
        ] if options.get("include_recommendations", True) else [],
        "missingData": list(dict.fromkeys(missing_data)),
        "limitations": [
            "Аудит использует сохранённые read-only данные DirectPilot и не применяет изменения.",
            "Полные сырые ответы Яндекса, журнал и все поисковые запросы в AI-контекст не включаются.",
        ],
        "safeDrillDownPlan": [
            "Проверить критические кампании на уровне запросов, площадок, устройств и географии по доступным данным.",
            "Проверить корректность выбранных целей и качество лидов до бюджетных решений.",
            "Любые изменения подготовить как dry-run черновик для ручного approval.",
        ],
    }
    metadata = {
        "campaignsTotal": len(campaigns),
        "campaignsIncluded": campaigns_analyzed,
        "searchQueriesTotal": int(search.get("totalQueries") or len(search_items)),
        "searchQueriesIncluded": len(query_risks),
        "tokenTarget": token_target,
        "truncated": len(campaigns) > sum(len(items) for items in groups.values()) or len(search_items) > len(query_risks),
        "omittedSections": ["raw_api_responses", "full_journal", "all_search_queries", "oauth_credentials"],
    }
    snapshot["metadata"] = metadata
    metadata["estimatedTokens"] = estimate_tokens(_json_dump(snapshot))
    if metadata["estimatedTokens"] > token_target:
        for key in groups:
            groups[key] = groups[key][:3]
        snapshot["searchQueryRisks"] = query_risks[:5]
        snapshot["periodComparison"] = {"dataQuality": (snapshot.get("periodComparison") or {}).get("dataQuality", {})}
        metadata["campaignsIncluded"] = sum(len(items) for items in groups.values())
        metadata["searchQueriesIncluded"] = len(snapshot["searchQueryRisks"])
        metadata["truncated"] = True
        metadata["omittedSections"].append("detailed_period_comparison")
        metadata["estimatedTokens"] = estimate_tokens(_json_dump(snapshot))
        snapshot["dataCoverage"]["campaigns"]["analyzed"] = metadata["campaignsIncluded"]
        snapshot["dataCoverage"]["searchQueries"]["analyzed"] = metadata["searchQueriesIncluded"]
    return snapshot


def _audit_result_contract(output_budget_tokens: int) -> dict[str, Any]:
    finding = {
        "hypothesis_id": "hyp_001 или null для чистого факта",
        "verification_status": "confirmed|partially_confirmed|rejected|unverified|not_applicable",
        "campaign_name": "Название кампании или null",
        "campaign_type": "search|yan|retargeting|master_campaign|unknown",
        "analysis_level": "campaign|ad_group|keyword|query|placement|audience|device|geo|demographic|tracking",
        "problem": "Краткая проблема",
        "fact": "Факт из данных",
        "evidence": ["До 5 коротких доказательств с метриками"],
        "hypothesis": "Возможная причина или null",
        "confidence": "low|medium|high",
        "risk": "low|medium|high",
        "recommendation": "Конкретный следующий шаг",
        "requires_human_approval": True,
        "next_data_needed": [],
    }
    return {
        "meta": {"period": {}, "data_coverage": {}, "model": None, "output_budget_tokens": output_budget_tokens},
        "executive_summary": "Краткий итог без вступления о роли AI",
        "data_quality": {"status": "sufficient|partial|insufficient", "facts": [], "limitations": []},
        "critical_findings": [finding],
        "opportunities": [finding],
        "insufficient_data_campaigns": [],
        "tracking_and_goals": {},
        "drilldown_summary": {"analyzed_levels": [], "not_analyzed_levels": [], "next_data_needed": []},
        "action_plan": [{"priority": 1, "hypothesis_id": "hyp_001 или null", "action": "...", "scope": "...", "reason": "...", "mode": "manual_review|dry_run", "requires_human_approval": True}],
        "prohibited_actions": [],
        "limitations": [],
        "conclusion": "Итоговый вывод",
    }


def build_full_audit_prompt(
    snapshot: dict[str, Any],
    *,
    output_budget_tokens: int = AI_AUDIT_MAX_OUTPUT_TOKENS,
    compact_retry: bool = False,
) -> str:
    knowledge = select_knowledge_snippets("полный аудит Яндекс Директ критические проблемы tracking поисковые запросы", snapshot, limit=4)
    knowledge_text = "\n".join(
        f"- {item.get('title') or item.get('id')}: {str(item.get('content') or item.get('text') or '')[:800]}"
        for item in knowledge
    )
    scope_instruction = (
        "Сфокусируй итог на критических проблемах, но сохрани раздел качества данных и safety."
        if snapshot.get("requestedScope") == "critical_issues"
        else "Проведи полный аудит аккаунта по всем доступным разделам."
    )
    compact_retry_instruction = (
        "Это повтор после достижения лимита. Сохрани все обязательные разделы, но сократи evidence и количество примеров; обязательно закончи conclusion и limitations."
        if compact_retry
        else ""
    )
    return f"""Задача: провести полный read-only аудит Яндекс.Директа по сохранённому compact snapshot DirectPilot.
Scope: {scope_instruction}
Доступный максимум ответа — {output_budget_tokens} токенов. Это потолок, а не целевой объём. Дай полный, но компактный ответ.
Не обрывай разделы и finding. Если данных много, сокращай второстепенные примеры и повторяющиеся evidence.
Зарезервируй место для action_plan, limitations и conclusion. {compact_retry_instruction}

{build_direct_analyst_instructions(snapshot)}

Релевантные фрагменты базы знаний:
{knowledge_text or '- Дополнительные фрагменты не выбраны.'}

Compact audit snapshot:
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

Верни только один валидный JSON-объект без Markdown fences и текста до/после JSON.
Строгий контракт результата:
{json.dumps(_audit_result_contract(output_budget_tokens), ensure_ascii=False, indent=2)}

Ограничения контракта: critical_findings ≤ 5, opportunities ≤ 5, action_plan ≤ 10, evidence в finding ≤ 5.
Начинай анализ с фактического analysisPeriod и dataCoverage из snapshot. Не пиши вступление о роли AI.
Используй только названия кампаний. Не выводи CampaignId, client_id, organization_id, job_id и любые внутренние object IDs.
Если название отсутствует, используй «Кампания без названия». Если уровень данных не собран, укажи «не анализировался».
Одна проблема — один finding. Не повторяй одинаковые цифры и safety-ограничения в разных finding.
Факт и evidence должны содержать конкретные метрики; hypothesis не должна повторять problem; recommendation должна быть конкретной.
Причину называй установленной только при verified status confirmed или partially_confirmed.
Rejected hypothesis не включай в recommendation. Unverified явно подпиши как неподтверждённую и предлагай только безопасный сбор данных.
Not_applicable не показывай как проблему. Action plan основывай только на фактах и подтверждённых/частично подтверждённых причинах.
Не выдумывай отсутствующие данные. Все действия — dry-run черновики; изменения в Яндекс.Директ не применялись."""


def _trusted_result_meta(snapshot: dict[str, Any], job: AiAuditJob, response: dict[str, Any]) -> dict[str, Any]:
    period = snapshot.get("analysisPeriod") or {}
    return {
        "period": {
            "date_from": period.get("dateFrom"),
            "date_to": period.get("dateTo"),
            "days": period.get("days"),
            "comparison_date_from": period.get("comparisonDateFrom"),
            "comparison_date_to": period.get("comparisonDateTo"),
        },
        "data_coverage": snapshot.get("dataCoverage") or {},
        "model": response.get("model") or job.model,
        "output_budget_tokens": job.max_tokens,
    }


_JSON_FENCE_PATTERN = re.compile(
    r"\A```[ \t]*(?P<language>json)?[ \t]*\r?\n(?P<body>.*?)(?:\r?\n)?```[ \t]*\Z",
    re.IGNORECASE | re.DOTALL,
)
_UNSUPPORTED_AUDIT_FORMAT_MESSAGE = (
    "AI вернул результат в неподдерживаемом формате. Метаданные аудита сохранены, "
    "технический ответ доступен ниже."
)
_MAX_AUDIT_TECHNICAL_RESPONSE_CHARS = 80_000


def extract_model_json_object(answer: str) -> tuple[dict[str, Any] | None, str]:
    """Accept only a JSON object or one outer plain/JSON Markdown fence."""
    text = str(answer or "").lstrip("\ufeff").strip()
    if not text:
        return None, "empty"
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict):
        return parsed, "plain_json"

    fenced = _JSON_FENCE_PATTERN.fullmatch(text)
    if not fenced:
        return None, "invalid"
    try:
        parsed = json.loads(fenced.group("body").strip())
    except (TypeError, ValueError):
        return None, "invalid"
    return (parsed, "markdown_fenced_json") if isinstance(parsed, dict) else (None, "invalid")


def _validate_structured_result_with_metadata(
    answer: str,
    *,
    snapshot: dict[str, Any],
    job: AiAuditJob,
    response: dict[str, Any],
    finish_reason: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    parsed, source_format = extract_model_json_object(answer)
    parsing = {
        "status": "fallback",
        "sourceFormat": source_format,
        "errorCode": None,
        "validationErrorsCount": 0,
    }
    if parsed is None:
        parsing["errorCode"] = (
            "truncated_provider_response"
            if finish_reason == "length"
            else ("empty_provider_response" if source_format == "empty" else "json_parse_failed")
        )
        return None, parsing
    parsed["meta"] = _trusted_result_meta(snapshot, job, response)
    try:
        validated = AiAuditResult.model_validate(parsed).model_dump(mode="json")
    except ValidationError as exc:
        parsing["errorCode"] = "truncated_provider_response" if finish_reason == "length" else "json_schema_validation_failed"
        parsing["validationErrorsCount"] = len(exc.errors())
        return None, parsing
    parsing["status"] = "success"
    parsing["errorCode"] = "truncated_provider_response" if finish_reason == "length" else None
    return _enforce_verified_result(validated, snapshot), parsing


def _validate_structured_result(
    answer: str,
    *,
    snapshot: dict[str, Any],
    job: AiAuditJob,
    response: dict[str, Any],
) -> dict[str, Any] | None:
    structured, _ = _validate_structured_result_with_metadata(
        answer,
        snapshot=snapshot,
        job=job,
        response=response,
    )
    return structured


def _safe_technical_response(answer: str | None) -> str | None:
    text = str(answer or "").strip()
    if not text:
        return None
    redacted = str(redact_openrouter_debug_payload(text))
    if len(redacted) > _MAX_AUDIT_TECHNICAL_RESPONSE_CHARS:
        return f"{redacted[:_MAX_AUDIT_TECHNICAL_RESPONSE_CHARS].rstrip()}\n\n[технический ответ сокращён]"
    return redacted


def _enforce_verified_result(result: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    verification = {item.get("hypothesis_id"): item for item in (snapshot.get("verifiedHypotheses") or [])}
    for key in ("critical_findings", "opportunities"):
        for finding in result.get(key) or []:
            hypothesis_id = finding.get("hypothesis_id")
            verified = verification.get(hypothesis_id) if hypothesis_id else None
            status_value = str((verified or {}).get("status") or "unverified")
            finding["verification_status"] = status_value
            if status_value in {"rejected", "not_applicable"}:
                finding["hypothesis"] = None
                finding["recommendation"] = "Не выполнять действие по отклонённой или неприменимой гипотезе."
            elif status_value == "unverified":
                remaining = (verified or {}).get("remaining_data_needed") or finding.get("next_data_needed") or []
                finding["hypothesis"] = f"Неподтверждённая гипотеза: {finding.get('hypothesis') or 'причина не установлена'}"
                finding["recommendation"] = "Собрать недостающие данные: " + (", ".join(remaining) if remaining else "проверить гипотезу вручную")
            finding["requires_human_approval"] = True
    safe_actions = []
    for action in result.get("action_plan") or []:
        hypothesis_id = action.get("hypothesis_id")
        status_value = str((verification.get(hypothesis_id) or {}).get("status") or "") if hypothesis_id else "fact_based"
        if status_value in {"rejected", "not_applicable"}:
            continue
        if status_value == "unverified":
            action["action"] = f"Собрать дополнительные данные для проверки {hypothesis_id}."
            action["reason"] = "Причина не подтверждена собранными данными."
            action["mode"] = "manual_review"
        action["requires_human_approval"] = True
        safe_actions.append(action)
    result["action_plan"] = safe_actions[:10]
    return result


def _format_period_line(period: dict[str, Any]) -> str:
    def display(value: Any) -> str:
        parsed = _parse_iso_date(value)
        return parsed.strftime("%d.%m.%Y") if parsed else "дата не определена"

    return f"Период анализа: {display(period.get('dateFrom'))}–{display(period.get('dateTo'))}, {period.get('days') or '—'} дней."


def build_audit_answer_markdown(structured: dict[str, Any], snapshot: dict[str, Any]) -> str:
    lines = [_format_period_line(snapshot.get("analysisPeriod") or {}), "", "## Краткий итог аудита", structured.get("executive_summary") or ""]
    sections = (
        ("Критические проблемы", "critical_findings", 5),
        ("Возможности", "opportunities", 3),
    )
    for title, key, limit in sections:
        items = [
            item for item in (structured.get(key) or [])
            if item.get("verification_status") not in {"rejected", "not_applicable"}
        ][:limit]
        if items:
            lines.extend(["", f"## {title}"])
            for item in items:
                lines.append(f"- **{item.get('campaign_name') or 'Аккаунт'}:** {item.get('problem') or ''} — {item.get('recommendation') or ''}")
    actions = (structured.get("action_plan") or [])[:5]
    if actions:
        lines.extend(["", "## Краткий план действий"])
        lines.extend(f"- {item.get('action') or ''}" for item in actions)
    lines.extend(["", "## Вывод", structured.get("conclusion") or ""])
    return "\n".join(lines)


def _prompt_metadata(
    prompt: str,
    job: AiAuditJob,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    max_tokens_cap: int = AI_AUDIT_FINAL_MAX_TOKENS,
) -> dict[str, Any]:
    debug = build_prompt_debug_snapshot(
        context={"auditContextMetadata": (_json_load(job.context_snapshot_json, {}).get("metadata") or {})},
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=model or job.model,
        max_tokens=max_tokens or job.max_tokens,
        include_preview=False,
        max_tokens_cap=max_tokens_cap,
    )
    return {
        "promptHash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "promptChars": len(prompt),
        "estimatedInputTokens": debug["size"]["estimatedInputTokens"],
        "estimatedTotalTokens": debug["size"]["estimatedTotalTokens"],
        "contextLimit": debug["size"]["contextLimit"],
        "isTooLarge": debug["size"]["isTooLarge"],
        "fullPromptStored": False,
    }


def _audit_runtime(snapshot: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "investigationRound": 1,
        "maxInvestigationRounds": 2,
        "requestsCount": 0,
        "providerCallsCount": 0,
        "helperProviderCallsCount": 0,
        "finalProviderCallsCount": 0,
        "helperFallbacksCount": 0,
        "plannerPromptTokensEstimated": 0,
        "verificationPromptTokensEstimated": 0,
        "directApiCallsCount": 0,
        "tokenUsage": {"prompt": 0, "completion": 0, "total": 0},
    }
    runtime = snapshot.setdefault("auditRuntime", {})
    for key, value in defaults.items():
        runtime.setdefault(key, value.copy() if isinstance(value, dict) else value)
    return runtime


def _record_provider_attempt(snapshot: dict[str, Any], provider_kind: str) -> None:
    runtime = _audit_runtime(snapshot)
    runtime["providerCallsCount"] = int(runtime.get("providerCallsCount") or 0) + 1
    counter = "helperProviderCallsCount" if provider_kind == "helper" else "finalProviderCallsCount"
    runtime[counter] = int(runtime.get(counter) or 0) + 1


def _record_provider_response(snapshot: dict[str, Any], response: dict[str, Any]) -> None:
    runtime = _audit_runtime(snapshot)
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    token_usage = runtime.setdefault("tokenUsage", {"prompt": 0, "completion": 0, "total": 0})
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    token_usage["prompt"] = int(token_usage.get("prompt") or 0) + prompt_tokens
    token_usage["completion"] = int(token_usage.get("completion") or 0) + completion_tokens
    token_usage["total"] = int(token_usage.get("total") or 0) + total_tokens


def _helper_stages(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stages = snapshot.setdefault("helperStages", {})
    defaults = {
        "planner": {"model": AI_AUDIT_HELPER_MODEL, "status": "pending", "warningCode": None},
        "verification": {"model": AI_AUDIT_HELPER_MODEL, "status": "pending", "warningCode": None},
    }
    for key, value in defaults.items():
        stages.setdefault(key, dict(value))
    return stages


def _audit_models(snapshot: dict[str, Any], requested_model: str) -> dict[str, Any]:
    models = snapshot.setdefault("auditModels", {})
    defaults = {
        "requested_model": requested_model,
        "helper_model": AI_AUDIT_HELPER_MODEL,
        "planner_returned_model": None,
        "verification_returned_model": None,
        "final_returned_model": None,
    }
    for key, value in defaults.items():
        models.setdefault(key, value)
    return models


def _set_helper_stage(
    snapshot: dict[str, Any],
    stage_name: str,
    *,
    status_value: str,
    warning_code: str | None = None,
    returned_model: str | None = None,
) -> None:
    helper_stage = _helper_stages(snapshot).setdefault(stage_name, {})
    helper_stage.update({
        "model": AI_AUDIT_HELPER_MODEL,
        "status": status_value,
        "warningCode": warning_code,
    })
    if returned_model:
        helper_stage["returnedModel"] = returned_model


def _helper_warning(stage: str, code: str, message: str) -> dict[str, Any]:
    return {"stage": stage, "code": code, "message": message, "retryable": False}


def _append_helper_fallback(
    snapshot: dict[str, Any],
    *,
    job_id: str,
    stage: str,
    stage_name: str,
    code: str,
    message: str,
    reason: str,
    elapsed_ms: int,
    prompt_tokens: int,
) -> None:
    warnings = snapshot.setdefault("auditWarnings", [])
    if not any(item.get("code") == code for item in warnings if isinstance(item, dict)):
        warnings.append(_helper_warning(stage, code, message))
    runtime = _audit_runtime(snapshot)
    runtime["helperFallbacksCount"] = int(runtime.get("helperFallbacksCount") or 0) + 1
    _set_helper_stage(snapshot, stage_name, status_value="fallback", warning_code=code)
    logger.warning(
        "AI_AUDIT_HELPER_STAGE_FALLBACK job_id=%s stage=%s helper_model=%s elapsed_ms=%s "
        "prompt_estimated_tokens=%s fallback_reason=%s",
        job_id,
        stage,
        AI_AUDIT_HELPER_MODEL,
        elapsed_ms,
        prompt_tokens,
        reason,
    )


def _helper_fallback_reason(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return str(detail.get("error_code") or "provider_error")[:100]
        return f"http_{exc.status_code}"
    return type(exc).__name__[:100]


def _helper_warning_messages(snapshot: dict[str, Any]) -> list[str]:
    return [
        str(item.get("message"))
        for item in (snapshot.get("auditWarnings") or [])
        if isinstance(item, dict) and item.get("message")
    ]


def _cap_drilldown_results(results: list[dict[str, Any]], token_target: int = DRILLDOWN_TOKEN_TARGET) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    used = 0
    for original in results:
        item = dict(original)
        rows = list(item.pop("data", []) or [])
        base_tokens = estimate_tokens(_json_dump(item))
        if used + base_tokens > token_target:
            item["data"] = []
            item["limitations"] = list(item.get("limitations") or []) + ["Данные исключены из AI-контекста из-за общего token budget."]
            compact.append(item)
            continue
        included = []
        used += base_tokens
        for row in rows:
            row_tokens = estimate_tokens(_json_dump(row))
            if used + row_tokens > token_target:
                break
            included.append(row)
            used += row_tokens
        item["data"] = included
        if len(included) < len(rows):
            item["limitations"] = list(item.get("limitations") or []) + [f"В AI-контекст включено {len(included)} из {len(rows)} строк."]
        compact.append(item)
    return compact


def _save_stage_prompt_metadata(
    job: AiAuditJob,
    stage: str,
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int,
    max_tokens_cap: int = AI_AUDIT_FINAL_MAX_TOKENS,
) -> dict[str, Any]:
    stored = _json_load(job.prompt_snapshot_json, {}) or {}
    stages = stored.setdefault("stages", {})
    stages[stage] = _prompt_metadata(
        prompt,
        job,
        model=model,
        max_tokens=max_tokens,
        max_tokens_cap=max_tokens_cap,
    )
    stored["fullPromptStored"] = False
    job.prompt_snapshot_json = _json_dump(stored)
    return stages[stage]


def _locked_job(db: Session, job_id: str, organization_id: str) -> AiAuditJob:
    job = db.scalar(
        select(AiAuditJob)
        .where(AiAuditJob.id == job_id, AiAuditJob.organization_id == organization_id)
        .with_for_update()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI audit job not found")
    return job


def is_audit_stage_stale(job: AiAuditJob, now: datetime | None = None) -> bool:
    if job.status != "generating":
        return False
    lease_expires_at = job.stage_lease_expires_at
    if not lease_expires_at:
        legacy_started_at = job.stage_started_at or job.updated_at
        if not legacy_started_at:
            return False
        lease_seconds = AUDIT_STAGE_LEASE_SECONDS.get(job.current_stage, 180)
        lease_expires_at = _as_aware(legacy_started_at) + timedelta(seconds=lease_seconds)
    return _as_aware(lease_expires_at) < _as_aware(now or _now())


def recover_stale_audit_job(job: AiAuditJob, now: datetime | None = None) -> bool:
    if not is_audit_stage_stale(job, now):
        return False
    logger.warning(
        "AI_AUDIT_STAGE_STALE job_id=%s stage=%s attempt=%s",
        job.id,
        job.current_stage,
        job.stage_attempt,
    )
    if job.current_stage in {"create_investigation_plan", "verify_hypotheses"}:
        snapshot = _json_load(job.context_snapshot_json, {}) or {}
        runtime = _audit_runtime(snapshot)
        if job.current_stage == "create_investigation_plan":
            base_plan = AuditInvestigationPlan.model_validate(snapshot.get("ruleBasedInvestigationPlan") or {})
            snapshot["investigationPlan"] = base_plan.model_dump(mode="json")
            stage_name = "planner"
            warning_code = "planner_fallback_used"
            message = "AI-планировщик не ответил; используется безопасный план backend."
            next_stage = "validate_data_requests"
            progress_percent = 40
            prompt_tokens = int(runtime.get("plannerPromptTokensEstimated") or 0)
        else:
            snapshot["verifiedHypotheses"] = _verification_fallback(snapshot).model_dump(mode="json")["verifications"]
            stage_name = "verification"
            warning_code = "verification_fallback_used"
            message = "AI-проверка гипотез не ответила; неподтверждённые выводы безопасно помечены как требующие проверки."
            next_stage = "generate_answer"
            progress_percent = 78
            prompt_tokens = int(runtime.get("verificationPromptTokensEstimated") or 0)
        _append_helper_fallback(
            snapshot,
            job_id=job.id,
            stage=job.current_stage,
            stage_name=stage_name,
            code=warning_code,
            message=message,
            reason="stage_lease_expired",
            elapsed_ms=0,
            prompt_tokens=prompt_tokens,
        )
        job.context_snapshot_json = _json_dump(snapshot)
        job.status = "context_ready"
        job.current_stage = next_stage
        job.progress_percent = progress_percent
        job.error_code = None
        job.error_message = None
        job.retryable = False
        job.stage_attempt = 0
        job.stage_execution_token = None
        job.stage_lease_expires_at = None
        job.cancel_requested = False
        job.stage_version += 1
        return True
    job.status = "failed"
    job.error_code = "ai_audit_stage_stale"
    job.error_message = "Этап аудита был прерван и не завершился."
    job.retryable = True
    job.stage_execution_token = None
    job.cancel_requested = False
    job.stage_version += 1
    return True


def _claim_provider_stage(db: Session, job: AiAuditJob, stage: str, *, progress_percent: int) -> str:
    token = str(uuid.uuid4())
    now = _now()
    lease_seconds = AUDIT_STAGE_LEASE_SECONDS[stage]
    job.status = "generating"
    job.current_stage = stage
    job.progress_percent = progress_percent
    job.stage_started_at = now
    job.stage_lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.stage_execution_token = token
    job.stage_attempt = int(job.stage_attempt or 0) + 1
    job.cancel_requested = False
    job.error_code = None
    job.error_message = None
    job.retryable = False
    job.stage_version += 1
    db.commit()
    db.refresh(job)
    logger.info(
        "AI_AUDIT_STAGE_STARTED job_id=%s stage=%s attempt=%s lease_seconds=%s",
        job.id,
        stage,
        job.stage_attempt,
        lease_seconds,
    )
    return token


async def _call_audit_provider(stage: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        async with asyncio.timeout(AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS[stage]):
            return await generate_openrouter_response(*args, **kwargs)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error_code": "openrouter_total_timeout",
                "message": "AI-провайдер не завершил этап аудита за отведённое время.",
                "retryable": True,
            },
        ) from exc


def _reload_stage_owner(
    db: Session,
    job_id: str,
    organization_id: str,
    *,
    stage: str,
    execution_token: str,
) -> tuple[AiAuditJob, bool]:
    db.expire_all()
    current = _locked_job(db, job_id, organization_id)
    if recover_stale_audit_job(current, _now()):
        db.commit()
        db.refresh(current)
    owns_stage = (
        current.status == "generating"
        and current.current_stage == stage
        and current.stage_execution_token == execution_token
        and not current.cancel_requested
    )
    if owns_stage:
        return current, True
    logger.info(
        "AI_AUDIT_LATE_RESULT_DISCARDED job_id=%s stage=%s attempt=%s",
        current.id,
        stage,
        current.stage_attempt,
    )
    return current, False


def _complete_provider_stage(job: AiAuditJob, stage: str) -> None:
    logger.info(
        "AI_AUDIT_STAGE_COMPLETED job_id=%s stage=%s attempt=%s",
        job.id,
        stage,
        job.stage_attempt,
    )
    job.stage_execution_token = None
    job.stage_lease_expires_at = None


def get_audit_job(db: Session, job_id: str, *, organization_id: str) -> AiAuditJob:
    job = _locked_job(db, job_id, organization_id)
    if recover_stale_audit_job(job, _now()):
        db.commit()
        db.refresh(job)
        return job
    return job


def _context_metadata(job: AiAuditJob) -> dict[str, Any]:
    snapshot = _json_load(job.context_snapshot_json, {}) or {}
    drilldowns = snapshot.get("drilldownResults") or []
    runtime = snapshot.get("auditRuntime") or {}
    requested_dimensions = sorted({str(item.get("dimension")) for item in drilldowns if item.get("dimension")})
    status_counts: dict[str, int] = {}
    for item in drilldowns:
        value = str(item.get("status") or "unknown")
        status_counts[value] = status_counts.get(value, 0) + 1
    return {
        **(snapshot.get("metadata") or {}),
        "analysisPeriod": snapshot.get("analysisPeriod") or {},
        "dataCoverage": snapshot.get("dataCoverage") or {},
        "investigation": {
            "hypothesesCount": len((snapshot.get("investigationPlan") or {}).get("hypotheses", [])),
            "requestedDimensions": requested_dimensions,
            "requestStatusCounts": status_counts,
            "verifiedStatusCounts": {
                status_name: sum(1 for item in (snapshot.get("verifiedHypotheses") or []) if item.get("status") == status_name)
                for status_name in ("confirmed", "partially_confirmed", "rejected", "unverified", "not_applicable")
            },
            "dataRequests": {
                "planned": int(runtime.get("requestsCount") or 0),
                "allowed": sum(
                    1
                    for item in drilldowns
                    if item.get("status") in {"collected", "unavailable", "insufficient_data", "failed"}
                ),
                "saved": int(runtime.get("savedDataRequestsCount") or 0),
                "live": int(runtime.get("directApiCallsCount") or 0),
                "statusCounts": status_counts,
                "unavailableDimensions": sorted({
                    str(item.get("dimension"))
                    for item in drilldowns
                    if item.get("dimension") and item.get("status") in {
                        "unavailable", "unsupported", "skipped_budget_limit", "failed"
                    }
                }),
            },
        },
        "runtime": runtime,
        "helperStages": snapshot.get("helperStages") or {},
        "models": snapshot.get("auditModels") or {},
        "warnings": snapshot.get("auditWarnings") or [],
    }


def _public_audit_result(job: AiAuditJob) -> tuple[dict[str, Any] | None, str | None]:
    """Return a presentation-safe result and repair legacy fenced-JSON jobs on read."""
    stored_result = _json_load(job.result_json, None)
    result = dict(stored_result) if isinstance(stored_result, dict) else None
    snapshot = _json_load(job.context_snapshot_json, {}) or {}
    structured = result.get("structured") if result else None
    parsing = result.get("structuredParsing") if result else None
    technical_candidate = None

    if not structured:
        candidates = []
        if result:
            candidates.extend((result.get("technicalResponse"), result.get("rawResponse"), result.get("fallbackMarkdown")))
        candidates.append(job.answer_text)
        response = {"model": job.returned_model or job.model}
        for candidate in candidates:
            if not candidate:
                continue
            technical_candidate = technical_candidate or str(candidate)
            structured, candidate_parsing = _validate_structured_result_with_metadata(
                str(candidate),
                snapshot=snapshot,
                job=job,
                response=response,
                finish_reason=(result or {}).get("finishReason"),
            )
            if structured:
                parsing = candidate_parsing
                break
            parsing = parsing or candidate_parsing

    if result is not None:
        result.pop("rawResponse", None)
        if structured:
            result["structured"] = structured
            result["fallbackMarkdown"] = None
            result.pop("technicalResponse", None)
            if not result.get("truncated"):
                result["completeness"] = "structured"
            result["structuredParsing"] = parsing or {
                "status": "success", "sourceFormat": "plain_json", "errorCode": None, "validationErrorsCount": 0,
            }
            result["warnings"] = [
                warning
                for warning in (result.get("warnings") or [])
                if "json-контракт" not in str(warning).lower()
            ]
        else:
            result["fallbackMarkdown"] = _UNSUPPORTED_AUDIT_FORMAT_MESSAGE
            result["technicalResponse"] = _safe_technical_response(
                result.get("technicalResponse") or technical_candidate or job.answer_text
            )
            result["structuredParsing"] = parsing or {
                "status": "fallback", "sourceFormat": "empty", "errorCode": "empty_provider_response", "validationErrorsCount": 0,
            }

    if structured:
        answer = build_audit_answer_markdown(structured, snapshot)
    elif result is not None:
        answer = _UNSUPPORTED_AUDIT_FORMAT_MESSAGE
    else:
        answer = _UNSUPPORTED_AUDIT_FORMAT_MESSAGE if job.answer_text else None
    return result, answer


def audit_job_response(job: AiAuditJob) -> AiAuditJobResponse:
    result, answer = _public_audit_result(job)
    return AiAuditJobResponse(
        job_id=job.id,
        client_id=job.client_id,
        status=job.status,
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        poll_after_ms=POLL_AFTER_MS,
        requested_scope=job.requested_scope,
        requested_period=job.requested_period,
        selected_campaign_name=job.selected_campaign_name,
        model=job.model,
        returned_model=job.returned_model,
        ai_preset=job.ai_preset,
        max_tokens=job.max_tokens,
        system_prompt_version=job.system_prompt_version,
        system_prompt_hash=job.system_prompt_hash,
        context_metadata=_context_metadata(job),
        timings=_json_load(job.timings_json, {}),
        result=result,
        answer=answer,
        error_code=job.error_code,
        error_message=job.error_message,
        retryable=job.retryable,
        stage_started_at=_iso(job.stage_started_at),
        stage_lease_expires_at=_iso(job.stage_lease_expires_at),
        stage_attempt=int(job.stage_attempt or 0),
        is_stage_stale=job.error_code == "ai_audit_stage_stale" or is_audit_stage_stale(job),
        cancel_requested=bool(job.cancel_requested),
        created_at=_iso(job.created_at),
        updated_at=_iso(job.updated_at),
        completed_at=_iso(job.completed_at),
        expires_at=_iso(job.expires_at),
    )


def create_audit_job(
    db: Session,
    payload: AiAuditCreateRequest,
    *,
    organization_id: str,
    user_id: str | None,
    user_email: str | None,
) -> AiAuditJob:
    client = db.get(ClientAccount, payload.client_id)
    if not client or client.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    options = normalize_ai_audit_request_options(
        model=payload.model,
        ai_preset=payload.ai_preset,
        max_tokens=payload.max_tokens,
        scope=payload.scope,
    )
    prompt_metadata = get_system_prompt_metadata()
    now = _now()
    job = AiAuditJob(
        organization_id=organization_id,
        client_id=client.id,
        created_by_user_id=user_id,
        created_by_email=user_email,
        status="queued",
        current_stage="collect_context",
        progress_percent=0,
        requested_scope=payload.scope,
        requested_period=payload.period,
        selected_campaign_name=payload.selected_campaign_name,
        model=str(options["model"]),
        ai_preset=str(options["ai_preset"]),
        max_tokens=int(options["max_tokens"]),
        system_prompt_version=str(prompt_metadata["version"]),
        system_prompt_hash=str(prompt_metadata["hash"]),
        input_options_json=_json_dump(payload.options.model_dump()),
        timings_json="{}",
        expires_at=now + timedelta(days=30),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _save_failure(db: Session, job: AiAuditJob, exc: Exception, *, stage: str) -> AiAuditJob:
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
    error_code = detail.get("error_code") if isinstance(detail, dict) else None
    retryable = bool(detail.get("retryable")) if isinstance(detail, dict) else False
    job.status = "failed"
    job.current_stage = stage
    job.error_code = str(error_code or "ai_audit_stage_failed")
    job.error_message = str(detail.get("message") if isinstance(detail, dict) else detail)[:1000]
    job.retryable = retryable
    job.stage_execution_token = None
    job.stage_lease_expires_at = None
    job.cancel_requested = False
    job.stage_version += 1
    db.commit()
    db.refresh(job)
    return job


def _log_timing(job: AiAuditJob, stage: str) -> None:
    timings = _json_load(job.timings_json, {})
    logger.info(
        "AI_AUDIT_JOB_TIMING job_id=%s organization_id=%s client_id=%s status=%s stage=%s model=%s "
        "system_prompt_version=%s system_prompt_hash=%s elapsed_ms=%s error_code=%s",
        job.id,
        job.organization_id,
        job.client_id,
        job.status,
        stage,
        job.model,
        job.system_prompt_version,
        job.system_prompt_hash[:12],
        timings.get(f"{stage}Ms", 0),
        job.error_code or "none",
    )


async def advance_audit_job(
    db: Session,
    job_id: str,
    *,
    organization_id: str,
    retry: bool = False,
    compact_retry: bool = False,
) -> AiAuditJob:
    job = _locked_job(db, job_id, organization_id)
    if recover_stale_audit_job(job, _now()):
        db.commit()
        db.refresh(job)
        return job
    if job.status == "completed" and compact_retry:
        current_result = _json_load(job.result_json, {}) or {}
        if current_result.get("truncated"):
            options = _json_load(job.input_options_json, {}) or {}
            options["compact_retry"] = True
            job.input_options_json = _json_dump(options)
            job.status = "context_ready"
            job.current_stage = "generate_answer"
            job.stage_attempt = 0
            job.progress_percent = 78
            job.completed_at = None
            job.result_json = None
            job.answer_text = None
            job.error_code = None
            job.error_message = None
            db.commit()
            db.refresh(job)
        return job
    if job.status in {"completed", "cancelled"}:
        return job
    if job.status == "failed":
        if not retry or not job.retryable:
            return job
        if not job.context_snapshot_json:
            job.status = "queued"
            job.current_stage = "collect_context"
            job.stage_attempt = 0
        else:
            job.status = "context_ready"
        job.error_code = None
        job.error_message = None
        job.retryable = False
        job.cancel_requested = False
        db.commit()
        db.refresh(job)
    if job.status in {"collecting_context", "generating"}:
        return job

    timings = _json_load(job.timings_json, {})
    stage = job.current_stage
    started_at = perf_counter()
    execution_token: str | None = None
    try:
        if stage == "collect_context":
            job.status = "collecting_context"
            job.progress_percent = 10
            job.started_at = job.started_at or _now()
            job.stage_version += 1
            db.commit()
            context_started_at = perf_counter()
            full_context = build_client_ai_context_from_db(db, job.client_id, selected_campaign_name=job.selected_campaign_name)
            timings["collectContextMs"] = _elapsed_ms(context_started_at)
            compact_started_at = perf_counter()
            snapshot = build_compact_audit_context(
                full_context,
                requested_period=job.requested_period,
                options=_json_load(job.input_options_json, {}),
            )
            snapshot["requestedScope"] = job.requested_scope
            snapshot["auditRuntime"] = {
                "investigationRound": 1,
                "maxInvestigationRounds": 2,
                "requestsCount": 0,
                "providerCallsCount": 0,
                "helperProviderCallsCount": 0,
                "finalProviderCallsCount": 0,
                "helperFallbacksCount": 0,
                "plannerPromptTokensEstimated": 0,
                "verificationPromptTokensEstimated": 0,
                "savedDataRequestsCount": 0,
                "directApiCallsCount": 0,
                "tokenUsage": {"prompt": 0, "completion": 0, "total": 0},
            }
            _helper_stages(snapshot)
            _audit_models(snapshot, job.model)
            snapshot["metadata"]["estimatedTokens"] = estimate_tokens(_json_dump(snapshot))
            timings["compactContextMs"] = _elapsed_ms(compact_started_at)
            job.context_snapshot_json = _json_dump(snapshot)
            internal_ids = [
                str(item.get("campaign_id") or item.get("id"))
                for item in (full_context.get("campaigns") or [])
                if isinstance(item, dict) and (item.get("campaign_id") or item.get("id"))
            ]
            job.prompt_snapshot_json = _json_dump({"internalCampaignIds": internal_ids[:100]})
            job.status = "context_ready"
            job.current_stage = "classify_campaigns"
            job.stage_attempt = 0
            job.progress_percent = 15
        elif stage == "classify_campaigns":
            snapshot = _json_load(job.context_snapshot_json, {})
            snapshot["campaignClassifications"] = classify_audit_campaigns(snapshot)
            base_plan = build_rule_based_investigation_plan(snapshot)
            snapshot["ruleBasedInvestigationPlan"] = base_plan.model_dump(mode="json")
            job.context_snapshot_json = _json_dump(snapshot)
            job.status = "context_ready"
            job.current_stage = "create_investigation_plan"
            job.stage_attempt = 0
            job.progress_percent = 25
            timings["classifyCampaignsMs"] = _elapsed_ms(started_at)
        elif stage == "create_investigation_plan":
            snapshot = _json_load(job.context_snapshot_json, {})
            base_plan = AuditInvestigationPlan.model_validate(snapshot.get("ruleBasedInvestigationPlan") or {})
            if not should_call_ai_investigation_planner(base_plan, snapshot):
                snapshot["investigationPlan"] = base_plan.model_dump(mode="json")
                _set_helper_stage(snapshot, "planner", status_value="skipped_not_needed")
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "validate_data_requests"
                job.stage_attempt = 0
                job.progress_percent = 40
                timings["investigationPlanOpenrouterMs"] = 0
            else:
                execution_token = _claim_provider_stage(db, job, stage, progress_percent=30)
                snapshot = _json_load(job.context_snapshot_json, {})
                base_plan = AuditInvestigationPlan.model_validate(snapshot.get("ruleBasedInvestigationPlan") or {})
                prompt = build_investigation_plan_prompt(snapshot, base_plan)
                prompt_metadata = _save_stage_prompt_metadata(
                    job,
                    stage,
                    prompt,
                    model=AI_AUDIT_HELPER_MODEL,
                    max_tokens=AI_AUDIT_PLANNER_MAX_TOKENS,
                    max_tokens_cap=AI_AUDIT_PLANNER_MAX_TOKENS,
                )
                runtime = _audit_runtime(snapshot)
                runtime["plannerPromptTokensEstimated"] = int(prompt_metadata["estimatedInputTokens"] or 0)
                _record_provider_attempt(snapshot, "helper")
                job.context_snapshot_json = _json_dump(snapshot)
                db.commit()
                openrouter_started_at = perf_counter()
                logger.info(
                    "AI_AUDIT_HELPER_STAGE_STARTED job_id=%s stage=%s helper_model=%s prompt_estimated_tokens=%s",
                    job.id,
                    stage,
                    AI_AUDIT_HELPER_MODEL,
                    runtime["plannerPromptTokensEstimated"],
                )
                try:
                    response = await _call_audit_provider(
                        stage,
                        AI_AUDIT_HELPER_MODEL,
                        prompt,
                        max_tokens=AI_AUDIT_PLANNER_MAX_TOKENS,
                        max_tokens_cap=AI_AUDIT_PLANNER_MAX_TOKENS,
                        timeout=AUDIT_STAGE_PROVIDER_TIMEOUTS[stage],
                    )
                except Exception as helper_exc:
                    job, owns_result = _reload_stage_owner(
                        db,
                        job_id,
                        organization_id,
                        stage=stage,
                        execution_token=execution_token,
                    )
                    if not owns_result:
                        return job
                    elapsed_ms = _elapsed_ms(openrouter_started_at)
                    timings["investigationPlanOpenrouterMs"] = elapsed_ms
                    snapshot = _json_load(job.context_snapshot_json, {})
                    snapshot["investigationPlan"] = base_plan.model_dump(mode="json")
                    _append_helper_fallback(
                        snapshot,
                        job_id=job.id,
                        stage=stage,
                        stage_name="planner",
                        code="planner_fallback_used",
                        message="AI-планировщик не ответил; используется безопасный план backend.",
                        reason=_helper_fallback_reason(helper_exc),
                        elapsed_ms=elapsed_ms,
                        prompt_tokens=int((_audit_runtime(snapshot).get("plannerPromptTokensEstimated") or 0)),
                    )
                    job.context_snapshot_json = _json_dump(snapshot)
                    job.status = "context_ready"
                    job.current_stage = "validate_data_requests"
                    job.stage_attempt = 0
                    job.progress_percent = 40
                    _complete_provider_stage(job, stage)
                else:
                    job, owns_result = _reload_stage_owner(
                        db,
                        job_id,
                        organization_id,
                        stage=stage,
                        execution_token=execution_token,
                    )
                    if not owns_result:
                        return job
                    elapsed_ms = _elapsed_ms(openrouter_started_at)
                    timings["investigationPlanOpenrouterMs"] = elapsed_ms
                    snapshot = _json_load(job.context_snapshot_json, {})
                    _record_provider_response(snapshot, response)
                    returned_model = str(response.get("model") or AI_AUDIT_HELPER_MODEL)
                    _audit_models(snapshot, job.model)["planner_returned_model"] = returned_model
                    plan, valid_plan = _parse_investigation_plan(str(response.get("content") or ""), snapshot, base_plan)
                    snapshot["investigationPlan"] = plan.model_dump(mode="json")
                    if valid_plan:
                        _set_helper_stage(
                            snapshot,
                            "planner",
                            status_value="success",
                            returned_model=returned_model,
                        )
                        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
                        logger.info(
                            "AI_AUDIT_HELPER_STAGE_COMPLETED job_id=%s stage=%s helper_model=%s elapsed_ms=%s "
                            "prompt_estimated_tokens=%s completion_tokens=%s",
                            job.id,
                            stage,
                            AI_AUDIT_HELPER_MODEL,
                            elapsed_ms,
                            _audit_runtime(snapshot).get("plannerPromptTokensEstimated") or 0,
                            usage.get("completion_tokens") or usage.get("output_tokens") or 0,
                        )
                    else:
                        _append_helper_fallback(
                            snapshot,
                            job_id=job.id,
                            stage=stage,
                            stage_name="planner",
                            code="planner_fallback_used",
                            message="AI-планировщик вернул некорректный ответ; используется безопасный план backend.",
                            reason="invalid_json",
                            elapsed_ms=elapsed_ms,
                            prompt_tokens=int((_audit_runtime(snapshot).get("plannerPromptTokensEstimated") or 0)),
                        )
                    job.context_snapshot_json = _json_dump(snapshot)
                    job.status = "context_ready"
                    job.current_stage = "validate_data_requests"
                    job.stage_attempt = 0
                    job.progress_percent = 40
                    _complete_provider_stage(job, stage)
        elif stage == "validate_data_requests":
            snapshot = _json_load(job.context_snapshot_json, {})
            plan = AuditInvestigationPlan.model_validate(snapshot.get("investigationPlan") or {})
            requests = [request for hypothesis in plan.hypotheses for request in hypothesis.data_requests]
            accepted, rejected = validate_audit_data_requests(requests)
            runtime = _audit_runtime(snapshot)
            runtime["requestsCount"] = len(requests)
            snapshot["validatedDataRequests"] = [item.model_dump(mode="json") for item in accepted]
            snapshot["drilldownResults"] = [item.model_dump(mode="json") for item in rejected]
            job.context_snapshot_json = _json_dump(snapshot)
            job.status = "context_ready"
            job.current_stage = "collect_drilldowns"
            job.stage_attempt = 0
            job.progress_percent = 50
            timings["validateDataRequestsMs"] = _elapsed_ms(started_at)
        elif stage == "collect_drilldowns":
            snapshot = _json_load(job.context_snapshot_json, {})
            requests = [AuditDataRequest.model_validate(item) for item in (snapshot.get("validatedDataRequests") or [])]
            collected, direct_api_calls = collect_audit_data_requests(db, job.client_id, requests)
            snapshot["drilldownResults"] = _cap_drilldown_results(
                (snapshot.get("drilldownResults") or []) + [item.model_dump(mode="json") for item in collected]
            )
            runtime = _audit_runtime(snapshot)
            runtime["savedDataRequestsCount"] = int(runtime.get("savedDataRequestsCount") or 0) + sum(
                1 for item in collected if item.source == "directpilot_saved_read_only_stats"
            )
            runtime["directApiCallsCount"] = int(runtime.get("directApiCallsCount") or 0) + direct_api_calls
            has_hypotheses = bool((snapshot.get("investigationPlan") or {}).get("hypotheses"))
            if not has_hypotheses:
                snapshot["verifiedHypotheses"] = []
                _set_helper_stage(snapshot, "verification", status_value="skipped_not_needed")
            job.context_snapshot_json = _json_dump(snapshot)
            job.status = "context_ready"
            job.current_stage = "verify_hypotheses" if has_hypotheses else "generate_answer"
            job.stage_attempt = 0
            job.progress_percent = 65 if has_hypotheses else 78
            timings["collectDrilldownsMs"] = _elapsed_ms(started_at)
        elif stage == "verify_hypotheses":
            execution_token = _claim_provider_stage(db, job, stage, progress_percent=70)
            snapshot = _json_load(job.context_snapshot_json, {})
            prompt = build_verification_prompt(snapshot)
            prompt_metadata = _save_stage_prompt_metadata(
                job,
                stage,
                prompt,
                model=AI_AUDIT_HELPER_MODEL,
                max_tokens=AI_AUDIT_VERIFICATION_MAX_TOKENS,
                max_tokens_cap=AI_AUDIT_VERIFICATION_MAX_TOKENS,
            )
            runtime = _audit_runtime(snapshot)
            runtime["verificationPromptTokensEstimated"] = int(prompt_metadata["estimatedInputTokens"] or 0)
            _record_provider_attempt(snapshot, "helper")
            job.context_snapshot_json = _json_dump(snapshot)
            db.commit()
            openrouter_started_at = perf_counter()
            logger.info(
                "AI_AUDIT_HELPER_STAGE_STARTED job_id=%s stage=%s helper_model=%s prompt_estimated_tokens=%s",
                job.id,
                stage,
                AI_AUDIT_HELPER_MODEL,
                runtime["verificationPromptTokensEstimated"],
            )
            try:
                response = await _call_audit_provider(
                    stage,
                    AI_AUDIT_HELPER_MODEL,
                    prompt,
                    max_tokens=AI_AUDIT_VERIFICATION_MAX_TOKENS,
                    max_tokens_cap=AI_AUDIT_VERIFICATION_MAX_TOKENS,
                    timeout=AUDIT_STAGE_PROVIDER_TIMEOUTS[stage],
                )
            except Exception as helper_exc:
                job, owns_result = _reload_stage_owner(
                    db,
                    job_id,
                    organization_id,
                    stage=stage,
                    execution_token=execution_token,
                )
                if not owns_result:
                    return job
                elapsed_ms = _elapsed_ms(openrouter_started_at)
                timings["verificationOpenrouterMs"] = elapsed_ms
                snapshot = _json_load(job.context_snapshot_json, {})
                verification = _verification_fallback(snapshot)
                snapshot["verifiedHypotheses"] = verification.model_dump(mode="json")["verifications"]
                _append_helper_fallback(
                    snapshot,
                    job_id=job.id,
                    stage=stage,
                    stage_name="verification",
                    code="verification_fallback_used",
                    message="AI-проверка гипотез не ответила; неподтверждённые выводы безопасно помечены как требующие проверки.",
                    reason=_helper_fallback_reason(helper_exc),
                    elapsed_ms=elapsed_ms,
                    prompt_tokens=int((_audit_runtime(snapshot).get("verificationPromptTokensEstimated") or 0)),
                )
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "generate_answer"
                job.stage_attempt = 0
                job.progress_percent = 78
                _complete_provider_stage(job, stage)
            else:
                job, owns_result = _reload_stage_owner(
                    db,
                    job_id,
                    organization_id,
                    stage=stage,
                    execution_token=execution_token,
                )
                if not owns_result:
                    return job
                elapsed_ms = _elapsed_ms(openrouter_started_at)
                timings["verificationOpenrouterMs"] = elapsed_ms
                snapshot = _json_load(job.context_snapshot_json, {})
                _record_provider_response(snapshot, response)
                returned_model = str(response.get("model") or AI_AUDIT_HELPER_MODEL)
                _audit_models(snapshot, job.model)["verification_returned_model"] = returned_model
                verification, valid_verification = _parse_verifications(str(response.get("content") or ""), snapshot)
                snapshot["verifiedHypotheses"] = verification.model_dump(mode="json")["verifications"]
                second_round: list[AuditDataRequest] = []
                if valid_verification:
                    _set_helper_stage(
                        snapshot,
                        "verification",
                        status_value="success",
                        returned_model=returned_model,
                    )
                    second_round = _second_round_requests(snapshot)
                    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
                    logger.info(
                        "AI_AUDIT_HELPER_STAGE_COMPLETED job_id=%s stage=%s helper_model=%s elapsed_ms=%s "
                        "prompt_estimated_tokens=%s completion_tokens=%s",
                        job.id,
                        stage,
                        AI_AUDIT_HELPER_MODEL,
                        elapsed_ms,
                        _audit_runtime(snapshot).get("verificationPromptTokensEstimated") or 0,
                        usage.get("completion_tokens") or usage.get("output_tokens") or 0,
                    )
                else:
                    _append_helper_fallback(
                        snapshot,
                        job_id=job.id,
                        stage=stage,
                        stage_name="verification",
                        code="verification_fallback_used",
                        message="AI-проверка гипотез вернула некорректный ответ; неподтверждённые выводы безопасно помечены как требующие проверки.",
                        reason="invalid_json",
                        elapsed_ms=elapsed_ms,
                        prompt_tokens=int((_audit_runtime(snapshot).get("verificationPromptTokensEstimated") or 0)),
                    )
                if second_round:
                    runtime = _audit_runtime(snapshot)
                    runtime["investigationRound"] = 2
                    runtime["requestsCount"] = int(runtime.get("requestsCount") or 0) + len(second_round)
                    snapshot["validatedDataRequests"] = [item.model_dump(mode="json") for item in second_round]
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "collect_drilldowns" if second_round else "generate_answer"
                job.stage_attempt = 0
                job.progress_percent = 68 if second_round else 78
                _complete_provider_stage(job, stage)
        elif stage == "generate_answer":
            execution_token = _claim_provider_stage(db, job, stage, progress_percent=82)
            snapshot = _json_load(job.context_snapshot_json, {})
            input_options = _json_load(job.input_options_json, {}) or {}
            prompt = build_full_audit_prompt(snapshot, output_budget_tokens=job.max_tokens, compact_retry=bool(input_options.get("compact_retry")))
            metadata = _prompt_metadata(prompt, job)
            if metadata["isTooLarge"]:
                raise HTTPException(status_code=413, detail={"error_code": "ai_prompt_too_large", "message": "Adaptive audit prompt exceeds model context.", "retryable": False})
            _save_stage_prompt_metadata(
                job,
                stage,
                prompt,
                model=job.model,
                max_tokens=job.max_tokens,
                max_tokens_cap=AI_AUDIT_FINAL_MAX_TOKENS,
            )
            _record_provider_attempt(snapshot, "final")
            job.context_snapshot_json = _json_dump(snapshot)
            db.commit()
            openrouter_started_at = perf_counter()
            response = await _call_audit_provider(
                stage, job.model, prompt, max_tokens=job.max_tokens,
                max_tokens_cap=AI_AUDIT_FINAL_MAX_TOKENS, timeout=AUDIT_STAGE_PROVIDER_TIMEOUTS[stage],
            )
            job, owns_result = _reload_stage_owner(
                db,
                job_id,
                organization_id,
                stage=stage,
                execution_token=execution_token,
            )
            if not owns_result:
                return job
            timings["finalAnswerOpenrouterMs"] = _elapsed_ms(openrouter_started_at)
            _record_provider_response(snapshot, response)
            final_returned_model = str(response.get("model") or job.model)
            _audit_models(snapshot, job.model)["final_returned_model"] = final_returned_model
            job.context_snapshot_json = _json_dump(snapshot)
            answer = str(response.get("content") or "")
            finish_reason = str(response.get("finish_reason") or "") or None
            structured, parsing = _validate_structured_result_with_metadata(
                answer,
                snapshot=snapshot,
                job=job,
                response=response,
                finish_reason=finish_reason,
            )
            truncated = finish_reason == "length"
            warnings = _helper_warning_messages(snapshot)
            if not (snapshot.get("analysisPeriod") or {}).get("requestedMatchesAvailableData"):
                warnings.append("Фактический период отличается от запрошенного или доступен не полностью.")
            if not structured:
                warnings.append("Модель вернула результат в неподдерживаемом формате; основной интерфейс показывает только безопасные метаданные.")
            if truncated:
                warnings.append("Ответ модели достиг лимита и мог быть обрезан.")
            fallback_markdown = None if structured else _UNSUPPORTED_AUDIT_FORMAT_MESSAGE
            technical_response = None if structured else _safe_technical_response(answer)
            job.returned_model = final_returned_model
            job.answer_text = build_audit_answer_markdown(structured, snapshot) if structured else fallback_markdown
            job.result_json = _json_dump({
                "structured": structured,
                "fallbackMarkdown": fallback_markdown,
                "technicalResponse": technical_response,
                "structuredParsing": parsing,
                "providerResponseMetadata": {
                    "sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest() if answer else None,
                    "length": len(answer),
                    "sourceFormat": parsing["sourceFormat"],
                    "fullResponseStored": bool(technical_response),
                },
                "warnings": warnings,
                "finishReason": finish_reason,
                "truncated": truncated,
                "completeness": "truncated" if truncated else ("structured" if structured else "fallback"),
                "analysisPeriod": snapshot.get("analysisPeriod") or {},
                "dataCoverage": snapshot.get("dataCoverage") or {},
                "usage": response.get("usage"),
                "responseId": response.get("id"),
                "requestTrace": {
                    "jobId": job.id,
                    "model": job.model,
                    "systemPromptVersion": job.system_prompt_version,
                    "systemPromptHash": job.system_prompt_hash[:12],
                    "context": _context_metadata(job),
                    "runtime": snapshot.get("auditRuntime") or {},
                    "models": snapshot.get("auditModels") or {},
                    "helperStages": snapshot.get("helperStages") or {},
                },
                "safety": {"readOnly": True, "appliedToYandexDirect": False, "requiresHumanApproval": True},
            })
            job.status = "context_ready"
            job.current_stage = "finalize"
            job.stage_attempt = 0
            job.progress_percent = 95
            _complete_provider_stage(job, stage)
        elif stage == "finalize":
            finalize_started_at = perf_counter()
            job.status = "completed"
            job.progress_percent = 100
            job.completed_at = _now()
            job.retryable = False
            timings["finalizeMs"] = _elapsed_ms(finalize_started_at)
        else:
            raise RuntimeError(f"Unknown AI audit stage: {stage}")
        timings["totalElapsedMs"] = max(0, round((_now() - _as_aware(job.created_at or _now())).total_seconds() * 1000))
        job.timings_json = _json_dump(timings)
        job.stage_version += 1
        db.commit()
        db.refresh(job)
        _log_timing(job, stage)
        return job
    except Exception as exc:
        timings[f"{stage}Ms"] = _elapsed_ms(started_at)
        if execution_token:
            job, owns_result = _reload_stage_owner(
                db,
                job_id,
                organization_id,
                stage=stage,
                execution_token=execution_token,
            )
            if not owns_result:
                return job
        job.timings_json = _json_dump(timings)
        failed = _save_failure(db, job, exc, stage=stage)
        _log_timing(failed, stage)
        return failed


def cancel_audit_job(db: Session, job_id: str, *, organization_id: str) -> AiAuditJob:
    job = _locked_job(db, job_id, organization_id)
    if recover_stale_audit_job(job, _now()):
        db.commit()
        db.refresh(job)
    if job.status in {"completed", "cancelled"}:
        return job
    job.status = "cancelled"
    job.cancel_requested = True
    job.stage_execution_token = None
    job.stage_lease_expires_at = None
    job.error_code = None
    job.error_message = None
    job.retryable = False
    job.stage_version += 1
    db.commit()
    db.refresh(job)
    logger.info(
        "AI_AUDIT_STAGE_CANCELLED job_id=%s stage=%s attempt=%s",
        job.id,
        job.current_stage,
        job.stage_attempt,
    )
    return job


def reset_audit_job(db: Session, job_id: str, *, organization_id: str) -> AiAuditJob:
    job = _locked_job(db, job_id, organization_id)
    recovered = recover_stale_audit_job(job, _now())
    if recovered:
        db.commit()
        db.refresh(job)
    if job.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сброс доступен только для завершённого, отменённого или зависшего аудита.",
        )
    job.status = "cancelled"
    job.cancel_requested = True
    job.stage_execution_token = None
    job.stage_lease_expires_at = None
    job.error_code = None
    job.error_message = None
    job.retryable = False
    job.stage_version += 1
    db.commit()
    db.refresh(job)
    return job
