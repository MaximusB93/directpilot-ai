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
    AI_FALLBACK_ECONOMY_MODEL,
    normalize_ai_audit_request_options,
)
from app.models import AiAuditJob, ClientAccount, DirectReportJob
from app.schemas import (
    AiAuditCreateRequest,
    AiAuditAction,
    AiAuditDataQuality,
    AiAuditDrilldownSummary,
    AiAuditFinding,
    AiAuditInsufficientDataCampaign,
    AiAuditJobResponse,
    AiAuditResult,
    AuditDataRequest,
    AuditDataRequestResult,
    AuditHypothesisVerification,
    AuditHypothesisVerificationSet,
    AuditInvestigationHypothesis,
    AuditInvestigationPlan,
    AuditNextRoundPlan,
    AuditNextRoundRequest,
)
from app.services.audit_data_tools import (
    MAX_AUDIT_DATA_REQUESTS,
    collect_audit_data_requests,
    public_audit_tool_manifest,
    select_live_request_batch,
    validate_audit_data_requests,
)
from app.services.audit_evidence import (
    CONFIRMATION_RULE_BY_CAPABILITY,
    HYPOTHESIS_EVIDENCE_POLICY,
    REJECTION_RULE_BY_CAPABILITY,
    evaluate_capability_evidence,
    evaluate_metric_sufficiency,
    parse_numeric_metric,
)
from app.services.audit_evidence_store import (
    load_audit_evidence_results,
    save_audit_evidence_results,
)
from app.services.audit_evidence_reconciliation import (
    apply_canonical_coverage_to_registry,
    build_canonical_evidence_index,
    capability_candidates,
    canonical_coverage_projection,
    evidence_for_hypothesis,
)
from app.services.audit_evidence_identity import campaign_scope_for_name, campaign_scope_key
from app.services.audit_evidence_policy import (
    AUDIT_EVIDENCE_POLICY_VERSION,
    evidence_dimension_forbidden,
    ensure_evidence_coverage_registry,
    evaluate_audit_evidence_coverage,
    merge_mandatory_and_ai_requests,
    public_evidence_coverage,
    refresh_evidence_coverage_registry,
)
from app.services.audit_public_trace import build_public_audit_trace
from app.services.audit_scheduler import (
    collection_batch_can_start,
    build_minimum_coverage_requests,
    execution_profile_for_scope,
    initialize_scheduler_state,
    mark_scheduler_progress,
    mark_scheduler_waiting,
    partition_breadth_and_depth_requests,
    scheduler_deadline_state,
    scheduler_health,
)
from app.services.audit_scenario_library import (
    classify_conversion_state,
    select_audit_scenario,
)
from app.services.cascade_investigation import (
    MAX_DATA_REQUESTS_PER_AUDIT,
    MAX_INVESTIGATION_ROUNDS,
    build_cascade_hypotheses,
    build_observed_facts,
    create_investigation_round,
    enforce_hypothesis_verification,
    next_cascade_capabilities,
    round_stop_reason,
)
from app.services.ai_prompt_debug import (
    build_prompt_debug_snapshot,
    context_limit_for_model,
    estimate_tokens,
)
from app.services.ai_recommendations import build_client_ai_context_from_db
from app.services.direct_analyst_playbook import build_direct_analyst_instructions
from app.services.knowledge_base import select_knowledge_snippets
from app.services.yandex_direct_api_knowledge import (
    DIRECT_API_KNOWLEDGE_VERSION,
    describe_direct_capability,
    search_direct_api_docs,
)
from app.services.openrouter import (
    DEFAULT_SYSTEM_PROMPT,
    OPENROUTER_AUDIT_TIMEOUT,
    generate_openrouter_response,
)

logger = logging.getLogger(__name__)

TERMINAL_AUDIT_STATUSES = {"completed", "failed", "cancelled"}
AVAILABLE_AUDIT_DATA_STATUSES = {"collected", "cached", "partial"}
POLL_AFTER_MS = 1800
CONTEXT_TOKEN_TARGET = 12000
DRILLDOWN_TOKEN_TARGET = 18000
FINAL_PROMPT_SAFETY_MARGIN_TOKENS = 2048
FINAL_COMPACTION_LEVELS = (0, 1, 2, 3)
FINAL_AUDIT_PROVIDER_MAX_TOKENS = 4000
FINAL_SCHEMA_REPAIR_MAX_SECONDS = 45
FINAL_SCHEMA_REPAIR_MIN_REMAINING_SECONDS = 20
FINALIZATION_COMMIT_RESERVE_SECONDS = 10
NON_PROVIDER_STAGE_STALE_SECONDS = 15 * 60
QUEUED_AUDIT_STALE_SECONDS = 24 * 60 * 60
PROVIDER_CONTEXT_OVERFLOW_CODE = "provider_context_limit_rejected"
FINAL_PROVIDER_TIMEOUT_WARNING_CODE = "final_provider_timeout"
_FINAL_PROVIDER_TIMEOUT_CODES = frozenset({"openrouter_timeout", "openrouter_total_timeout"})
_PROVIDER_CONTEXT_OVERFLOW_CODES = frozenset({
    "context_length_exceeded",
    "context_window_exceeded",
    "context_limit_exceeded",
    "maximum_context_length_exceeded",
    "prompt_too_large",
    "prompt_too_long",
    "input_too_long",
    "input_tokens_exceeded",
    "token_limit_exceeded",
})
_PROVIDER_CONTEXT_OVERFLOW_MARKERS = (
    "context length",
    "maximum context",
    "max context",
    "context window",
    "prompt too large",
    "prompt is too large",
    "prompt too long",
    "input too long",
    "input tokens exceed",
    "input token count exceeds",
    "token limit exceeded",
    "tokens exceed the context",
)
AUDIT_STAGE_LEASE_SECONDS = {
    "create_investigation_plan": 75,
    "verify_hypotheses": 85,
    "plan_next_investigation_round": 75,
    "generate_answer": 180,
}
AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS = {
    "create_investigation_plan": 55,
    "verify_hypotheses": 65,
    "plan_next_investigation_round": 55,
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
    "plan_next_investigation_round": httpx.Timeout(
        connect=10.0,
        read=AI_AUDIT_PLANNER_READ_TIMEOUT_SECONDS,
        write=10.0,
        pool=10.0,
    ),
    "generate_answer": OPENROUTER_AUDIT_TIMEOUT,
}


def _log_audit_event(event: str, job: AiAuditJob, **fields: Any) -> None:
    safe_fields = " ".join(
        f"{key}={value}" for key, value in fields.items()
        if key in {
            "round", "request_count", "status", "capability", "rows", "pages",
            "hypothesis_id", "stop_reason",
        }
    )
    logger.info("%s audit_job_id=%s %s", event, job.id, safe_fields)
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
    if value is None or str(value).strip() in {"", "--", "—", "�"}:
        return None
    try:
        parsed = float(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else round(parsed, 2)


def _number_or_zero(value: Any) -> float:
    parsed = _number(value)
    return float(parsed) if parsed is not None else 0.0


def _int_or_zero(value: Any) -> int:
    return int(_number_or_zero(value))


def _flags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:100] for item in value[:10]]
    if isinstance(value, str):
        return [item.strip()[:100] for item in value.split(",") if item.strip()][:10]
    return []


def _hypothesis_registry(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    registry = snapshot.get("hypothesisRegistry")
    if not isinstance(registry, dict):
        registry = {}
        for item in (snapshot.get("investigationPlan") or {}).get("hypotheses", []):
            hypothesis_id = str(item.get("hypothesis_id") or "")
            if hypothesis_id:
                registry[hypothesis_id] = dict(item)
        snapshot["hypothesisRegistry"] = registry
    return registry


def _active_hypothesis_ids(snapshot: dict[str, Any]) -> list[str]:
    registry = _hypothesis_registry(snapshot)
    active = snapshot.get("activeHypothesisIds")
    if not isinstance(active, list):
        active = [
            str(item.get("hypothesis_id"))
            for item in (snapshot.get("investigationPlan") or {}).get("hypotheses", [])
            if item.get("hypothesis_id")
        ]
    normalized = list(dict.fromkeys(item for item in map(str, active) if item in registry))[:5]
    snapshot["activeHypothesisIds"] = normalized
    return normalized


def _active_hypotheses(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    registry = _hypothesis_registry(snapshot)
    return [registry[item] for item in _active_hypothesis_ids(snapshot) if item in registry]


def _sync_active_investigation_plan(snapshot: dict[str, Any]) -> None:
    snapshot["investigationPlan"] = {"hypotheses": [dict(item) for item in _active_hypotheses(snapshot)]}


def _initialize_hypothesis_state(snapshot: dict[str, Any]) -> None:
    plan_hypotheses = [
        dict(item) for item in (snapshot.get("investigationPlan") or {}).get("hypotheses", [])
        if item.get("hypothesis_id")
    ]
    snapshot["hypothesisRegistry"] = {
        str(item["hypothesis_id"]): item for item in plan_hypotheses
    }
    snapshot["activeHypothesisIds"] = [
        str(item["hypothesis_id"]) for item in plan_hypotheses[:5]
    ]
    _sync_active_investigation_plan(snapshot)


def _verification_registry(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    registry = snapshot.get("verificationRegistry")
    if not isinstance(registry, dict):
        registry = {
            str(item.get("hypothesis_id")): dict(item)
            for item in (snapshot.get("verifiedHypotheses") or [])
            if item.get("hypothesis_id")
        }
        snapshot["verificationRegistry"] = registry
    return registry


def _active_verifications(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    active_ids = set(_active_hypothesis_ids(snapshot))
    active = snapshot.get("activeVerifications")
    if isinstance(active, list):
        filtered = [
            dict(item) for item in active
            if isinstance(item, dict) and str(item.get("hypothesis_id")) in active_ids
        ][:5]
        if filtered:
            return filtered
    return [
        dict(item) for hypothesis_id, item in _verification_registry(snapshot).items()
        if hypothesis_id in active_ids
    ][:5]


def _merge_verification_registry(
    snapshot: dict[str, Any], verification: AuditHypothesisVerificationSet,
) -> None:
    registry = _verification_registry(snapshot)
    active: list[dict[str, Any]] = []
    for item in verification.verifications[:5]:
        payload = item.model_dump(mode="json")
        previous = registry.get(item.hypothesis_id)
        if previous and previous.get("status") == "rejected":
            payload = previous
        else:
            registry[item.hypothesis_id] = payload
        active.append(dict(payload))
    snapshot["activeVerifications"] = active
    snapshot["verifiedHypotheses"] = active


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


def _dynamics_campaign_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    """Keep only aggregate comparison data needed for deterministic facts."""

    def metrics(value: Any) -> dict[str, Any]:
        source = value if isinstance(value, dict) else {}
        return {
            key: _number(source.get(key))
            for key in (
                "cost", "impressions", "clicks", "ctr", "avgCpc",
                "goalConversions", "goalCpa", "conversionRate",
            )
        }

    changes = item.get("changes") if isinstance(item.get("changes"), dict) else {}
    comparison = changes.get("last7VsPrevious7") if isinstance(changes.get("last7VsPrevious7"), dict) else {}
    return {
        "name": item.get("campaignName") or item.get("campaign_name") or "Кампания без названия",
        "severity": item.get("severity") or "ok",
        "flags": _flags(item.get("issueFlags") or item.get("issue_flags")),
        "last7": metrics(item.get("last7")),
        "previous7": metrics(item.get("previous7")),
        "changes": {
            key: _number(comparison.get(key))
            for key in (
                "costDeltaPct", "clicksDeltaPct", "impressionsDeltaPct",
                "ctrDeltaPct", "avgCpcDeltaPct", "goalConversionsDeltaPct",
                "goalCpaDeltaPct",
            )
        },
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


def _name_campaign_classification(name: str) -> dict[str, str]:
    normalized = name.lower().replace("ё", "е")
    is_retargeting = any(
        marker in normalized
        for marker in ("ретарг", "ртг", "rtg", "retarget", "ремаркет")
    )
    explicit_search_retargeting = any(
        marker in normalized
        for marker in ("поисковый ретаргетинг", "search retargeting")
    )
    is_search_marker = any(marker in normalized for marker in ("поиск", "search"))
    is_search = bool(
        is_search_marker
        and (not is_retargeting or explicit_search_retargeting)
    )
    is_yan = (
        any(
            marker in normalized
            for marker in (
                "рся", "yan", "сети", "network", "интерес", "interest",
                "аудитор", "audience", "lookalike",
            )
        )
        or (is_retargeting and not explicit_search_retargeting)
    )
    is_brand = any(marker in normalized for marker in ("бренд", "brand"))
    if is_yan:
        return {"campaign_name": name, "campaign_family": "yan", "campaign_subtype": "yan_retargeting" if is_retargeting else "yan_prospecting", "classification_source": "name_heuristic", "warnings": []}
    if is_search or is_brand:
        return {"campaign_name": name, "campaign_family": "search", "campaign_subtype": "brand_search" if is_brand else "search", "classification_source": "name_heuristic", "warnings": []}
    return {"campaign_name": name, "campaign_family": "unknown", "campaign_subtype": "unknown", "classification_source": "unresolved", "warnings": []}


def _strategy_placement_family(metadata: dict[str, Any]) -> str | None:
    strategy = None
    for key in ("text_campaign", "mobile_app_campaign", "cpm_banner_campaign", "unified_campaign"):
        section = metadata.get(key)
        if isinstance(section, dict) and isinstance(section.get("bidding_strategy"), dict):
            strategy = section["bidding_strategy"]
            break
    if strategy is None and isinstance(metadata.get("bidding_strategy"), dict):
        strategy = metadata["bidding_strategy"]
    if not isinstance(strategy, dict):
        return None

    def enabled(section: Any) -> bool:
        if not isinstance(section, dict):
            return False
        strategy_type = str(section.get("bidding_strategy_type") or "").upper()
        return bool(strategy_type and strategy_type not in {"SERVING_OFF", "UNKNOWN"})

    search_enabled = enabled(strategy.get("search"))
    network_enabled = enabled(strategy.get("network"))
    if search_enabled and network_enabled:
        return "mixed"
    if search_enabled:
        return "search"
    if network_enabled:
        return "yan"
    return None


def _campaign_classification(name: str, explicit_type: str | dict[str, Any] | None = None) -> dict[str, Any]:
    heuristic = _name_campaign_classification(name)
    metadata = explicit_type if isinstance(explicit_type, dict) else {"type": explicit_type}
    api_type = str(metadata.get("type") or "").upper()
    strategy_family = _strategy_placement_family(metadata)
    api_family = "yan" if api_type == "CPM_BANNER_CAMPAIGN" else strategy_family
    if api_family == "mixed":
        return {
            "campaign_name": name,
            "campaign_family": "mixed",
            "campaign_subtype": "mixed",
            "classification_source": "direct_api_mixed",
            "api_type": api_type or None,
            "warnings": [
                "Direct API reports both search and network placements; "
                "the breadth plan requests explicit Search and Network evidence."
            ],
        }
    if api_family is None:
        return {
            **heuristic,
            "classification_source": "name_fallback" if heuristic["campaign_family"] != "unknown" else "unresolved",
            "api_type": api_type or None,
            "warnings": (["Campaign API metadata is insufficient; name heuristic was used."] if heuristic["campaign_family"] != "unknown" else []),
        }
    if heuristic["campaign_family"] not in {"unknown", api_family}:
        return {
            "campaign_name": name,
            "campaign_family": "unknown",
            "campaign_subtype": "unknown",
            "classification_source": "api_name_conflict",
            "api_type": api_type,
            "warnings": ["API placement metadata conflicts with the campaign-name heuristic; subtype cascade is disabled."],
        }
    subtype = (
        "brand_search" if api_family == "search" and heuristic["campaign_subtype"] == "brand_search"
        else "search" if api_family == "search"
        else "yan_retargeting" if heuristic["campaign_subtype"] == "yan_retargeting"
        else "yan_prospecting"
    )
    return {
        "campaign_name": name,
        "campaign_family": api_family,
        "campaign_subtype": subtype,
        "classification_source": "direct_api_strategy" if strategy_family else "direct_api_type",
        "api_type": api_type,
        "warnings": [],
    }


def classify_audit_campaigns(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    source_groups = (
        {"all": snapshot.get("campaignAnalysisRows") or []}
        if snapshot.get("campaignAnalysisRows") is not None
        else (snapshot.get("campaignGroups") or {})
    )
    for items in source_groups.values():
        for item in items or []:
            name = str(item.get("name") or "Кампания без названия")
            if name in seen:
                continue
            seen.add(name)
            api_metadata = (snapshot.get("campaignApiMetadata") or {}).get(name) or {}
            classification = _campaign_classification(name, api_metadata or {"type": item.get("type")})
            scope_key = (
                api_metadata.get("campaign_scope_key")
                or (snapshot.get("_trustedCampaignScopes") or {}).get(name)
            )
            if scope_key:
                classification["campaign_scope_key"] = scope_key
            result.append(classification)
    return result


def _classification_summary(classifications: list[dict[str, Any]]) -> dict[str, int]:
    """Expose only aggregate classification diagnostics; campaign identities stay private."""
    summary: dict[str, int] = {}
    for item in classifications:
        if not isinstance(item, dict):
            continue
        key = ":".join((
            str(item.get("campaign_family") or "unknown")[:40],
            str(item.get("campaign_subtype") or "unknown")[:40],
            str(item.get("classification_source") or "unknown")[:60],
        ))
        summary[key] = summary.get(key, 0) + 1
    return dict(sorted(summary.items()))


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


def _rule_codes_for_requests(
    requests: list[AuditDataRequest],
) -> tuple[list[str], list[str], list[str]]:
    capabilities = {request.capability_id or request.dimension for request in requests}
    prerequisites = ["selected_goal_data_available"] if "goals" in capabilities else []
    confirmation = [
        rule_code
        for capability, rule_code in CONFIRMATION_RULE_BY_CAPABILITY.items()
        if capability in capabilities
    ]
    rejection = [
        rule_code
        for capability, rule_code in REJECTION_RULE_BY_CAPABILITY.items()
        if capability in capabilities
    ]
    return prerequisites, confirmation, rejection


def _hypothesis_type_for_capabilities(capabilities: list[str] | set[str]) -> str:
    values = set(capabilities)
    for capability, hypothesis_type in (
        ("search_queries", "search_query_waste"),
        ("ad_group_performance", "ad_group_concentration"),
        ("ad_groups", "ad_group_concentration"),
        ("keyword_performance", "keyword_waste"),
        ("keywords", "keyword_waste"),
        ("devices", "device_segment_gap"),
        ("geo", "geo_segment_gap"),
        ("placements", "placement_waste"),
        ("retargeting_lists", "retargeting_segment_issue"),
        ("retargeting_segments", "retargeting_segment_issue"),
        ("goals", "tracking_issue"),
    ):
        if capability in values:
            return hypothesis_type
    return "campaign_metadata_issue"


def _hypothesis_policy(hypothesis: dict[str, Any]) -> dict[str, set[str]]:
    hypothesis_type = str(hypothesis.get("hypothesis_type") or "campaign_metadata_issue")
    return HYPOTHESIS_EVIDENCE_POLICY.get(
        hypothesis_type, HYPOTHESIS_EVIDENCE_POLICY["campaign_metadata_issue"],
    )


def _capability_matches_hypothesis(hypothesis: dict[str, Any], capability: str) -> bool:
    return capability in _hypothesis_policy(hypothesis)["allowed_capabilities"]


def _extend_hypothesis_contract(
    hypothesis: dict[str, Any], requests: list[AuditDataRequest],
) -> None:
    if not requests:
        return
    required = list(hypothesis.get("required_capabilities") or [])
    optional = list(hypothesis.get("optional_capabilities") or [])
    for request in requests:
        capability = request.capability_id or request.dimension
        if not _capability_matches_hypothesis(hypothesis, capability):
            continue
        target = required if request.required_for_conclusion else optional
        if capability not in target:
            target.append(capability)
        if request.required_for_conclusion and capability in optional:
            optional.remove(capability)
    trusted_requests = [
        request for request in requests
        if _capability_matches_hypothesis(hypothesis, request.capability_id or request.dimension)
    ]
    prerequisites, confirmations, rejections = _rule_codes_for_requests(trusted_requests)
    policy = _hypothesis_policy(hypothesis)
    confirmations = [code for code in confirmations if code in policy["confirmation_rule_codes"]]
    rejections = [code for code in rejections if code in policy["rejection_rule_codes"]]
    hypothesis["required_capabilities"] = required[:4]
    hypothesis["optional_capabilities"] = optional[:4]
    hypothesis["prerequisite_rule_codes"] = list(dict.fromkeys(
        list(hypothesis.get("prerequisite_rule_codes") or []) + prerequisites
    ))[:8]
    hypothesis["confirmation_rule_codes"] = list(dict.fromkeys(
        list(hypothesis.get("confirmation_rule_codes") or []) + confirmations
    ))[:8]
    hypothesis["rejection_rule_codes"] = list(dict.fromkeys(
        list(hypothesis.get("rejection_rule_codes") or []) + rejections
    ))[:8]


def _fresh_baseline_requests(snapshot: dict[str, Any]) -> list[AuditDataRequest]:
    period = snapshot.get("analysisPeriod") or {}
    common = {
        "campaign_name": "__all_campaigns__",
        "period": {
            "date_from": period.get("dateFrom"),
            "date_to": period.get("dateTo"),
            "days": period.get("days"),
        },
        "filters": {"campaign_name": "__all_campaigns__"},
        "priority": "high",
        "required_for_conclusion": True,
        "data_preference": "live_required",
    }
    return [
        AuditDataRequest(
            request_id="baseline_campaigns",
            hypothesis_id="baseline",
            campaign_family="unknown",
            campaign_subtype="unknown",
            dimension="campaigns",
            capability_id="campaigns",
            reason="Load current campaign names, statuses and API types before audit facts.",
            metrics=["name", "status", "state", "type"],
            **common,
        ),
        AuditDataRequest(
            request_id="baseline_campaign_performance",
            hypothesis_id="baseline",
            campaign_family="search",
            campaign_subtype="search",
            dimension="campaign_performance",
            capability_id="campaign_performance",
            reason="Load current campaign performance for the requested audit period.",
            metrics=["impressions", "clicks", "cost", "ctr", "avg_cpc", "conversions", "cpa", "conversion_rate"],
            **common,
        ),
    ]


_GOAL_METRIC_PATTERN = re.compile(
    r"^(conversions|cost_per_conversion|conversion_rate|revenue|goals_roi)_([^_]+)(?:_.+)?$"
)


def _row_per_goal_metrics(
    row: dict[str, Any], selected_goal_ids: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    selected = set(map(str, selected_goal_ids or []))
    metrics: dict[str, dict[str, float]] = {}
    for key, value in row.items():
        match = _GOAL_METRIC_PATTERN.match(str(key).lower())
        if not match:
            continue
        metric, goal_id = match.groups()
        if selected and goal_id not in selected:
            continue
        parsed = _number(value)
        if parsed is None:
            continue
        metrics.setdefault(goal_id, {})[metric] = float(parsed)
    return metrics


def _row_goal_conversion_details(
    row: dict[str, Any], selected_goal_ids: list[str] | None = None,
) -> tuple[float | None, bool, dict[str, dict[str, float]], str]:
    per_goal = _row_per_goal_metrics(row, selected_goal_ids)
    explicit = _number(row.get("goal_conversions"))
    provider_aggregate = _number(row.get("conversions"))
    if explicit is not None:
        return float(explicit), True, per_goal, "explicit_goal_conversions"
    if provider_aggregate is not None and len(selected_goal_ids or []) <= 10:
        return float(provider_aggregate), True, per_goal, "provider_selected_goals_aggregate"
    conversion_values = [item["conversions"] for item in per_goal.values() if "conversions" in item]
    if len(conversion_values) == 1 and len(selected_goal_ids or []) <= 1:
        return float(conversion_values[0]), True, per_goal, "single_selected_goal"
    if conversion_values:
        return None, True, per_goal, "per_goal_only_no_cross_goal_sum"
    return None, False, per_goal, "goal_data_unavailable"


def _row_goal_conversions(row: dict[str, Any]) -> tuple[float | None, bool]:
    conversions, available, _, _ = _row_goal_conversion_details(row)
    return conversions, available


def _apply_live_baseline(
    snapshot: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    allow_saved_fallback: bool,
) -> None:
    by_capability = {str(item.get("capability_id") or item.get("dimension")): item for item in results}
    campaign_result = by_capability.get("campaigns") or {}
    performance_result = by_capability.get("campaign_performance") or {}
    campaign_available = campaign_result.get("status") in AVAILABLE_AUDIT_DATA_STATUSES
    performance_available = performance_result.get("status") in AVAILABLE_AUDIT_DATA_STATUSES
    source_values = {
        str(item.get("source")) for item in (campaign_result, performance_result)
        if item.get("status") in AVAILABLE_AUDIT_DATA_STATUSES and item.get("source")
    }
    if source_values == {"yandex_direct_live_report"}:
        baseline_source = "yandex_direct_live_report"
    elif source_values and all(value.startswith("yandex_direct_live") for value in source_values):
        baseline_source = "yandex_direct_live"
    elif len(source_values) > 1:
        baseline_source = "mixed_live_and_saved"
    elif source_values:
        baseline_source = next(iter(source_values))
    else:
        baseline_source = "unavailable"
    evidence_source = str(
        performance_result.get("source")
        or ("yandex_direct_live_report" if performance_available else baseline_source)
    )
    fetched_at = max(
        (str(item.get("fetched_at")) for item in (campaign_result, performance_result) if item.get("fetched_at")),
        default=None,
    )
    metadata_by_name: dict[str, dict[str, Any]] = {}
    trusted_scopes = snapshot.setdefault("_trustedCampaignScopes", {})
    trusted_scope_names = snapshot.setdefault("_trustedCampaignScopeNames", {})
    ambiguous_scope_names = {
        str(item) for item in (snapshot.get("_ambiguousCampaignNames") or [])
    }
    for row in (campaign_result.get("data") or []):
        if not isinstance(row, dict) or not row.get("name"):
            continue
        name = str(row.get("name"))
        scope = str(row.get("campaign_scope_key") or row.get("campaignScopeKey") or "").strip() or campaign_scope_key(
            row.get("campaign_id") or row.get("CampaignId") or row.get("id")
        )
        metadata = {
            "type": row.get("type"), "status": row.get("status"), "state": row.get("state"),
            "text_campaign": row.get("text_campaign"),
            "mobile_app_campaign": row.get("mobile_app_campaign"),
            "cpm_banner_campaign": row.get("cpm_banner_campaign"),
            "unified_campaign": row.get("unified_campaign"),
            "campaign_scope_key": scope,
        }
        if scope:
            trusted_scope_names[scope] = name
        prior_scope = trusted_scopes.get(name)
        if name in ambiguous_scope_names or (prior_scope and scope and prior_scope != scope):
            ambiguous_scope_names.add(name)
            trusted_scopes.pop(name, None)
            metadata_by_name.pop(name, None)
            continue
        if scope:
            trusted_scopes[name] = scope
        metadata_by_name[name] = metadata
    # A campaign can be present in a fresh performance report while absent from
    # the current Campaigns service response (for example, historical data for
    # an archived campaign). The report already carries a one-way scope key;
    # register it so no-data follow-up reads stay terminal rather than becoming
    # indistinguishable from an unrequested campaign.
    for row_index, row in enumerate(performance_result.get("data") or [], start=1):
        if not isinstance(row, dict):
            continue
        name = str(row.get("campaign_name") or row.get("CampaignName") or "").strip()
        scope = str(row.get("campaign_scope_key") or row.get("campaignScopeKey") or "").strip() or campaign_scope_key(
            row.get("campaign_id") or row.get("CampaignId")
        )
        if not scope:
            continue
        if not name:
            # Direct performance rows occasionally omit CampaignName. Keep the
            # campaign in breadth coverage under a deterministic safe alias so
            # zero-row follow-ups resolve to an explicit terminal status rather
            # than silently dropping the campaign from evidence reconciliation.
            name = f"Campaign without name {row_index}"
            row["campaign_name"] = name
        trusted_scope_names[scope] = name
        prior_scope = trusted_scopes.get(name)
        if name in ambiguous_scope_names or (prior_scope and prior_scope != scope):
            ambiguous_scope_names.add(name)
            trusted_scopes.pop(name, None)
            metadata_by_name.pop(name, None)
            continue
        trusted_scopes[name] = scope
    for name in ambiguous_scope_names:
        trusted_scopes.pop(name, None)
        metadata_by_name.pop(name, None)
    snapshot["_ambiguousCampaignNames"] = sorted(ambiguous_scope_names)
    snapshot["_trustedCampaignScopeNames"] = trusted_scope_names
    snapshot["campaignApiMetadata"] = metadata_by_name
    if ambiguous_scope_names:
        limitations = snapshot.setdefault("evidenceIdentityLimitations", [])
        for name in sorted(ambiguous_scope_names):
            item = {
                "code": "ambiguous_campaign_identity",
                "campaignName": name,
                "message": "Имя кампании неоднозначно; доказательства не объединяются между кампаниями с одинаковым названием.",
            }
            if item not in limitations:
                limitations.append(item)
    baseline = {
        "policy": "fresh",
        "status": "complete" if campaign_available and performance_available else "partial",
        "campaignsAvailable": campaign_available,
        "performanceAvailable": performance_available,
        "allowSavedFallback": allow_saved_fallback,
        "savedFallbackUsed": False,
        "source": evidence_source,
        "fetchedAt": fetched_at,
        "failures": [
            {
                "capability_id": item.get("capability_id") or item.get("dimension"),
                "status": item.get("status"),
                "error_code": item.get("error_code"),
            }
            for item in results if item.get("status") not in AVAILABLE_AUDIT_DATA_STATUSES
        ],
    }
    if not performance_available:
        if allow_saved_fallback:
            baseline["savedFallbackUsed"] = True
        else:
            snapshot["campaignGroups"] = {key: [] for key in ("critical", "warning", "opportunity", "low_data", "stable")}
            snapshot["accountTotals"] = {
                "cost": 0, "impressions": 0, "clicks": 0, "goalConversions": None,
            }
        snapshot.setdefault("dataCoverage", {})["campaigns"] = {
            "available": 0, "total": 0, "analyzed": 0,
            "source": "yandex_direct_live", "freshness": "live_failed",
        }
        snapshot["freshBaseline"] = baseline
        return
    target_cpa = _number_or_zero((snapshot.get("targetKpis") or {}).get("targetCpa"))
    selected_goal_ids = [str(item) for item in (snapshot.get("selectedGoals") or {}).get("ids", [])]
    groups = {key: [] for key in ("critical", "warning", "opportunity", "low_data", "stable")}
    all_campaigns: list[dict[str, Any]] = []
    totals = {"cost": 0.0, "impressions": 0, "clicks": 0, "goalConversions": 0.0}
    has_goal_data = False
    aggregate_goal_rows_known = 0
    aggregate_goal_rows_unknown = 0
    performance_rows = performance_result.get("data") or []
    for row in performance_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("campaign_name") or "Campaign without name")
        cost = _number_or_zero(row.get("cost"))
        clicks = _int_or_zero(row.get("clicks"))
        impressions = _int_or_zero(row.get("impressions"))
        conversions, row_has_goals, per_goal_metrics, aggregation_policy = _row_goal_conversion_details(
            row, selected_goal_ids,
        )
        has_goal_data = has_goal_data or row_has_goals
        conversion_known = conversions is not None
        aggregate_goal_rows_known += int(conversion_known)
        aggregate_goal_rows_unknown += int(not conversion_known)
        ctr = _number_or_zero(row.get("ctr")) or (clicks / impressions * 100 if impressions else 0)
        cpa = cost / conversions if conversion_known and conversions > 0 else (0 if conversions == 0 else None)
        flags = []
        if cost > 0 and conversion_known and conversions == 0:
            flags.append("spend_without_conversions")
        if target_cpa and cpa is not None and cpa > target_cpa:
            flags.append("high_cpa")
        if impressions >= 1000 and ctr < 1:
            flags.append("low_ctr")
        sufficient = evaluate_metric_sufficiency(
            "spend_without_conversions" if conversions == 0 else "high_cpa",
            cost=cost, clicks=clicks, impressions=impressions, conversions=conversions or 0,
            target_cpa=target_cpa, period_days=int((snapshot.get("analysisPeriod") or {}).get("days") or 30),
        ).sufficient if conversion_known else False
        group = "low_data" if not sufficient else "critical" if flags[:1] and flags[0] == "spend_without_conversions" else "warning" if flags else "opportunity" if conversions and conversions > 0 else "stable"
        campaign_projection = {
            "name": name, "type": (metadata_by_name.get(name) or {}).get("type"),
            "status": (metadata_by_name.get(name) or {}).get("status"),
            "cost": cost, "clicks": clicks, "impressions": impressions, "ctr": ctr,
            "goalConversions": conversions, "goalCpa": cpa, "flags": flags,
            "selectedGoalIds": selected_goal_ids,
            "perGoalMetrics": per_goal_metrics,
            "aggregationPolicy": aggregation_policy,
            "diagnostic": "; ".join(flags) if flags else "No critical backend signal.",
        }
        groups[group].append(campaign_projection)
        all_campaigns.append(campaign_projection)
        totals["cost"] += cost
        totals["clicks"] += clicks
        totals["impressions"] += impressions
        if conversion_known:
            totals["goalConversions"] += conversions
    totals["ctr"] = totals["clicks"] / totals["impressions"] * 100 if totals["impressions"] else 0
    if aggregate_goal_rows_unknown:
        totals["goalConversions"] = None
        totals["goalCpa"] = None
    else:
        totals["goalCpa"] = totals["cost"] / totals["goalConversions"] if totals["goalConversions"] else 0
    totals["goalRowsKnown"] = aggregate_goal_rows_known
    totals["goalRowsUnknown"] = aggregate_goal_rows_unknown
    group_totals = {key: len(items) for key, items in groups.items()}
    for items in groups.values():
        items.sort(key=lambda item: float(item.get("cost") or 0), reverse=True)
        del items[5:]
    snapshot["campaignGroups"] = groups
    snapshot["campaignAnalysisRows"] = all_campaigns
    snapshot["accountTotals"] = totals
    if snapshot.get("selectedGoals"):
        snapshot["selectedGoals"]["hasGoalData"] = has_goal_data
    included = sum(len(items) for items in groups.values())
    baseline["campaignAggregates"] = {
        "campaignsTotal": len(performance_rows),
        "groupCounts": group_totals,
        "totals": totals,
    }
    coverage = snapshot.setdefault("dataCoverage", {})
    coverage["campaigns"] = {
        **(coverage.get("campaigns") or {}),
        "available": len(performance_rows),
        "total": len(performance_rows),
        "analyzed": len(performance_rows),
        "source": evidence_source,
        "freshness": "live" if evidence_source.startswith("yandex_direct_live") else "mixed_or_saved",
        "fetchedAt": fetched_at,
    }
    metadata = snapshot.setdefault("metadata", {})
    metadata.update({
        "campaignsTotal": len(performance_rows),
        "campaignsIncluded": included,
        "rowsReceived": len(performance_rows),
        "rowsAnalyzed": len(performance_rows),
        "rowsSentToAi": sum(
            int(item.get("rowsSentToAi") or 0) for item in (snapshot.get("baselineEvidenceSummary") or [])
        ),
        "truncated": len(performance_rows) > included,
        "campaignEvidenceSource": evidence_source,
        "campaignEvidenceFetchedAt": fetched_at,
    })
    analysis_period = snapshot.setdefault("analysisPeriod", {})
    analysis_period["source"] = evidence_source
    analysis_period["fetchedAt"] = fetched_at
    prompt_projection = {
        "analysisPeriod": snapshot.get("analysisPeriod") or {},
        "dataCoverage": coverage,
        "accountTotals": totals,
        "selectedGoals": snapshot.get("selectedGoals") or {},
        "campaignGroups": groups,
        "freshBaseline": baseline,
    }
    metadata["estimatedTokens"] = estimate_tokens(_json_dump(prompt_projection))
    snapshot["freshBaseline"] = baseline


def build_rule_based_investigation_plan(snapshot: dict[str, Any]) -> AuditInvestigationPlan:
    if not snapshot.get("observedFacts"):
        snapshot["observedFacts"] = [
            item.model_dump(mode="json") for item in build_observed_facts(snapshot)
        ]
    classifications = {item["campaign_name"]: item for item in classify_audit_campaigns(snapshot)}
    candidates = []
    for group_name in ("critical", "warning"):
        candidates.extend((snapshot.get("campaignGroups") or {}).get(group_name) or [])
    period = snapshot.get("analysisPeriod") or {}
    hypotheses = []
    facts_by_campaign: dict[str, list[dict[str, Any]]] = {}
    for fact_item in (snapshot.get("observedFacts") or []):
        facts_by_campaign.setdefault(str(fact_item.get("campaign_name") or ""), []).append(fact_item)
    def triggering_fact_ids(campaign_name: str, hypothesis_type: str) -> list[str]:
        campaign_facts = facts_by_campaign.get(campaign_name, [])
        required_metrics = set(HYPOTHESIS_EVIDENCE_POLICY[hypothesis_type]["required_fact_metrics"])
        fact_metrics = {
            "spend_without_goal_conversions": {"cost", "clicks", "goal_conversions"},
            "cpa_above_target": {"cost", "clicks", "goal_conversions"},
            "good_campaign": {"cost", "clicks", "goal_conversions"},
            "campaign_health": {"cost", "clicks", "goal_conversions"},
            "low_ctr": {"clicks"},
            "low_data": set(),
            "conversion_data_unknown": set(),
        }
        preferred = [
            fact for fact in campaign_facts
            if fact.get("sufficient_data") and fact.get("metric") not in {"low_data", "conversion_data_unknown"}
            and required_metrics <= fact_metrics.get(str(fact.get("metric")), set())
        ]
        selected = preferred[:1]
        return [str(fact["fact_id"]) for fact in selected if fact.get("fact_id")]

    for index, item in enumerate(candidates[:5], start=1):
        if len(hypotheses) >= 5:
            break
        name = str(item.get("name") or "Кампания без названия")
        classification = classifications[name]
        flags = item.get("flags") or []
        fact = str(item.get("diagnostic") or f"Сигналы: {', '.join(flags) or 'требуется проверка'}")[:700]
        hypothesis_id = f"hyp_{index:03d}"
        if classification["campaign_subtype"] == "unknown":
            requests = [
                _request(hypothesis_id, classification, "campaigns", "Уточнить тип и статус кампании до типоспецифичного анализа.", period, priority="high", required=True)
            ]
        else:
            requests = [_request(hypothesis_id, classification, "goals", "Проверить выбранные цели и CPA по ним.", period, priority="high", required=True)]
        if classification["campaign_subtype"] in {"search", "brand_search"}:
            requests.extend([
                _request(hypothesis_id, classification, "search_queries", "Проверить интент и расход поисковых запросов.", period, priority="high", required=True),
                _request(hypothesis_id, classification, "ad_groups", "Локализовать проблему по группам объявлений.", period),
            ])
            hypothesis = "Качество поискового трафика или отдельных групп может объяснять отклонение метрик."
        elif classification["campaign_subtype"] == "yan_retargeting":
            requests.extend([
                _request(hypothesis_id, classification, "retargeting_lists", "Проверить доступность списков ретаргетинга.", period, priority="high", required=True),
                _request(hypothesis_id, classification, "retargeting_segments", "Сравнить сегменты и окна ретаргетинга.", period, priority="high", required=True),
                _request(hypothesis_id, classification, "audience_targets", "Проверить аудиторные таргетинги кампании.", period),
            ])
            hypothesis = "Настройки сегментов ретаргетинга могут снижать эффективность кампании."
        elif classification["campaign_family"] == "yan":
            requests.extend([
                _request(hypothesis_id, classification, "placements", "Проверить площадки с неэффективным расходом.", period, priority="high", required=True),
                _request(hypothesis_id, classification, "audiences", "Сравнить доступные аудитории.", period),
            ])
            hypothesis = "Качество площадок или аудиторий может объяснять отклонение метрик."
        else:
            hypothesis = "Тип кампании не определён; сначала нужны безопасные данные по целям."
        hypothesis_type = _hypothesis_type_for_capabilities([
            request.dimension for request in requests if request.dimension != "goals"
        ])
        policy = HYPOTHESIS_EVIDENCE_POLICY[hypothesis_type]
        bound_fact_ids = triggering_fact_ids(name, hypothesis_type)
        if hypothesis_type not in {"tracking_issue", "campaign_metadata_issue"} and not bound_fact_ids:
            continue
        requests = [
            request for request in requests
            if request.dimension in policy["allowed_capabilities"]
        ]
        prerequisite_rule_codes, confirmation_rule_codes, rejection_rule_codes = _rule_codes_for_requests(requests)
        confirmation_rule_codes = [
            code for code in confirmation_rule_codes if code in policy["confirmation_rule_codes"]
        ]
        rejection_rule_codes = [
            code for code in rejection_rule_codes if code in policy["rejection_rule_codes"]
        ]
        hypotheses.append(AuditInvestigationHypothesis(
            hypothesis_id=hypothesis_id,
            hypothesis_type=hypothesis_type,
            campaign_name=name,
            campaign_family=classification["campaign_family"],
            campaign_subtype=classification["campaign_subtype"],
            observed_fact=fact,
            hypothesis=hypothesis,
            fact_ids=bound_fact_ids,
            rationale=fact,
            confidence_before_verification=(
                "medium" if any(item.get("sufficient_data") for item in facts_by_campaign.get(name, [])) else "low"
            ),
            required_capabilities=[request.dimension for request in requests if request.required_for_conclusion],
            optional_capabilities=[request.dimension for request in requests if not request.required_for_conclusion],
            forbidden_capabilities=(
                ["search_queries", "keywords", "autotargeting"]
                if classification["campaign_subtype"] == "yan_retargeting" else []
            ),
            confirmation_rules=["Обязательные read-only данные содержат измеримый подтверждающий сигнал."],
            rejection_rules=["Полученные данные противоречат предполагаемой причине."],
            prerequisite_rule_codes=prerequisite_rule_codes,
            confirmation_rule_codes=confirmation_rule_codes,
            rejection_rule_codes=rejection_rule_codes,
            stop_conditions=["Доказательств достаточно", "Следующие данные недоступны"],
            data_requests=requests[:4],
        ))
        if classification["campaign_subtype"] == "yan_retargeting" and len(hypotheses) < 5:
            placement_id = f"hyp_{index:03d}_placement"
            placement_request = _request(
                placement_id, classification, "placements",
                "Отдельно проверить площадки с расходом без целевых конверсий.", period,
                priority="medium", required=True,
            )
            hypotheses.append(AuditInvestigationHypothesis(
                hypothesis_id=placement_id,
                hypothesis_type="placement_waste",
                campaign_name=name,
                campaign_family=classification["campaign_family"],
                campaign_subtype=classification["campaign_subtype"],
                observed_fact=fact,
                hypothesis="Отдельные площадки могут создавать неэффективный расход.",
                fact_ids=triggering_fact_ids(name, "placement_waste"),
                rationale=fact,
                confidence_before_verification="medium",
                required_capabilities=["placements"],
                forbidden_capabilities=["search_queries", "keywords", "autotargeting"],
                confirmation_rules=["Площадки содержат измеримый расход без выбранных конверсий."],
                rejection_rules=["Данные площадок не показывают материального неэффективного расхода."],
                prerequisite_rule_codes=[],
                confirmation_rule_codes=["placements_waste_without_goals"],
                rejection_rule_codes=["placements_no_material_waste"],
                stop_conditions=["Доказательств достаточно", "Данные площадок недоступны"],
                data_requests=[placement_request],
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
    campaign_families = {str(item.get("campaign_family")) for item in classifications}
    campaign_subtypes = {str(item.get("campaign_subtype")) for item in classifications}
    compact_manifest = []
    for item in public_audit_tool_manifest():
        families = set(item.get("supported_campaign_families") or [])
        subtypes = set(item.get("supported_campaign_subtypes") or [])
        if item.get("supported_now") and (
            (not campaign_families or families & campaign_families)
            and (not campaign_subtypes or subtypes & campaign_subtypes)
        ):
            compact_manifest.append({
                "id": item.get("id"),
                "families": sorted(families & campaign_families) or sorted(families),
                "subtypes": sorted(subtypes & campaign_subtypes) or sorted(subtypes),
            })
    planned_capabilities = {
        str(request.get("capability_id") or request.get("dimension"))
        for hypothesis in (snapshot.get("ruleBasedInvestigationPlan") or {}).get("hypotheses", [])
        for request in (hypothesis.get("data_requests") or [])
    }
    capability_descriptions = []
    for capability_id in sorted(planned_capabilities)[:8]:
        description = describe_direct_capability(capability_id)
        compact_description = {
            "id": capability_id,
            "source_type": description.get("source_type"),
            "supported_now": description.get("supported_now"),
        }
        if description.get("prerequisites"):
            compact_description["prerequisites"] = description["prerequisites"]
        if description.get("limitations"):
            compact_description["limitations"] = description["limitations"]
        capability_descriptions.append(compact_description)
    return {
        "directApiKnowledgeVersion": DIRECT_API_KNOWLEDGE_VERSION,
        "analysisPeriod": snapshot.get("analysisPeriod") or {},
        "observedFacts": (snapshot.get("observedFacts") or [])[:10],
        "accountTotals": snapshot.get("accountTotals") or {},
        "targetKpis": snapshot.get("targetKpis") or {},
        "campaigns": selected_campaigns,
        "campaignClassifications": classifications,
        "dataCoverage": snapshot.get("dataCoverage") or {},
        "ruleBasedInvestigationPlan": snapshot.get("ruleBasedInvestigationPlan") or {},
        "publicToolManifest": compact_manifest,
        "capabilityDescriptions": capability_descriptions,
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
Для каждой гипотезы заполни fact_ids, rationale, required_capabilities, optional_capabilities,
forbidden_capabilities, confirmation_rules, rejection_rules и stop_conditions. Не давай финальных рекомендаций.
Backend связывает вывод с prerequisite_rule_codes, confirmation_rule_codes и rejection_rule_codes; не используй правило одной capability для подтверждения другой.
Каждый дополнительный запрос должен объяснять expected information gain: какой результат изменит вывод.
Не передавай campaign ID, endpoint, token или credentials. Верни только JSON AuditInvestigationPlan без Markdown.

Planner context:
{json.dumps(planner_context, ensure_ascii=False, separators=(',', ':'))}"""


def _merge_investigation_plans(
    proposed: AuditInvestigationPlan,
    snapshot: dict[str, Any],
    fallback: AuditInvestigationPlan,
) -> AuditInvestigationPlan:
    classifications = {item["campaign_name"]: item for item in (snapshot.get("campaignClassifications") or [])}
    normalized: list[AuditInvestigationHypothesis] = []
    used_proposed: set[int] = set()
    used_ids: set[str] = set()
    facts_by_id = {
        str(item.get("fact_id")): item for item in (snapshot.get("observedFacts") or [])
        if item.get("fact_id")
    }

    def reject(source: AuditInvestigationHypothesis, code: str, message: str) -> None:
        rejections = snapshot.setdefault("validationRejections", [])
        item = {
            "hypothesisId": source.hypothesis_id,
            "campaignName": source.campaign_name,
            "status": "rejected_by_validation",
            "errorCode": code,
            "message": message,
        }
        if item not in rejections:
            rejections.append(item)
        warnings = snapshot.setdefault("auditWarnings", [])
        warning = _helper_warning("create_investigation_plan", code, message)
        if not any(existing.get("code") == code for existing in warnings if isinstance(existing, dict)):
            warnings.append(warning)

    def has_trusted_binding(source: AuditInvestigationHypothesis, base: AuditInvestigationHypothesis) -> bool:
        if source.campaign_name != base.campaign_name or source.hypothesis_type != base.hypothesis_type:
            return False
        fact_ids = list(source.fact_ids or base.fact_ids)
        facts = [facts_by_id.get(str(fact_id)) for fact_id in fact_ids]
        if not fact_ids or any(fact is None for fact in facts):
            return False
        if any(str(fact.get("campaign_name")) != base.campaign_name for fact in facts if fact):
            return False
        if source.parent_hypothesis_id and source.parent_hypothesis_id != base.parent_hypothesis_id:
            return False
        if base.hypothesis_type not in {"tracking_issue", "campaign_metadata_issue"} and not any(
            bool(fact.get("sufficient_data")) for fact in facts if fact
        ):
            return False
        return True

    def proposed_for(base: AuditInvestigationHypothesis, index: int) -> AuditInvestigationHypothesis | None:
        for proposed_index, item in enumerate(proposed.hypotheses):
            if proposed_index not in used_proposed and item.hypothesis_id == base.hypothesis_id:
                used_proposed.add(proposed_index)
                return item
        if index < len(proposed.hypotheses):
            item = proposed.hypotheses[index]
            if index not in used_proposed and item.campaign_name == base.campaign_name:
                used_proposed.add(index)
                return item
        return None

    def normalize_hypothesis(
        source: AuditInvestigationHypothesis,
        base: AuditInvestigationHypothesis,
        stable_id: str,
    ) -> AuditInvestigationHypothesis | None:
        classification = classifications.get(base.campaign_name)
        if not classification:
            return None
        proposed_requests = {request.dimension: request for request in source.data_requests}
        requests: list[AuditDataRequest] = []
        included_dimensions: set[str] = set()
        request_prefix = stable_id[4:] if stable_id.startswith("hyp_") else stable_id
        for base_request in base.data_requests:
            if not _capability_matches_hypothesis(base.model_dump(mode="json"), base_request.dimension):
                continue
            proposed_request = proposed_requests.get(base_request.dimension)
            if source is not base and not base_request.required_for_conclusion and not proposed_request:
                continue
            payload = base_request.model_dump()
            if proposed_request:
                payload["reason"] = str(proposed_request.reason)[:500]
                payload["priority"] = proposed_request.priority
            payload.update({
                "request_id": f"req_{request_prefix}_{len(requests) + 1:02d}",
                "hypothesis_id": stable_id,
                "campaign_name": base.campaign_name,
                "campaign_family": classification["campaign_family"],
                "campaign_subtype": classification["campaign_subtype"],
                "filters": {"campaign_name": base.campaign_name},
            })
            requests.append(AuditDataRequest.model_validate(payload))
            included_dimensions.add(base_request.dimension)
        for proposed_request in source.data_requests:
            if proposed_request.dimension in included_dimensions or len(requests) >= 4:
                continue
            if not _capability_matches_hypothesis(base.model_dump(mode="json"), proposed_request.dimension):
                continue
            payload = proposed_request.model_dump()
            payload.update({
                "request_id": f"req_{request_prefix}_{len(requests) + 1:02d}",
                "hypothesis_id": stable_id,
                "campaign_name": base.campaign_name,
                "campaign_family": classification["campaign_family"],
                "campaign_subtype": classification["campaign_subtype"],
                "filters": {"campaign_name": base.campaign_name},
                "required_for_conclusion": False,
            })
            requests.append(AuditDataRequest.model_validate(payload))
            included_dimensions.add(proposed_request.dimension)
        prerequisite_codes, confirmation_codes, rejection_codes = _rule_codes_for_requests(requests)
        policy = HYPOTHESIS_EVIDENCE_POLICY[base.hypothesis_type]
        confirmation_codes = [code for code in confirmation_codes if code in policy["confirmation_rule_codes"]]
        rejection_codes = [code for code in rejection_codes if code in policy["rejection_rule_codes"]]
        requested_prerequisites = source.prerequisite_rule_codes or base.prerequisite_rule_codes
        requested_confirmations = source.confirmation_rule_codes or base.confirmation_rule_codes
        return AuditInvestigationHypothesis(
            hypothesis_id=stable_id,
            hypothesis_type=base.hypothesis_type,
            parent_hypothesis_id=source.parent_hypothesis_id or base.parent_hypothesis_id,
            supersedes_hypothesis_id=source.supersedes_hypothesis_id or base.supersedes_hypothesis_id,
            campaign_name=base.campaign_name,
            campaign_family=classification["campaign_family"],
            campaign_subtype=classification["campaign_subtype"],
            observed_fact=base.observed_fact,
            hypothesis=str(source.hypothesis or base.hypothesis)[:700],
            fact_ids=base.fact_ids,
            rationale=source.rationale or base.rationale,
            confidence_before_verification=source.confidence_before_verification,
            required_capabilities=[request.dimension for request in requests if request.required_for_conclusion],
            optional_capabilities=[request.dimension for request in requests if not request.required_for_conclusion],
            forbidden_capabilities=base.forbidden_capabilities,
            confirmation_rules=source.confirmation_rules or base.confirmation_rules,
            rejection_rules=source.rejection_rules or base.rejection_rules,
            prerequisite_rule_codes=[
                code for code in requested_prerequisites if code in prerequisite_codes
            ] or prerequisite_codes,
            confirmation_rule_codes=[
                code for code in requested_confirmations if code in confirmation_codes
            ] or confirmation_codes,
            rejection_rule_codes=[
                code for code in (source.rejection_rule_codes or base.rejection_rule_codes)
                if code in rejection_codes
            ] or rejection_codes,
            stop_conditions=source.stop_conditions or base.stop_conditions,
            data_requests=requests,
        )

    for index, base_hypothesis in enumerate(fallback.hypotheses[:5]):
        stable_id = base_hypothesis.hypothesis_id
        if stable_id in used_ids:
            stable_id = f"hyp_{len(used_ids) + 1:03d}"
        proposed_source = proposed_for(base_hypothesis, index)
        if proposed_source is not None and not has_trusted_binding(proposed_source, base_hypothesis):
            reject(
                proposed_source,
                "untrusted_fact_binding",
                "AI-гипотеза отклонена backend-валидатором: отсутствует trusted fact той же кампании.",
            )
            source = base_hypothesis
        else:
            source = proposed_source or base_hypothesis
        item = normalize_hypothesis(source, base_hypothesis, stable_id)
        if item:
            normalized.append(item)
            used_ids.add(stable_id)

    for proposed_index, source in enumerate(proposed.hypotheses):
        if proposed_index not in used_proposed:
            reject(
                source,
                "untrusted_fact_binding",
                "Новая независимая AI-гипотеза разрешена только через trusted child-hypothesis lifecycle.",
            )
    return AuditInvestigationPlan(hypotheses=normalized) if normalized else fallback


def _parse_investigation_plan(
    answer: str,
    snapshot: dict[str, Any],
    fallback: AuditInvestigationPlan,
) -> tuple[AuditInvestigationPlan, bool, dict[str, Any]]:
    proposed, parsing = _parse_model_json(answer, AuditInvestigationPlan)
    if proposed is None or not proposed.hypotheses:
        return fallback, False, parsing
    return _merge_investigation_plans(proposed, snapshot, fallback), True, parsing


def _normalized_investigation_plan(answer: str, snapshot: dict[str, Any], fallback: AuditInvestigationPlan) -> AuditInvestigationPlan:
    return _parse_investigation_plan(answer, snapshot, fallback)[0]


def build_verification_prompt(snapshot: dict[str, Any]) -> str:
    active_hypotheses = _active_hypotheses(snapshot)
    active_ids = {str(item.get("hypothesis_id")) for item in active_hypotheses}
    active_plan = {"hypotheses": active_hypotheses}
    summaries = [
        item for item in (snapshot.get("drilldownEvidenceSummaries") or [])
        if str(item.get("hypothesis_id")) in active_ids
    ]
    samples = [
        item for item in (snapshot.get("aiDrilldownSamples") or snapshot.get("drilldownResults") or [])
        if str(item.get("hypothesis_id")) in active_ids
    ]
    return f"""Проверь максимум 5 гипотез только по собранным read-only данным. Ответ должен быть кратким.
Верни только JSON объекта
{{"verifications":[{{"hypothesis_id":"hyp_001","status":"confirmed|partially_confirmed|rejected|unverified|not_applicable","verification_summary":"...","supporting_evidence":[],"contradicting_evidence":[],"limitations":[],"remaining_data_needed":[]}}]}}.
Не подтверждай гипотезу из-за правдоподобия. unavailable/insufficient_data означает unverified; все not_applicable означает not_applicable.
Investigation plan: {json.dumps(active_plan, ensure_ascii=False)}
Backend evidence summaries: {json.dumps(summaries, ensure_ascii=False)}
Representative AI samples: {json.dumps(samples, ensure_ascii=False)}"""


def _verification_fallback(
    snapshot: dict[str, Any], full_results: list[dict[str, Any]] | None = None,
) -> AuditHypothesisVerificationSet:
    results = full_results if full_results is not None else (snapshot.get("drilldownResults") or [])
    previous = _verification_registry(snapshot)
    verifications = []
    for hypothesis in _active_hypotheses(snapshot):
        related = [item for item in results if item.get("hypothesis_id") == hypothesis.get("hypothesis_id")]
        statuses = {item.get("status") for item in related}
        status_value = (
            "rejected" if (previous.get(hypothesis.get("hypothesis_id")) or {}).get("status") == "rejected"
            else "not_applicable" if statuses == {"not_applicable"}
            else "unverified"
        )
        verifications.append(AuditHypothesisVerification(
            hypothesis_id=hypothesis.get("hypothesis_id"), status=status_value,
            verification_summary="AI-проверка недоступна; backend не считает гипотезу подтверждённой.",
            limitations=[
                item.get("summary")
                for item in related
                if item.get("status") not in AVAILABLE_AUDIT_DATA_STATUSES and item.get("summary")
            ][:5],
            remaining_data_needed=[
                item.get("dimension")
                for item in related
                if item.get("status") not in AVAILABLE_AUDIT_DATA_STATUSES
            ][:5],
        ))
    return AuditHypothesisVerificationSet(verifications=verifications)


def _parse_verifications(
    answer: str,
    snapshot: dict[str, Any],
    full_results: list[dict[str, Any]] | None = None,
) -> tuple[AuditHypothesisVerificationSet, bool, dict[str, Any]]:
    parsed, parsing = _parse_model_json(answer, AuditHypothesisVerificationSet)
    if parsed is None:
        return _verification_fallback(snapshot, full_results), False, parsing
    hypotheses = _active_hypotheses(snapshot)
    expected = {item.get("hypothesis_id") for item in hypotheses}
    hypotheses_by_id = {item.get("hypothesis_id"): item for item in hypotheses}
    previous = _verification_registry(snapshot)
    facts_by_id = {item.get("fact_id"): item for item in (snapshot.get("observedFacts") or [])}
    safe = []
    for item in parsed.verifications:
        if item.hypothesis_id not in expected:
            continue
        hypothesis = hypotheses_by_id[item.hypothesis_id]
        fact_ids = hypothesis.get("fact_ids") or []
        hypothesis = {
            **hypothesis,
            "status": (previous.get(item.hypothesis_id) or {}).get("status") or hypothesis.get("current_status"),
            "fact_sufficient_data": all(
                bool((facts_by_id.get(fact_id) or {}).get("sufficient_data")) for fact_id in fact_ids
            ) if fact_ids else False,
        }
        safe.append(enforce_hypothesis_verification(
            item,
            hypothesis=hypothesis,
            requests=hypothesis.get("data_requests") or [],
            results=full_results if full_results is not None else (snapshot.get("drilldownResults") or []),
            target_cpa=float((snapshot.get("targetKpis") or {}).get("targetCpa") or 0),
            period_days=int((snapshot.get("analysisPeriod") or {}).get("days") or 30),
        ))
    if not safe:
        return _verification_fallback(snapshot, full_results), False, parsing
    return AuditHypothesisVerificationSet(verifications=safe), True, parsing


def _apply_verification_statuses(snapshot: dict[str, Any], verification: AuditHypothesisVerificationSet) -> None:
    _merge_verification_registry(snapshot, verification)
    statuses = {
        str(item.get("hypothesis_id")): str(item.get("status"))
        for item in _active_verifications(snapshot)
    }
    for hypothesis in _active_hypotheses(snapshot):
        hypothesis_id = hypothesis.get("hypothesis_id")
        previous_status = hypothesis.get("current_status")
        if previous_status == "rejected":
            continue
        if hypothesis_id in statuses:
            hypothesis["current_status"] = statuses[hypothesis_id]
    if snapshot.get("investigationRounds"):
        for hypothesis in snapshot["investigationRounds"][-1].get("hypotheses") or []:
            hypothesis_id = hypothesis.get("hypothesis_id")
            if hypothesis_id in statuses:
                hypothesis["status"] = statuses[hypothesis_id]
    _sync_active_investigation_plan(snapshot)


def reconcile_collected_audit_evidence(
    snapshot: dict[str, Any], full_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconcile policy and AI evidence before final generation without new API calls."""

    index = build_canonical_evidence_index(snapshot, full_results)
    facts_by_id = {
        str(item.get("fact_id")): item
        for item in snapshot.get("observedFacts") or []
        if isinstance(item, dict) and item.get("fact_id")
    }
    prior = _verification_registry(snapshot)
    reconciled: list[AuditHypothesisVerification] = []
    linked_summaries: list[dict[str, Any]] = []
    for hypothesis in _active_hypotheses(snapshot):
        hypothesis_id = str(hypothesis.get("hypothesis_id") or "")
        requests, results = evidence_for_hypothesis(snapshot, hypothesis, index)
        current = prior.get(hypothesis_id) or {}
        proposed = AuditHypothesisVerification(
            hypothesis_id=hypothesis_id,
            status=str(current.get("status") or "unverified"),
            verification_summary=str(
                current.get("verification_summary")
                or "Backend повторно сопоставил гипотезу с фактически собранными данными."
            ),
            supporting_evidence=list(current.get("supporting_evidence") or []),
            contradicting_evidence=list(current.get("contradicting_evidence") or []),
            limitations=list(current.get("limitations") or []),
            remaining_data_needed=list(current.get("remaining_data_needed") or []),
        )
        fact_ids = [str(item) for item in (hypothesis.get("fact_ids") or [])]
        trusted_hypothesis = {
            **hypothesis,
            "status": current.get("status") or hypothesis.get("current_status"),
            "fact_sufficient_data": all(
                bool((facts_by_id.get(fact_id) or {}).get("sufficient_data"))
                for fact_id in fact_ids
            ) if fact_ids else False,
        }
        enforced = enforce_hypothesis_verification(
            proposed,
            hypothesis=trusted_hypothesis,
            requests=requests,
            results=results,
            target_cpa=float((snapshot.get("targetKpis") or {}).get("targetCpa") or 0),
            period_days=int((snapshot.get("analysisPeriod") or {}).get("days") or 30),
        )
        limitations = list(enforced.limitations)
        truly_missing: list[str] = []
        required_capabilities = {
            str(item.get("capability_id") or item.get("dimension") or "")
            for item in requests if item.get("required_for_conclusion")
        }
        required_capabilities.update(
            str(item) for item in (hypothesis.get("required_capabilities") or []) if str(item)
        )
        hypothesis_scope = campaign_scope_for_name(snapshot, hypothesis.get("campaign_name"))
        entries = {
            candidate: item
            for item in index.get("entries") or []
            if item.get("scopeKey") == hypothesis_scope
            if any(
                str(result.get("request_id")) == str(item.get("requestId"))
                for result in results
            )
            for candidate in capability_candidates(item.get("capabilityId"))
        }
        for capability in sorted(required_capabilities):
            entry = next(
                (entries.get(candidate) for candidate in capability_candidates(capability) if entries.get(candidate)),
                None,
            )
            if entry and int(entry.get("rowsReceived") or 0) > 0:
                if entry.get("dataQuality") != "sufficient":
                    limitations.append(
                        f"{capability}: данные собраны, но вывод ограничен ({entry.get('qualityReason') or 'low_data'})."
                    )
                continue
            if entry and entry.get("status") == "not_applicable":
                continue
            reason = (entry or {}).get("qualityReason") or "not_collected"
            truly_missing.append(capability)
            limitations.append(f"{capability}: данные недоступны ({reason}).")
        enforced = enforced.model_copy(update={
            "remaining_data_needed": truly_missing[:8],
            "limitations": list(dict.fromkeys(limitations))[:8],
        })
        reconciled.append(enforced)
        for summary in enforced.evidence_summaries:
            linked_summaries.append({**summary, "hypothesis_id": hypothesis_id})
    if reconciled:
        _apply_verification_statuses(
            snapshot, AuditHypothesisVerificationSet(verifications=reconciled),
        )
    # Keep campaign-scoped diagnostics for every collected capability, not only
    # the at-most-five active hypotheses. The final campaign table is a backend
    # projection over all trusted evidence, so dropping these summaries here
    # turns already collected query/device/geo rows back into generic advice.
    campaign_results = [
        item.get("result")
        for item in index.get("entries") or []
        if item.get("scope") == "campaign"
        and isinstance(item.get("result"), dict)
    ]
    campaign_summaries = _drilldown_evidence_summaries(snapshot, campaign_results)
    merged_summaries: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for summary in campaign_summaries + linked_summaries:
        key = (
            str(summary.get("campaign_name") or summary.get("campaignName") or ""),
            str(summary.get("capability_id") or summary.get("capabilityId") or ""),
            str(summary.get("request_id") or summary.get("requestId") or ""),
            str(summary.get("hypothesis_id") or summary.get("hypothesisId") or ""),
        )
        merged_summaries[key] = summary
    snapshot["drilldownEvidenceSummaries"] = list(merged_summaries.values())
    coverage = canonical_coverage_projection(index, snapshot)
    snapshot["canonicalEvidenceCoverage"] = coverage
    apply_canonical_coverage_to_registry(snapshot, index)

    requested = snapshot.get("analysisPeriod") or {}
    requested_from = str(requested.get("dateFrom") or "")
    requested_to = str(requested.get("dateTo") or "")
    checkable_periods: list[tuple[str, str, str, str]] = []
    mismatches: list[dict[str, str]] = []
    for item in index.get("entries") or []:
        if (
            item.get("status") not in AVAILABLE_AUDIT_DATA_STATUSES
            or not item.get("live")
            or item.get("cached")
            or item.get("savedFallback")
        ):
            continue
        period = item.get("period") or {}
        date_from = str(period.get("date_from") or period.get("dateFrom") or "")
        date_to = str(period.get("date_to") or period.get("dateTo") or "")
        if not date_from or not date_to:
            continue
        key = (
            str(item.get("campaignName") or "Аккаунт"),
            str(item.get("capabilityId") or "unknown"),
            date_from,
            date_to,
        )
        if key not in checkable_periods:
            checkable_periods.append(key)
        if requested_from and requested_to and (date_from != requested_from or date_to != requested_to):
            mismatches.append({
                "campaignName": key[0],
                "capabilityId": key[1],
                "reasonCode": "evidence_period_mismatch",
            })
    requested["evidencePeriodsChecked"] = len(checkable_periods)
    requested["requestedMatchesAvailableData"] = bool(
        checkable_periods and requested_from and requested_to and not mismatches
    )
    snapshot["periodEvidenceLimitations"] = mismatches[:20]
    for mismatch in mismatches:
        for section in ("accountWide", "campaignScoped"):
            for item in coverage.get(section) or []:
                if (
                    str(item.get("campaignName") or "Аккаунт") == mismatch["campaignName"]
                    and str(item.get("capabilityId") or "unknown") == mismatch["capabilityId"]
                ):
                    item["limitations"] = list(dict.fromkeys([
                        *(item.get("limitations") or []),
                        "Фактический период evidence отличается от запрошенного периода аудита.",
                    ]))[:5]
    return index


def _normalized_verifications(answer: str, snapshot: dict[str, Any]) -> AuditHypothesisVerificationSet:
    return _parse_verifications(answer, snapshot)[0]


_REMEDIATION_HYPOTHESIS_TYPES = {
    "search_queries": "search_query_waste",
    "ad_group_performance": "ad_group_concentration",
    "keyword_performance": "keyword_waste",
    "placements": "placement_waste",
    "devices": "device_segment_gap",
    "geo": "geo_segment_gap",
}


def _diagnostic_remediation_requests(
    snapshot: dict[str, Any],
    *,
    round_number: int,
    remaining_budget: int,
) -> list[AuditDataRequest]:
    """Repeat concrete but quality-limited factors on 60/90-day windows."""

    if remaining_budget <= 0:
        return []
    classifications = {
        str(item.get("campaign_name") or ""): item
        for item in (snapshot.get("campaignClassifications") or [])
        if isinstance(item, dict) and item.get("campaign_name")
    }
    validated = [
        item for item in (snapshot.get("validatedDataRequests") or [])
        if isinstance(item, dict)
    ]
    date_to_raw = str((snapshot.get("analysisPeriod") or {}).get("dateTo") or "")
    try:
        date_to = datetime.fromisoformat(date_to_raw).date()
    except ValueError:
        return []
    candidates: list[AuditDataRequest] = []
    registry = _hypothesis_registry(snapshot)
    for summary in snapshot.get("drilldownEvidenceSummaries") or []:
        if len(candidates) >= min(15, remaining_budget):
            break
        if not isinstance(summary, dict) or summary.get("sufficient_data") is True:
            continue
        if str(summary.get("stop_reason") or "") not in {"low_data", "unknown_conversion_metric"}:
            continue
        capability = str(summary.get("capability_id") or summary.get("dimension") or "")
        hypothesis_type = _REMEDIATION_HYPOTHESIS_TYPES.get(capability)
        campaign_name = str(summary.get("campaign_name") or "")
        classification = classifications.get(campaign_name)
        diagnostics = summary.get("diagnostics")
        if not hypothesis_type or not classification or not isinstance(diagnostics, dict):
            continue
        has_factor = bool(
            diagnostics.get("top_waste")
            or diagnostics.get("top_high_cpa")
            or (
                diagnostics.get("kind") == "segment_comparison"
                and float(diagnostics.get("cpa_ratio") or 0) > 1
            )
        )
        if not has_factor:
            continue
        prior_requests = [
            item for item in validated
            if str(item.get("campaign_name") or "") == campaign_name
            and str(item.get("capability_id") or item.get("dimension") or "") == capability
        ]
        prior_days = max(
            [int((item.get("period") or {}).get("days") or 0) for item in prior_requests]
            or [int((snapshot.get("analysisPeriod") or {}).get("days") or 30)]
        )
        extended_days = 60 if prior_days < 60 else 90 if prior_days < 90 else None
        if not extended_days:
            continue
        if any(
            item.campaign_name == campaign_name
            and (item.capability_id or item.dimension) == capability
            and int(item.period.days or 0) == extended_days
            for item in candidates
        ):
            continue
        hypothesis_id = f"remediation_r{round_number + 1}_{len(candidates) + 1:03d}"
        fact_ids = [
            str(item.get("fact_id"))
            for item in (snapshot.get("observedFacts") or [])
            if item.get("campaign_name") == campaign_name and item.get("fact_id")
        ][:5]
        registry[hypothesis_id] = {
            "hypothesis_id": hypothesis_id,
            "hypothesis_type": hypothesis_type,
            "parent_hypothesis_id": summary.get("hypothesis_id"),
            "fact_ids": fact_ids,
            "campaign_name": campaign_name,
            "campaign_family": classification.get("campaign_family") or "unknown",
            "campaign_subtype": classification.get("campaign_subtype") or "unknown",
            "hypothesis": f"Измеримый фактор в срезе {capability} сохраняется на расширенном периоде.",
            "rationale": (
                f"Данные за {prior_days} дней выявили фактор, но их качество недостаточно "
                "для детерминированного подтверждения."
            ),
            "current_status": "unverified",
            "required_capabilities": [capability],
            "optional_capabilities": [],
            "confirmation_rule_codes": [CONFIRMATION_RULE_BY_CAPABILITY[capability]],
            "rejection_rule_codes": [REJECTION_RULE_BY_CAPABILITY[capability]],
            "remaining_data_needed": [capability],
            "investigation_round": round_number + 1,
        }
        extended_period = {
            "dateFrom": (date_to - timedelta(days=extended_days - 1)).isoformat(),
            "dateTo": date_to.isoformat(),
            "days": extended_days,
        }
        candidate = _request(
            hypothesis_id,
            classification,
            capability,
            (
                f"Backend нашёл измеримый фактор, но данных за {prior_days} дней недостаточно; "
                f"повторить тот же read-only срез за {extended_days} дней."
            ),
            extended_period,
            priority="high",
            required=True,
        )
        candidate.request_id = (
            f"remediation_r{round_number + 1}_{len(candidates) + 1:03d}_{capability}_{extended_days}d"
        )
        candidates.append(candidate)
    snapshot["hypothesisRegistry"] = registry
    return candidates


def _validated_diagnostic_remediation_requests(
    snapshot: dict[str, Any],
) -> list[AuditDataRequest]:
    """Prefer deterministic 60/90-day checks before another AI planning call."""

    runtime = _audit_runtime(snapshot)
    round_number = int(runtime.get("investigationRound") or 1)
    request_count = int(runtime.get("requestsCount") or 0)
    max_rounds = int(runtime.get("maxDepthRounds") or MAX_INVESTIGATION_ROUNDS)
    max_requests = int(runtime.get("requestSafetyLimit") or MAX_DATA_REQUESTS_PER_AUDIT)
    if round_number >= max_rounds or request_count >= max_requests:
        return []
    candidates = _diagnostic_remediation_requests(
        snapshot,
        round_number=round_number,
        remaining_budget=max_requests - request_count,
    )
    accepted, rejected = validate_audit_data_requests(
        candidates,
        max_requests=max_requests,
    )
    if rejected:
        snapshot["drilldownResults"] = (
            snapshot.get("drilldownResults") or []
        ) + [item.model_dump(mode="json") for item in rejected]
    return accepted


def _second_round_requests(snapshot: dict[str, Any]) -> list[AuditDataRequest]:
    runtime = _audit_runtime(snapshot)
    round_number = int(runtime.get("investigationRound") or 1)
    request_count = int(runtime.get("requestsCount") or 0)
    max_rounds = int(runtime.get("maxDepthRounds") or MAX_INVESTIGATION_ROUNDS)
    max_requests = int(runtime.get("requestSafetyLimit") or MAX_DATA_REQUESTS_PER_AUDIT)
    if round_number >= max_rounds or request_count >= max_requests:
        return []
    hypotheses = {
        item.get("hypothesis_id"): item
        for item in _active_hypotheses(snapshot)
    }
    verifications = _verification_registry(snapshot)
    existing_by_hypothesis = {
        (item.get("hypothesis_id"), item.get("capability_id") or item.get("dimension"))
        for item in (snapshot.get("validatedDataRequests") or [])
    }
    candidates = _diagnostic_remediation_requests(
        snapshot,
        round_number=round_number,
        remaining_budget=max_requests - request_count,
    )
    for hypothesis_id, hypothesis in hypotheses.items():
        verification = verifications.get(hypothesis_id) or {}
        if verification.get("status") not in {"unverified", "partially_confirmed"}:
            continue
        related = [
            item for item in (snapshot.get("drilldownResults") or [])
            if item.get("hypothesis_id") == hypothesis_id
        ]
        low_volume = next(
            (
                item for item in related
                if item.get("status") == "insufficient_data"
                and (item.get("capability_id") or item.get("dimension"))
            ),
            None,
        )
        if low_volume:
            capability = str(low_volume.get("capability_id") or low_volume.get("dimension"))
            prior_requests = [
                item for item in (snapshot.get("validatedDataRequests") or [])
                if item.get("hypothesis_id") == hypothesis_id
                and str(item.get("capability_id") or item.get("dimension")) == capability
            ]
            prior_days = max(
                [
                    int((item.get("period") or {}).get("days") or 0)
                    for item in prior_requests
                ] or [int((snapshot.get("analysisPeriod") or {}).get("days") or 30)]
            )
            extended_days = 60 if prior_days < 60 else 90 if prior_days < 90 else None
            period_source = snapshot.get("analysisPeriod") or {}
            date_to_raw = str(period_source.get("dateTo") or "")
            try:
                date_to = datetime.fromisoformat(date_to_raw).date()
            except ValueError:
                date_to = None
            if extended_days and date_to:
                classification = {
                    "campaign_name": hypothesis.get("campaign_name"),
                    "campaign_family": hypothesis.get("campaign_family") or "unknown",
                    "campaign_subtype": hypothesis.get("campaign_subtype") or "unknown",
                }
                extended_period = {
                    "dateFrom": (date_to - timedelta(days=extended_days - 1)).isoformat(),
                    "dateTo": date_to.isoformat(),
                    "days": extended_days,
                }
                candidate = _request(
                    str(hypothesis_id),
                    classification,
                    capability,
                    (
                        f"Статистики за {prior_days} дней недостаточно; повторить тот же read-only срез "
                        f"за {extended_days} дней, чтобы проверить гипотезу на большей выборке."
                    ),
                    extended_period,
                    priority="high",
                    required=True,
                )
                candidate.request_id = (
                    f"req_r{round_number + 1}_{len(candidates) + 1:03d}_{extended_days}d"
                )
                candidates.append(candidate)
                continue
        if not any(item.get("status") in AVAILABLE_AUDIT_DATA_STATUSES for item in related):
            continue
        already = {
            capability for owner, capability in existing_by_hypothesis if owner == hypothesis_id
        }
        next_capabilities = next_cascade_capabilities(
            subtype=str(hypothesis.get("campaign_subtype") or "unknown"),
            already_requested=already,
            remaining_budget=max_requests - request_count - len(candidates),
        )
        next_capabilities = [
            capability for capability in next_capabilities
            if _capability_matches_hypothesis(hypothesis, capability)
        ]
        if not next_capabilities:
            continue
        classification = {
            "campaign_name": hypothesis.get("campaign_name"),
            "campaign_family": hypothesis.get("campaign_family") or "unknown",
            "campaign_subtype": hypothesis.get("campaign_subtype") or "unknown",
        }
        capability = next_capabilities[0]
        candidate = _request(
            str(hypothesis_id), classification, capability,
            f"Следующий каскадный уровень: проверить {capability}; результат может подтвердить или отклонить гипотезу.",
            snapshot.get("analysisPeriod") or {}, priority="high", required=True,
        )
        candidate.request_id = f"req_r{round_number + 1}_{len(candidates) + 1:03d}"
        candidates.append(candidate)
    remaining = max(0, max_requests - request_count)
    accepted, rejected = validate_audit_data_requests(
        candidates[:remaining],
        max_requests=max_requests,
    )
    if rejected:
        snapshot["drilldownResults"] = (snapshot.get("drilldownResults") or []) + [item.model_dump(mode="json") for item in rejected]
    return accepted


def _planner_docs_lookup(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Planner-only local lookup. It never executes a Direct API request."""

    queries: list[str] = []
    hypotheses = {
        item.get("hypothesis_id"): item
        for item in (snapshot.get("investigationPlan") or {}).get("hypotheses", [])
    }
    for verification in _verification_registry(snapshot).values():
        if verification.get("status") not in {"unverified", "partially_confirmed", "rejected"}:
            continue
        hypothesis = hypotheses.get(verification.get("hypothesis_id")) or {}
        queries.append(" ".join([
            str(hypothesis.get("campaign_subtype") or ""),
            str(hypothesis.get("hypothesis") or ""),
            " ".join(str(item) for item in verification.get("remaining_data_needed") or []),
        ]).strip())
        if len(queries) >= 2:
            break
    trace: list[dict[str, Any]] = []
    knowledge: list[dict[str, Any]] = []
    seen_capabilities: set[str] = set()
    for query in queries[:2]:
        lookup = search_direct_api_docs(query)
        matches = lookup.get("matches") or []
        trace.append({
            "queryHash": hashlib.sha256(query.encode("utf-8")).hexdigest()[:16],
            "knowledgeVersion": lookup.get("knowledge_version"),
            "capabilityIds": [item.get("capability_id") for item in matches[:10]],
            "apiExecuted": False,
        })
        for match in matches[:4]:
            capability_id = str(match.get("capability_id") or "")
            if not capability_id or capability_id in seen_capabilities:
                continue
            seen_capabilities.add(capability_id)
            description = describe_direct_capability(capability_id)
            knowledge.append({
                "capability_id": capability_id,
                "purpose": description.get("purpose") or match.get("purpose"),
                "permitted_metrics": description.get("semantic_metrics") or [],
                "supported_campaign_families": description.get("campaign_families") or [],
                "supported_campaign_subtypes": description.get("campaign_subtypes") or [],
                "prerequisites": description.get("prerequisites") or [],
                "limitations": description.get("limitations") or [],
                "source_type": description.get("source_type"),
                "supported_now": bool(description.get("supported_now")),
                "requires_backend_implementation": not bool(description.get("supported_now")),
            })
    snapshot.setdefault("docsLookupTrace", []).append({
        "round": int((_audit_runtime(snapshot).get("investigationRound") or 1)),
        "lookups": trace,
    })
    return knowledge


def build_next_round_prompt(snapshot: dict[str, Any]) -> str:
    runtime = _audit_runtime(snapshot)
    completed = sorted({
        str(item.get("capability_id") or item.get("dimension"))
        for item in snapshot.get("drilldownResults") or []
        if item.get("status") in AVAILABLE_AUDIT_DATA_STATUSES
    })
    unavailable = sorted({
        str(item.get("capability_id") or item.get("dimension"))
        for item in snapshot.get("drilldownResults") or []
        if item.get("status") in {"unavailable", "unsupported", "insufficient_data", "failed", "not_applicable"}
    })
    compact_manifest = [
        {
            "id": item.get("id"),
            "supported_now": item.get("supported_now"),
            "campaign_families": item.get("supported_campaign_families"),
            "campaign_subtypes": item.get("supported_campaign_subtypes"),
        }
        for item in public_audit_tool_manifest()
    ]
    payload = {
        "observed_facts": snapshot.get("observedFacts") or [],
        "hypotheses": _active_hypotheses(snapshot),
        "verifications": _active_verifications(snapshot),
        "completed_capabilities": completed,
        "unavailable_capabilities": unavailable,
        "public_capability_manifest": compact_manifest,
        "remaining_request_budget": max(
            0,
            int(runtime.get("requestSafetyLimit") or MAX_DATA_REQUESTS_PER_AUDIT)
            - int(runtime.get("requestsCount") or 0),
        ),
        "remaining_rounds": max(
            0,
            int(runtime.get("maxDepthRounds") or MAX_INVESTIGATION_ROUNDS)
            - int(runtime.get("investigationRound") or 1),
        ),
        "local_documentation": _planner_docs_lookup(snapshot),
    }
    return """Plan the next read-only investigation round from verified evidence, not from a fixed sequence.
Return only strict JSON:
{"continue_investigation":true,"existing_hypothesis_requests":[],"new_hypotheses":[{"hypothesis_id":"hyp_006","hypothesis_type":"device_segment_gap","parent_hypothesis_id":"hyp_001","fact_ids":[],"supersedes_hypothesis_id":null,"campaign_name":"...","hypothesis":"...","rationale":"...","required_capabilities":["devices"],"prerequisite_rule_codes":[],"confirmation_rule_codes":["devices_cpa_segment_gap"],"rejection_rule_codes":["devices_cpa_segments_comparable"],"requests":[]}],"stop_reason":null}
Use only supported_now capabilities applicable to the campaign subtype. Existing follow-up capability must match hypothesis_type; another cause requires a child hypothesis. Every new hypothesis must reference a trusted parent_hypothesis_id or trusted fact_ids from the same campaign. Never invent rule codes or request write actions. If data is already sufficient, the sample is low, or no executable capability can change the conclusion, return continue_investigation=false with a stop_reason.
Context: """ + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _parse_next_round_plan(answer: str) -> tuple[AuditNextRoundPlan | None, bool, dict[str, Any]]:
    parsed, parsing = _parse_model_json(answer, AuditNextRoundPlan)
    if parsed is None:
        return None, False, parsing
    if parsed.continue_investigation and not (
        parsed.existing_hypothesis_requests or parsed.new_hypotheses
    ):
        return None, False, {**parsing, "errorCode": "empty_next_round_requests"}
    if not parsed.continue_investigation and not parsed.stop_reason:
        return None, False, {**parsing, "errorCode": "missing_stop_reason"}
    return parsed, True, parsing


def _next_round_requests_from_plan(
    snapshot: dict[str, Any], plan: AuditNextRoundPlan,
) -> tuple[list[AuditDataRequest], list[AuditDataRequestResult]]:
    if not plan.continue_investigation:
        return [], []
    runtime = _audit_runtime(snapshot)
    remaining = max(
        0,
        int(runtime.get("requestSafetyLimit") or MAX_DATA_REQUESTS_PER_AUDIT)
        - int(runtime.get("requestsCount") or 0),
    )
    hypotheses = _hypothesis_registry(snapshot)
    verifications = _verification_registry(snapshot)
    manifest = {str(item.get("id")): item for item in public_audit_tool_manifest()}
    facts_by_id = {
        str(item.get("fact_id")): item for item in (snapshot.get("observedFacts") or [])
        if item.get("fact_id")
    }
    already = {
        (item.get("hypothesis_id"), item.get("capability_id") or item.get("dimension"))
        for item in snapshot.get("validatedDataRequests") or []
    }
    candidates: list[AuditDataRequest] = []
    validation_rejections: list[AuditDataRequestResult] = []
    new_hypothesis_ids: set[str] = set()

    def reject_plan_item(
        hypothesis_id: str,
        capability_id: str,
        campaign_name: str,
        error_code: str,
        summary: str,
    ) -> None:
        validation_rejections.append(AuditDataRequestResult(
            request_id=f"rejected_{hypothesis_id}_{capability_id or 'binding'}",
            hypothesis_id=hypothesis_id,
            capability_id=capability_id or None,
            dimension=capability_id or "campaigns",
            status="unsupported",
            campaign_name=campaign_name,
            summary=summary,
            limitations=[summary],
            error_code=error_code,
        ))

    def append_request(item: Any, hypothesis: dict[str, Any]) -> None:
        if len(candidates) >= remaining:
            return
        capability = manifest.get(item.capability_id) or {}
        if not capability.get("supported_now"):
            return
        if (item.hypothesis_id, item.capability_id) in already:
            return
        if item.capability_id in set(hypothesis.get("forbidden_capabilities") or []):
            return
        if evidence_dimension_forbidden(
            snapshot,
            str(hypothesis.get("campaign_name") or ""),
            item.capability_id,
        ):
            reject_plan_item(
                item.hypothesis_id,
                item.capability_id,
                str(hypothesis.get("campaign_name") or ""),
                "forbidden_dimension_for_campaign_subtype",
                "Capability запрещён deterministic evidence policy для этого типа кампании.",
            )
            return
        if not _capability_matches_hypothesis(hypothesis, item.capability_id):
            reject_plan_item(
                item.hypothesis_id,
                item.capability_id,
                str(hypothesis.get("campaign_name") or ""),
                "hypothesis_type_capability_mismatch",
                "Capability проверяет другую причину; требуется отдельная дочерняя гипотеза.",
            )
            return
        if hypothesis.get("campaign_family") not in (capability.get("supported_campaign_families") or []):
            return
        if hypothesis.get("campaign_subtype") not in (capability.get("supported_campaign_subtypes") or []):
            return
        classification = {
            "campaign_name": hypothesis.get("campaign_name"),
            "campaign_family": hypothesis.get("campaign_family") or "unknown",
            "campaign_subtype": hypothesis.get("campaign_subtype") or "unknown",
        }
        request = _request(
            item.hypothesis_id,
            classification,
            item.capability_id,
            f"{item.reason} Expected information gain: {item.expected_information_gain}",
            snapshot.get("analysisPeriod") or {},
            priority="high",
            required=item.required_for_conclusion,
        )
        request.request_id = f"req_r{int(runtime.get('investigationRound') or 1) + 1}_{len(candidates) + 1:03d}"
        request.expected_information_gain = item.expected_information_gain
        candidates.append(request)

    for new_hypothesis in plan.new_hypotheses:
        if len(candidates) >= remaining or new_hypothesis.hypothesis_id in hypotheses:
            continue
        parent = hypotheses.get(new_hypothesis.parent_hypothesis_id) if new_hypothesis.parent_hypothesis_id else None
        if new_hypothesis.parent_hypothesis_id and not parent:
            reject_plan_item(
                new_hypothesis.hypothesis_id, "", new_hypothesis.campaign_name,
                "unknown_parent_hypothesis", "Родительская гипотеза отсутствует в trusted registry.",
            )
            continue
        if parent and parent.get("campaign_name") != new_hypothesis.campaign_name:
            reject_plan_item(
                new_hypothesis.hypothesis_id, "", new_hypothesis.campaign_name,
                "parent_campaign_mismatch", "Родительская гипотеза относится к другой кампании.",
            )
            continue
        bound_fact_ids = list(new_hypothesis.fact_ids or (parent or {}).get("fact_ids") or [])
        bound_facts = [facts_by_id.get(str(fact_id)) for fact_id in bound_fact_ids]
        if (
            (not parent and not bound_fact_ids)
            or any(fact is None for fact in bound_facts)
            or any(str(fact.get("campaign_name")) != new_hypothesis.campaign_name for fact in bound_facts if fact)
        ):
            reject_plan_item(
                new_hypothesis.hypothesis_id, "", new_hypothesis.campaign_name,
                "untrusted_fact_binding", "Новая гипотеза не связана с trusted fact той же кампании.",
            )
            continue
        if new_hypothesis.hypothesis_type not in {"tracking_issue", "campaign_metadata_issue"} and any(
            not bool(fact.get("sufficient_data")) for fact in bound_facts if fact
        ):
            reject_plan_item(
                new_hypothesis.hypothesis_id, "", new_hypothesis.campaign_name,
                "insufficient_fact_binding", "Trusted fact не имеет достаточного объёма для причинной гипотезы.",
            )
            continue
        classification = parent or next(
            (
                item for item in (snapshot.get("campaignClassifications") or [])
                if item.get("campaign_name") == new_hypothesis.campaign_name
            ),
            None,
        )
        if not classification:
            continue
        trusted_requests = [
            AuditDataRequest(
                request_id=f"contract_{new_hypothesis.hypothesis_id}_{index}",
                hypothesis_id=new_hypothesis.hypothesis_id,
                campaign_name=new_hypothesis.campaign_name,
                campaign_family=classification.get("campaign_family") or "unknown",
                campaign_subtype=classification.get("campaign_subtype") or "unknown",
                dimension=capability,
                capability_id=capability,
                reason=new_hypothesis.rationale,
            )
            for index, capability in enumerate(new_hypothesis.required_capabilities)
            if capability in HYPOTHESIS_EVIDENCE_POLICY[new_hypothesis.hypothesis_type]["allowed_capabilities"]
        ]
        expected_prerequisites, expected_confirmations, expected_rejections = _rule_codes_for_requests(trusted_requests)
        confirmation_codes = [
            code for code in new_hypothesis.confirmation_rule_codes if code in expected_confirmations
        ] or expected_confirmations
        hypothesis_payload = {
            "hypothesis_id": new_hypothesis.hypothesis_id,
            "hypothesis_type": new_hypothesis.hypothesis_type,
            "parent_hypothesis_id": new_hypothesis.parent_hypothesis_id,
            "supersedes_hypothesis_id": new_hypothesis.supersedes_hypothesis_id,
            "campaign_name": new_hypothesis.campaign_name,
            "campaign_family": classification.get("campaign_family") or "unknown",
            "campaign_subtype": classification.get("campaign_subtype") or "unknown",
            "observed_fact": new_hypothesis.rationale,
            "hypothesis": new_hypothesis.hypothesis,
            "current_status": "unverified",
            "fact_ids": bound_fact_ids,
            "rationale": new_hypothesis.rationale,
            "required_capabilities": new_hypothesis.required_capabilities,
            "optional_capabilities": [],
            "forbidden_capabilities": list(classification.get("forbidden_capabilities") or []),
            "confirmation_rules": [],
            "rejection_rules": [],
            "prerequisite_rule_codes": [
                code for code in new_hypothesis.prerequisite_rule_codes if code in expected_prerequisites
            ] or expected_prerequisites,
            "confirmation_rule_codes": confirmation_codes,
            "rejection_rule_codes": [
                code for code in new_hypothesis.rejection_rule_codes if code in expected_rejections
            ] or expected_rejections,
            "stop_conditions": [],
            "data_requests": [],
        }
        hypotheses[new_hypothesis.hypothesis_id] = hypothesis_payload
        new_hypothesis_ids.add(new_hypothesis.hypothesis_id)
        request_items = list(new_hypothesis.requests)
        if not request_items:
            request_items = [
                AuditNextRoundRequest(
                    hypothesis_id=new_hypothesis.hypothesis_id,
                    capability_id=capability_id,
                    reason=new_hypothesis.rationale,
                    expected_information_gain="Test the new independent causal hypothesis.",
                    required_for_conclusion=True,
                )
                for capability_id in new_hypothesis.required_capabilities
            ]
        for item in request_items:
            if item.hypothesis_id != new_hypothesis.hypothesis_id:
                continue
            append_request(item, hypothesis_payload)

    for item in plan.existing_hypothesis_requests[:remaining]:
        hypothesis = hypotheses.get(item.hypothesis_id)
        if not hypothesis or (verifications.get(item.hypothesis_id) or {}).get("status") == "rejected":
            continue
        append_request(item, hypothesis)

    accepted, rejected = validate_audit_data_requests(
        candidates,
        max_requests=max(1, remaining),
    )
    rejected = validation_rejections + rejected
    active_ids = list(dict.fromkeys(item.hypothesis_id for item in accepted))[:5]
    active_set = set(active_ids)
    accepted = [item for item in accepted if item.hypothesis_id in active_set]
    for hypothesis_id in active_ids:
        _extend_hypothesis_contract(
            hypotheses[hypothesis_id],
            [item for item in accepted if item.hypothesis_id == hypothesis_id],
        )
    for hypothesis_id in new_hypothesis_ids - set(active_ids):
        hypotheses[hypothesis_id]["current_status"] = "unverified"
        hypotheses[hypothesis_id]["remaining_data_needed"] = list(
            hypotheses[hypothesis_id].get("required_capabilities") or []
        )
    snapshot["activeHypothesisIds"] = active_ids
    _sync_active_investigation_plan(snapshot)
    return accepted, rejected


def _apply_next_round_requests(snapshot: dict[str, Any], requests: list[AuditDataRequest]) -> None:
    runtime = _audit_runtime(snapshot)
    if snapshot.get("investigationRounds"):
        previous_round = snapshot["investigationRounds"][-1]
        previous_round["completed_at"] = _now().isoformat()
        previous_round["stop_reason"] = "next_level_requested"
    runtime.pop("stopReason", None)
    runtime["schedulerPhase"] = "depth"
    runtime["investigationRound"] = int(runtime.get("investigationRound") or 1) + 1
    runtime["requestsCount"] = int(runtime.get("requestsCount") or 0) + len(requests)
    snapshot["validatedDataRequests"] = (snapshot.get("validatedDataRequests") or []) + [
        item.model_dump(mode="json") for item in requests
    ]
    snapshot["pendingDataRequests"] = [item.model_dump(mode="json") for item in requests]
    snapshot["processingDataRequests"] = []
    names = {request.campaign_name for request in requests}
    round_facts = [
        item for item in (snapshot.get("observedFacts") or []) if item.get("campaign_name") in names
    ]
    hypothesis_ids = {request.hypothesis_id for request in requests}
    snapshot["activeHypothesisIds"] = list(dict.fromkeys(request.hypothesis_id for request in requests))[:5]
    registry = _hypothesis_registry(snapshot)
    canonical_hypotheses = [registry[item] for item in snapshot["activeHypothesisIds"] if item in registry]
    for hypothesis in canonical_hypotheses:
        if hypothesis.get("hypothesis_id") not in hypothesis_ids:
            continue
        if hypothesis.get("current_status") != "rejected" and hypothesis.get("status") != "rejected":
            hypothesis["current_status"] = "unverified"
        existing_requests = hypothesis.setdefault("data_requests", [])
        existing_ids = {item.get("request_id") for item in existing_requests}
        existing_requests.extend(
            request.model_dump(mode="json")
            for request in requests
            if request.hypothesis_id == hypothesis.get("hypothesis_id")
            and request.request_id not in existing_ids
        )
        _extend_hypothesis_contract(
            hypothesis,
            [request for request in requests if request.hypothesis_id == hypothesis.get("hypothesis_id")],
        )
    prior_hypotheses = list(canonical_hypotheses) + [
        item
        for round_item in (snapshot.get("investigationRounds") or [])
        for item in (round_item.get("hypotheses") or [])
        if item.get("hypothesis_id") in hypothesis_ids
    ]
    round_hypotheses = [
        {**item, "status": "collecting_data", "investigation_round": runtime["investigationRound"]}
        for item in {item.get("hypothesis_id"): item for item in prior_hypotheses}.values()
    ]
    snapshot.setdefault("investigationRounds", []).append({
        "round_number": runtime["investigationRound"],
        "observed_facts": round_facts,
        "hypotheses": round_hypotheses,
        "planned_requests": [item.model_dump(mode="json") for item in requests],
        "completed_requests": [],
        "pending_requests": [item.model_dump(mode="json") for item in requests],
        "processing_requests": [],
        "failed_requests": [],
        "verification_results": [],
        "started_at": _now().isoformat(),
        "completed_at": None,
        "stop_reason": None,
    })
    _sync_active_investigation_plan(snapshot)


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
    dynamics_campaigns = dynamics.get("campaignDynamics") if isinstance(dynamics.get("campaignDynamics"), dict) else {}
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
            "worstCampaigns": [_dynamics_campaign_snapshot(item) for item in (dynamics_campaigns.get("worstCampaigns") or [])[:5] if isinstance(item, dict)],
            "bestCampaigns": [_dynamics_campaign_snapshot(item) for item in (dynamics_campaigns.get("bestCampaigns") or [])[:5] if isinstance(item, dict)],
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
            "Аудит использует только доступные read-only данные и не применяет изменения.",
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


def _fresh_initial_audit_context(
    db: Session,
    job: AiAuditJob,
) -> dict[str, Any]:
    """Build the smallest honest context required before live Direct collection.

    A fresh staged audit must establish live campaign coverage before interpreting
    historical aggregates.  The generic recommendation context deliberately
    performs richer summary, plan, and dynamics queries, which made the first
    audit transition depend on data that the scheduler is about to refresh.
    """
    client = db.get(ClientAccount, job.client_id)
    date_to = (_now() - timedelta(days=1)).date()
    requested_days = {
        "last_7_days": 7,
        "last_14_days": 14,
        "last_30_days": 30,
    }.get(job.requested_period, 30)
    date_from = date_to - timedelta(days=requested_days - 1)
    return {
        "client": {
            "id": job.client_id,
            "name": client.name if client else None,
            "target_cpa": client.target_cpa if client else None,
            "last_synced_at": client.last_synced_at.isoformat() if client and client.last_synced_at else None,
        },
        "business_context": {"status": "unavailable", "fields": {}},
        "goals": {
            "selected_goal_ids": [],
            "has_goal_data": False,
            "source_message": "Goal evidence is collected during the read-only audit.",
        },
        "summary": {
            "totals": {},
            "campaigns": [],
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        },
        "campaigns": [],
        "search_query_insights": {"totalQueries": 0, "insights": []},
        "campaign_dynamics_analysis": {
            "dataQuality": {"rows": 0},
            "campaignDynamics": {"worstCampaigns": [], "bestCampaigns": []},
            "missingData": ["Historical context is deferred until fresh Direct evidence is collected."],
        },
        "yandex_direct_audit": {},
        "sync_diagnostics": {},
        "optimization_plan": [],
        "warnings": ["Fresh audit starts from live read-only Direct data; saved history is not used as evidence."],
    }


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
        "campaign_insights": [],
        "insufficient_data_campaigns": [{
            "campaign_name": "Название кампании",
            "reason": "Почему данных недостаточно",
            "recommendation": "Безопасный следующий шаг",
            "next_data_needed": [],
        }],
        "tracking_and_goals": {},
        "drilldown_summary": {"analyzed_levels": [], "not_analyzed_levels": [], "next_data_needed": []},
        "action_plan": [{"priority": 1, "hypothesis_id": "hyp_001 или null", "action": "...", "scope": "...", "reason": "...", "mode": "manual_review|dry_run", "requires_human_approval": True}],
        "prohibited_actions": [],
        "limitations": [],
        "conclusion": "Итоговый вывод",
    }


def _audit_source_description(snapshot: dict[str, Any]) -> str:
    source = str(
        (snapshot.get("analysisPeriod") or {}).get("source")
        or (snapshot.get("metadata") or {}).get("campaignEvidenceSource")
        or "unavailable"
    )
    return {
        "yandex_direct_live_report": "fresh report Яндекс.Директа",
        "yandex_direct_live_service": "fresh service response Яндекс.Директа",
        "yandex_direct_cached_live": "кешированный live-отчёт Яндекс.Директа",
        "directpilot_saved_stats": "сохранённая read-only статистика DirectPilot",
        "mixed_live_and_saved": "смешанные live и сохранённые read-only данные",
        "unavailable": "недоступные read-only данные",
    }.get(source, f"read-only источник {source}")


_FINAL_METRIC_KEYS = {
    "impressions", "clicks", "cost", "ctr", "avgCpc", "avg_cpc", "cpc",
    "goalConversions", "goal_conversions", "goalCpa", "goal_cpa",
    "conversionRate", "conversion_rate", "revenue", "roi", "campaigns",
}
_FINAL_PRIVATE_TEXT_PATTERN = re.compile(
    r'''(?ix)["']?\b(?:
        authorization|access_token|refresh_token|oauth_token|request_hash|
        client_id|organization_id|job_id|campaignid|adgroupid|criterionid
    )\b["']?\s*[:=]\s*["']?[^\s,"';}\]]+'''
)


def _safe_final_text(value: Any, *, max_chars: int = 500) -> str:
    text = str(value or "").strip()
    return _FINAL_PRIVATE_TEXT_PATTERN.sub("[internal value removed]", text)[:max_chars]


def _bounded_strings(values: Any, limit: int, *, max_chars: int = 500) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = _safe_final_text(value, max_chars=max_chars)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _safe_metric_values(values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    return {
        str(key): value
        for key, value in values.items()
        if str(key) in _FINAL_METRIC_KEYS and isinstance(value, (int, float, str, bool, type(None)))
    }


def _final_campaign_type(item: dict[str, Any]) -> str:
    family = str(item.get("campaign_family") or item.get("campaignFamily") or "unknown")
    subtype = str(item.get("campaign_subtype") or item.get("campaignSubtype") or "unknown")
    if "retarget" in subtype:
        return "retargeting"
    if family == "search":
        return "search"
    if family == "yan":
        return "yan"
    if "master" in subtype:
        return "master_campaign"
    return "unknown"


def _final_fact_records(snapshot: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    facts_by_id: dict[str, dict[str, Any]] = {}
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(snapshot.get("observedFacts") or []):
        if not isinstance(raw, dict):
            continue
        fact_id = str(raw.get("fact_id") or raw.get("factId") or f"fact_{index + 1:03d}")
        evidence = _bounded_strings(raw.get("evidence"), 3, max_chars=350)
        item = {
            "campaignName": str(raw.get("campaign_name") or raw.get("campaignName") or "Аккаунт")[:300],
            "metric": str(raw.get("metric") or "observation")[:100],
            "summary": " ".join(evidence)[:800] or "Факт зафиксирован backend-правилом.",
            "sufficientData": bool(raw.get("sufficient_data") if "sufficient_data" in raw else raw.get("sufficientData")),
        }
        facts_by_id[fact_id] = item
        key = (item["campaignName"], item["metric"], item["summary"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return facts_by_id, unique


_CAMPAIGN_SIGNAL_PRIORITY = {
    "spend_without_goal_conversions": 0,
    "cpa_above_target": 1,
    "goal_conversions_drop": 2,
    "budget_spike": 3,
    "low_ctr": 4,
    "high_cpc_traffic_proxy": 4,
    "traffic_metrics_available": 5,
    "conversion_data_unknown": 5,
    "low_data": 6,
    "good_campaign": 7,
    "traffic_metrics_reviewed": 8,
    "stable_efficiency": 8,
    "campaign_health": 9,
}


def _campaign_insight_copy(
    *,
    metric: str,
    subtype: str,
    verification_status: str,
) -> tuple[str, str, str]:
    is_yan = subtype in {"yan_prospecting", "yan_retargeting"}
    if metric == "spend_without_goal_conversions":
        problem = "Есть расход без конверсий по выбранным целям."
        recommendation = (
            "Проверить площадки и аудитории с расходом без конверсий; после подтверждения причины "
            "подготовить список исключений для ручного согласования."
            if is_yan else
            "Проверить поисковые запросы, группы и ключевые фразы с расходом без конверсий; "
            "после подтверждения причины подготовить минус-фразы или корректировку структуры для согласования."
        )
        effect = "Сократить непроизводительный расход без автоматического изменения кампании."
    elif metric == "cpa_above_target":
        problem = "CPA выше целевого значения."
        recommendation = (
            "Определить площадки, аудитории и сегменты, формирующие отклонение CPA; подтверждённые "
            "исключения или корректировки вынести на ручное согласование."
            if is_yan else
            "Определить запросы, группы, ключевые фразы, устройства или регионы, формирующие отклонение "
            "CPA; подтверждённые изменения вынести на ручное согласование."
        )
        effect = "Снизить CPA в направлении целевого значения при сохранении контроля объёма конверсий."
    elif metric == "goal_conversions_drop":
        problem = "Конверсии снизились относительно предыдущего периода."
        recommendation = "Проверить изменение трафика, стратегии, сегментов и трекинга между периодами до корректировки кампании."
        effect = "Локализовать причину снижения и избежать изменения параметров, которые не связаны с проблемой."
    elif metric == "budget_spike":
        problem = "Расход резко вырос относительно предыдущего периода."
        recommendation = "Проверить источники роста расхода и их конверсионность; изменения бюджета подготовить только после подтверждения причины."
        effect = "Вернуть расход под контроль без преждевременного ограничения эффективного трафика."
    elif metric == "low_ctr":
        problem = "CTR ниже рабочего ориентира."
        recommendation = "Проверить запросы, объявления и соответствие посадочной страницы намерению пользователя; варианты изменений подготовить для ручного теста."
        effect = "Повысить релевантность трафика и объявлений."
    elif metric in {"conversion_data_unknown", "low_data"}:
        problem = (
            "Конверсионная метрика не получена или некорректна; это неизвестное значение, а не ноль."
            if metric == "conversion_data_unknown"
            else "Статистики недостаточно для надёжного вывода."
        )
        recommendation = (
            "Проверить выбранные цели и передачу конверсий; одновременно продолжить независимый анализ качества трафика по доступным срезам без выводов о CPA и продажах."
            if metric == "conversion_data_unknown"
            else "Расширить период анализа до 60 дней, а при сохранении малого объёма — до 90 дней."
        )
        effect = "Получить достаточную выборку для проверяемого вывода без изменения настроек кампании."
    elif metric in {"good_campaign", "stable_efficiency"}:
        problem = "Кампания показывает стабильную эффективность в доступном периоде."
        recommendation = "Рассмотреть контролируемый тест масштабирования с отдельным лимитом и последующей проверкой CPA."
        effect = "Проверить потенциал роста без потери целевой эффективности."
    else:
        problem = "Сигнал по кампании зафиксирован, но причина не установлена."
        recommendation = "Проверить доступные срезы и подтвердить причинную гипотезу до любых изменений."
        effect = "Перевести наблюдение в проверяемое решение."
    if verification_status == "rejected":
        recommendation = "Не выполнять действие по опровергнутой причинной гипотезе; проверить другую причину отдельной гипотезой."
    return problem, recommendation, effect


_FACTOR_CAPABILITY_LABELS = {
    "campaign_performance": "кампания",
    "search_queries": "поисковый запрос",
    "ad_group_performance": "группа объявлений",
    "keyword_performance": "ключевая фраза",
    "placements": "площадка",
    "devices": "устройство",
    "geo": "регион",
}

_CAMPAIGN_SUBTYPE_LABELS = {
    "search": "Поиск",
    "brand_search": "брендовый Поиск",
    "yan_prospecting": "привлечение новой аудитории в РСЯ",
    "yan_retargeting": "ретаргетинг в РСЯ",
}


def _campaign_peer_traffic_factor(
    campaign_name: str,
    row: dict[str, Any],
    classification: dict[str, Any],
    *,
    rows: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    period_days: int = 0,
) -> dict[str, Any] | None:
    """Compare traffic metrics only with a stable peer cohort, never with conversions."""

    family = str(
        classification.get("campaign_family")
        or classification.get("campaignFamily")
        or "unknown"
    )
    subtype = str(
        classification.get("campaign_subtype")
        or classification.get("campaignSubtype")
        or "unknown"
    )
    if family == "unknown" or subtype == "unknown":
        return None

    peer_rows: list[dict[str, Any]] = []
    for peer_name, peer_row in rows.items():
        if peer_name == campaign_name:
            continue
        peer_classification = classifications.get(peer_name) or {}
        peer_subtype = str(
            peer_classification.get("campaign_subtype")
            or peer_classification.get("campaignSubtype")
            or "unknown"
        )
        if peer_subtype != subtype:
            continue
        clicks = int(_number(peer_row.get("clicks")) or 0)
        impressions = int(_number(peer_row.get("impressions")) or 0)
        cost = float(_number(peer_row.get("cost")) or 0)
        if clicks > 0 and impressions > 0 and cost > 0:
            peer_rows.append({
                "clicks": clicks,
                "impressions": impressions,
                "cost": cost,
            })
    if len(peer_rows) < 2:
        return None

    clicks = int(_number(row.get("clicks")) or 0)
    impressions = int(_number(row.get("impressions")) or 0)
    cost = float(_number(row.get("cost")) or 0)
    if clicks < 20 or impressions <= 0 or cost <= 0:
        return None

    peer_clicks = sum(item["clicks"] for item in peer_rows)
    peer_impressions = sum(item["impressions"] for item in peer_rows)
    peer_cost = sum(item["cost"] for item in peer_rows)
    if peer_clicks < 40 or peer_impressions < 2000 or peer_cost <= 0:
        return None

    cpc = cost / clicks
    ctr = clicks / impressions * 100
    baseline_cpc = peer_cost / peer_clicks
    baseline_ctr = peer_clicks / peer_impressions * 100
    cohort_cost = peer_cost + cost
    common = {
        "capability_id": "campaign_performance",
        "segment": campaign_name,
        "cost": round(cost, 2),
        "cost_share_pct": round(cost / cohort_cost * 100, 2) if cohort_cost else 0,
        "clicks": clicks,
        "impressions": impressions,
        "peer_campaigns": len(peer_rows),
        "benchmark_scope": subtype,
        "material": False,
        "backend_confirmed": False,
        "period_days": int(period_days or 0),
    }
    candidates: list[dict[str, Any]] = []
    if baseline_cpc > 0 and cpc >= baseline_cpc * 1.5:
        candidates.append({
            **common,
            "metric": "cpc",
            "factor_type": "traffic_proxy_cpc",
            "value": round(cpc, 2),
            "benchmark": round(baseline_cpc, 2),
            "deviation_ratio": round(cpc / baseline_cpc, 3),
        })
    if baseline_ctr > 0 and impressions >= 1000 and ctr <= baseline_ctr * 0.65:
        candidates.append({
            **common,
            "metric": "ctr",
            "factor_type": "traffic_proxy_ctr",
            "value": round(ctr, 2),
            "benchmark": round(baseline_ctr, 2),
            "deviation_ratio": round(baseline_ctr / ctr, 3) if ctr > 0 else None,
        })
    if not candidates:
        return {
            **common,
            "metric": "traffic",
            "factor_type": "traffic_proxy_within_peer_range",
            "cpc": round(cpc, 2),
            "ctr": round(ctr, 2),
            "benchmark_cpc": round(baseline_cpc, 2),
            "benchmark_ctr": round(baseline_ctr, 2),
            "deviation_ratio": 1.0,
        }
    return max(
        candidates,
        key=lambda item: (
            float(item.get("deviation_ratio") or 0),
            float(item.get("cost") or 0),
        ),
    )


def _campaign_primary_factor(
    summaries: list[dict[str, Any]],
    *,
    allow_traffic_proxy: bool = False,
    allow_conversion_factors: bool = True,
) -> dict[str, Any] | None:
    candidates: list[tuple[int, int, float, dict[str, Any]]] = []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        capability_id = str(
            summary.get("capability_id")
            or summary.get("capabilityId")
            or summary.get("dimension")
            or ""
        )
        diagnostics = summary.get("diagnostics")
        backend_confirmed = any(
            isinstance(rule, dict) and rule.get("passed") is True
            for rule in (summary.get("confirmation_rules") or [])
        )
        period_days = int((summary.get("period") or {}).get("days") or 0)
        if (
            allow_conversion_factors
            and isinstance(diagnostics, dict)
            and diagnostics.get("kind") == "performance_contributors"
        ):
            waste = diagnostics.get("top_waste") or []
            high_cpa = diagnostics.get("top_high_cpa") or []
            if waste and isinstance(waste[0], dict):
                factor = {
                    **waste[0],
                    "hypothesis_id": summary.get("hypothesis_id") or summary.get("hypothesisId"),
                    "capability_id": capability_id,
                    "factor_type": "waste_without_conversions",
                    "aggregate_waste_cost": diagnostics.get("waste_cost"),
                    "aggregate_waste_clicks": diagnostics.get("waste_clicks"),
                    "aggregate_waste_share_pct": diagnostics.get("waste_share_pct"),
                    "material": bool(diagnostics.get("material_waste")),
                    "backend_confirmed": backend_confirmed,
                    "period_days": period_days,
                }
                candidates.append((
                    0 if factor["material"] else 2,
                    -period_days,
                    -float(factor.get("cost") or 0),
                    factor,
                ))
            if high_cpa and isinstance(high_cpa[0], dict):
                factor = {
                    **high_cpa[0],
                    "hypothesis_id": summary.get("hypothesis_id") or summary.get("hypothesisId"),
                    "capability_id": capability_id,
                    "factor_type": "high_cpa_segment",
                    "material": True,
                    "backend_confirmed": False,
                    "period_days": period_days,
                }
                candidates.append((1, -period_days, -float(factor.get("cost") or 0), factor))
        elif (
            allow_conversion_factors
            and isinstance(diagnostics, dict)
            and diagnostics.get("kind") == "segment_comparison"
        ):
            worst = diagnostics.get("worst_segment")
            best = diagnostics.get("best_segment")
            ratio = float(diagnostics.get("cpa_ratio") or 0)
            if isinstance(worst, dict) and isinstance(best, dict) and ratio > 1:
                factor = {
                    **worst,
                    "hypothesis_id": summary.get("hypothesis_id") or summary.get("hypothesisId"),
                    "capability_id": capability_id,
                    "factor_type": "segment_cpa_gap",
                    "cpa_ratio": ratio,
                    "best_segment": best,
                    "material": ratio >= 1.5,
                    "backend_confirmed": backend_confirmed,
                    "period_days": period_days,
                }
                candidates.append((
                    0 if factor["material"] else 2,
                    -period_days,
                    -float(factor.get("cost") or 0),
                    factor,
                ))
        traffic_diagnostics = summary.get("traffic_diagnostics")
        if allow_traffic_proxy and isinstance(traffic_diagnostics, dict):
            for traffic_candidate in (traffic_diagnostics.get("candidates") or [])[:3]:
                if not isinstance(traffic_candidate, dict):
                    continue
                factor = {
                    **traffic_candidate,
                    "hypothesis_id": summary.get("hypothesis_id") or summary.get("hypothesisId"),
                    "capability_id": capability_id,
                    "factor_type": f"traffic_proxy_{traffic_candidate.get('metric') or 'signal'}",
                    "material": False,
                    "backend_confirmed": False,
                    "period_days": period_days,
                }
                candidates.append((
                    3,
                    -period_days,
                    -float(factor.get("cost") or 0),
                    factor,
                ))
    return sorted(candidates, key=lambda item: (item[0], item[1], item[2]))[0][3] if candidates else None


def _factor_evidence(factor: dict[str, Any]) -> list[str]:
    capability_id = str(factor.get("capability_id") or "")
    label = _FACTOR_CAPABILITY_LABELS.get(capability_id, "сегмент")
    segment = str(factor.get("segment") or "без названия")
    if factor.get("factor_type") == "traffic_proxy_within_peer_range":
        benchmark_scope = str(factor.get("benchmark_scope") or "peer cohort")
        benchmark_scope_label = _CAMPAIGN_SUBTYPE_LABELS.get(
            benchmark_scope,
            "сопоставимая группа кампаний",
        )
        return [
            (
                f"{label.capitalize()} «{segment}»: CTR {float(factor.get('ctr') or 0):.2f}% "
                f"против ориентира {float(factor.get('benchmark_ctr') or 0):.2f}%; "
                f"CPC {float(factor.get('cpc') or 0):.2f} ₽ против ориентира "
                f"{float(factor.get('benchmark_cpc') or 0):.2f} ₽."
            ),
            (
                f"Ориентир рассчитан по {int(factor.get('peer_campaigns') or 0)} "
                f"сопоставимым кампаниям типа «{benchmark_scope_label}»; "
                "материального отклонения трафика по заданным порогам не выявлено."
            ),
            "Конверсии в traffic-proxy сравнении не использовались.",
        ]
    if str(factor.get("factor_type") or "").startswith("traffic_proxy_"):
        metric = str(factor.get("metric") or "")
        metric_label = "CPC" if metric == "cpc" else "CTR"
        evidence = [
            (
                f"{label.capitalize()} «{segment}»: {metric_label} {float(factor.get('value') or 0):.2f} "
                f"против ориентира среза {float(factor.get('benchmark') or 0):.2f}; "
                f"расход {float(factor.get('cost') or 0):.2f} ₽, клики {int(factor.get('clicks') or 0)}, "
                f"доля расхода {float(factor.get('cost_share_pct') or 0):.1f}%."
            ),
            "Это traffic-proxy сигнал: он не подтверждает влияние на конверсии или продажи.",
        ]
        if int(factor.get("peer_campaigns") or 0) >= 2:
            benchmark_scope = str(factor.get("benchmark_scope") or "peer cohort")
            benchmark_scope_label = _CAMPAIGN_SUBTYPE_LABELS.get(
                benchmark_scope,
                "сопоставимая группа кампаний",
            )
            evidence.insert(1, (
                f"Ориентир рассчитан по {int(factor.get('peer_campaigns') or 0)} "
                f"сопоставимым кампаниям типа «{benchmark_scope_label}»; "
                "конверсии в сравнении не использовались."
            ))
        return evidence
    evidence = [
        (
            f"{label.capitalize()} «{segment}»: расход {float(factor.get('cost') or 0):.2f} ₽, "
            f"клики {int(factor.get('clicks') or 0)}, "
            f"конверсии {float(factor.get('conversions') or 0):.2f}"
            + (
                f", CPA {float(factor.get('cpa')):.2f} ₽"
                if factor.get("cpa") is not None else ""
            )
            + f", доля расхода {float(factor.get('cost_share_pct') or 0):.1f}%."
        )
    ]
    if factor.get("factor_type") == "waste_without_conversions":
        evidence.append(
            f"Совокупно сегменты без конверсий: {float(factor.get('aggregate_waste_cost') or 0):.2f} ₽, "
            f"{int(factor.get('aggregate_waste_clicks') or 0)} кликов, "
            f"{float(factor.get('aggregate_waste_share_pct') or 0):.1f}% расхода среза."
        )
    elif factor.get("factor_type") == "segment_cpa_gap":
        best = factor.get("best_segment") or {}
        evidence.append(
            f"CPA хуже лучшего сопоставимого сегмента «{best.get('segment') or 'без названия'}» "
            f"в {float(factor.get('cpa_ratio') or 0):.2f} раза "
            f"({float(factor.get('cpa') or 0):.2f} ₽ против {float(best.get('cpa') or 0):.2f} ₽)."
        )
    return evidence


def _factor_copy(
    factor: dict[str, Any],
    *,
    base_problem: str,
    base_recommendation: str,
    verification_status: str,
) -> tuple[str, str]:
    capability_id = str(factor.get("capability_id") or "")
    label = _FACTOR_CAPABILITY_LABELS.get(capability_id, "сегмент")
    segment = str(factor.get("segment") or "без названия")
    confirmed = verification_status == "confirmed"
    low_sample = factor.get("conversion_state") == "low_sample"
    if factor.get("factor_type") == "traffic_proxy_within_peer_range":
        return (
            (
                "Конверсионная выборка мала, но CTR и CPC проверены: "
                if low_sample
                else "Конверсионная метрика недоступна, но CTR и CPC проверены: "
            )
            +
            "материального отклонения от сопоставимых кампаний не выявлено.",
            "Не ограничиваться проверкой целей: продолжить разбор уже собранных срезов "
            "по запросам, группам, устройствам, регионам или площадкам; "
            + (
                "параллельно расширить период до 60 дней и при необходимости до 90 дней."
                if low_sample
                else "восстановление конверсионной метрики выполнять параллельно."
            ),
        )
    if str(factor.get("factor_type") or "").startswith("traffic_proxy_"):
        metric_label = "CPC" if factor.get("metric") == "cpc" else "CTR"
        problem = (
            f"Измеримый traffic-proxy кандидат: {label} «{segment}» отклоняется по "
            f"{metric_label} от ориентира доступного среза. "
            + (
                "Конверсионная выборка мала, поэтому влияние на продажи пока не подтверждено."
                if low_sample
                else "Конверсионная метрика недоступна, поэтому влияние на продажи не подтверждено."
            )
        )
        recommendation = (
            f"Проверить релевантность и структуру трафика для объекта: {label} «{segment}», "
            + (
                "не связывая отклонение с продажами до расширения периода до 60–90 дней; "
                if low_sample
                else "не связывая отклонение с продажами до восстановления конверсионной метрики; "
            )
            +
            "любую корректировку подготовить только как черновик для ручного согласования."
        )
        return problem, recommendation
    status_prefix = "Подтверждённый измеримый фактор" if confirmed else "Наиболее сильный измеримый фактор"
    problem = f"{base_problem} {status_prefix}: {label} «{segment}»."
    period_days = int(factor.get("period_days") or 0)
    if confirmed:
        review_prefix = ""
    elif period_days >= 90:
        review_prefix = (
            "Фактор проверен за 90 дней, но строгие пороги подтверждения не пройдены; "
            "не менять настройки автоматически и дополнительно "
        )
    elif period_days >= 60:
        review_prefix = (
            "Фактор проверен за 60 дней, но пока не подтверждён; "
            "автоматически расширить проверку до 90 дней, затем "
        )
    else:
        review_prefix = (
            "Фактор проверен за 30 дней; автоматически повторить срез за 60 дней "
            "и при необходимости за 90 дней, затем "
        )
    if capability_id == "search_queries":
        recommendation = (
            f"{review_prefix}проверить релевантность запроса «{segment}» объявлению и посадочной странице; "
            "при нерелевантности подготовить минус-фразу для ручного согласования."
        )
    elif capability_id == "ad_group_performance":
        recommendation = (
            f"{review_prefix}разобрать структуру группы «{segment}», запросы и объявления внутри неё; "
            "подготовить разделение или корректировку структуры для ручного согласования."
        )
    elif capability_id == "keyword_performance":
        recommendation = (
            f"{review_prefix}проверить соответствие ключевой фразы «{segment}» фактическим запросам; "
            "подготовить уточнение оператора или минус-фразы для ручного согласования."
        )
    elif capability_id == "placements":
        recommendation = (
            f"{review_prefix}проверить качество трафика площадки «{segment}»; "
            "при подтверждении подготовить её исключение для ручного согласования."
        )
    elif capability_id == "devices":
        recommendation = (
            f"{review_prefix}проверить конверсионный путь и посадочную страницу для устройства «{segment}»; "
            "корректировку по устройствам подготовить только как черновик для согласования."
        )
    elif capability_id == "geo":
        recommendation = (
            f"{review_prefix}проверить спрос, условия показа и обработку лидов в регионе «{segment}»; "
            "геокорректировку подготовить только как черновик для согласования."
        )
    else:
        recommendation = base_recommendation
    return problem, recommendation


def _factor_hypothesis(factor: dict[str, Any]) -> str:
    capability_id = str(factor.get("capability_id") or "")
    label = _FACTOR_CAPABILITY_LABELS.get(capability_id, "сегмент")
    segment = str(factor.get("segment") or "без названия")
    if factor.get("factor_type") == "traffic_proxy_within_peer_range":
        return (
            "CTR и CPC находятся в пределах заданных порогов сопоставимой группы; "
            "гипотеза о проблеме на верхнем уровне трафика не подтверждена. "
            "Следующий уровень проверки — структура запросов, групп, устройств, "
            "регионов или площадок."
        )
    if str(factor.get("factor_type") or "").startswith("traffic_proxy_"):
        metric_label = "CPC" if factor.get("metric") == "cpc" else "CTR"
        limitation = (
            "Конверсионная выборка пока мала; период нужно расширить до 60–90 дней."
            if factor.get("conversion_state") == "low_sample"
            else "Влияние на конверсии не подтверждено, поскольку конверсионная метрика неизвестна."
        )
        return (
            f"{label.capitalize()} «{segment}» является кандидатом отклонения качества трафика: "
            f"{metric_label} отличается от ориентира среза. {limitation}"
        )
    if factor.get("factor_type") == "segment_cpa_gap":
        best = factor.get("best_segment") or {}
        status = (
            "является подтверждённым измеримым фактором повышенного CPA"
            if factor.get("backend_confirmed")
            else "является измеримым кандидатом причины повышенного CPA"
        )
        return (
            f"{label.capitalize()} «{segment}» {status}: "
            f"CPA в {float(factor.get('cpa_ratio') or 0):.2f} раза выше, чем у сопоставимого сегмента "
            f"«{best.get('segment') or 'без названия'}»."
        )
    if factor.get("factor_type") == "waste_without_conversions":
        status = (
            "входит в подтверждённый непродуктивный расход"
            if factor.get("backend_confirmed")
            else "является измеримым кандидатом непродуктивного расхода"
        )
        return (
            f"{label.capitalize()} «{segment}» {status} "
            f"без конверсий по выбранным целям."
        )
    return (
        f"{label.capitalize()} «{segment}» — наиболее сильный измеримый фактор отклонения, "
        "который требует проверки перед изменением настроек."
    )


def build_campaign_insights(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Build stable campaign-level conclusions from trusted backend facts and evidence."""

    rows = {
        str(item.get("name") or item.get("campaign_name") or ""): item
        for item in (snapshot.get("campaignAnalysisRows") or [])
        if isinstance(item, dict) and (item.get("name") or item.get("campaign_name"))
    }
    classifications = {
        str(item.get("campaign_name") or item.get("campaignName") or ""): item
        for item in (snapshot.get("campaignClassifications") or [])
        if isinstance(item, dict)
    }
    registry = _hypothesis_registry(snapshot)
    verifications = _verification_registry(snapshot)
    hypotheses_by_campaign: dict[str, list[dict[str, Any]]] = {}
    for hypothesis_id, item in registry.items():
        if not isinstance(item, dict):
            continue
        campaign_name = str(item.get("campaign_name") or item.get("campaignName") or "")
        if not campaign_name:
            continue
        hypotheses_by_campaign.setdefault(campaign_name, []).append({
            **item,
            "_hypothesis_id": hypothesis_id,
            "_verification": verifications.get(hypothesis_id) or {},
        })
    evidence_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    evidence_by_campaign: dict[str, list[dict[str, Any]]] = {}
    for item in snapshot.get("drilldownEvidenceSummaries") or []:
        if not isinstance(item, dict):
            continue
        hypothesis_id = str(item.get("hypothesis_id") or item.get("hypothesisId") or "")
        if hypothesis_id:
            evidence_by_hypothesis.setdefault(hypothesis_id, []).append(item)
        campaign_name = str(item.get("campaign_name") or item.get("campaignName") or "")
        if campaign_name:
            evidence_by_campaign.setdefault(campaign_name, []).append(item)

    insights: list[dict[str, Any]] = []
    for fact in snapshot.get("observedFacts") or []:
        if not isinstance(fact, dict):
            continue
        campaign_name = str(fact.get("campaign_name") or fact.get("campaignName") or "")
        if not campaign_name or campaign_name == "Аккаунт":
            continue
        metric = str(fact.get("metric") or "campaign_health")
        linked = next(
            (
                item for item in hypotheses_by_campaign.get(campaign_name, [])
                if str(fact.get("fact_id") or fact.get("factId") or "") in {
                    str(value) for value in (item.get("fact_ids") or item.get("factIds") or [])
                }
            ),
            None,
        )
        hypothesis_id = str((linked or {}).get("_hypothesis_id") or "") or None
        verification = (linked or {}).get("_verification") or {}
        verification_status = str(
            verification.get("status")
            or (linked or {}).get("current_status")
            or (linked or {}).get("status")
            or "unverified"
        )
        row = rows.get(campaign_name) or {}
        classification = classifications.get(campaign_name) or linked or {}
        subtype = str(
            classification.get("campaign_subtype")
            or classification.get("campaignSubtype")
            or "unknown"
        )
        campaign_type = _final_campaign_type(classification)
        conversions = _number(
            row.get("goalConversions")
            if "goalConversions" in row
            else row.get("goal_conversions")
        )
        cpa = _number(row.get("goalCpa") if "goalCpa" in row else row.get("goal_cpa"))
        target_cpa = _number((snapshot.get("targetKpis") or {}).get("targetCpa"))
        cpa_delta = (
            round((float(cpa) / float(target_cpa) - 1) * 100, 2)
            if cpa is not None and target_cpa not in {None, 0}
            else _number(fact.get("deviation"))
        )
        evidence = _bounded_strings(fact.get("evidence"), 3)
        if cpa is not None and target_cpa is not None:
            evidence.append(f"CPA {float(cpa):.2f} при цели {float(target_cpa):.2f}; отклонение {float(cpa_delta or 0):+.1f}%.")
        evidence = list(dict.fromkeys(evidence))[:5]
        summaries = list({
            (
                str(item.get("campaign_name") or item.get("campaignName") or ""),
                str(item.get("capability_id") or item.get("capabilityId") or item.get("dimension") or ""),
                str(item.get("request_id") or item.get("requestId") or ""),
            ): item
            for item in (
                evidence_by_hypothesis.get(hypothesis_id or "", [])
                + evidence_by_campaign.get(campaign_name, [])
            )
        }.values())
        checked = list(dict.fromkeys(
            str(item.get("capability_id") or item.get("capabilityId") or item.get("dimension"))
            for item in summaries
            if item.get("status") in AVAILABLE_AUDIT_DATA_STATUSES
            and (item.get("capability_id") or item.get("capabilityId") or item.get("dimension"))
        ))[:12]
        missing = _bounded_strings(
            verification.get("remaining_data_needed")
            or (linked or {}).get("remaining_data_needed"),
            12,
        )
        sufficient = bool(
            fact.get("sufficient_data")
            if "sufficient_data" in fact
            else fact.get("sufficientData")
        )
        opportunity = metric in {"good_campaign", "stable_efficiency"}
        clicks = _number(row.get("clicks"))
        impressions = _number(row.get("impressions"))
        cost = _number(row.get("cost"))
        ctr = _number(row.get("ctr"))
        if ctr is None and clicks is not None and impressions not in {None, 0}:
            ctr = float(clicks) / float(impressions) * 100
        cpc = _number(row.get("cpc") or row.get("avgCpc") or row.get("avg_cpc"))
        if cpc is None and cost is not None and clicks not in {None, 0}:
            cpc = float(cost) / float(clicks)
        traffic_metric_parts = []
        if impressions is not None:
            traffic_metric_parts.append(f"показы {int(impressions)}")
        if ctr is not None:
            traffic_metric_parts.append(f"CTR {float(ctr):.2f}%")
        if cpc is not None:
            traffic_metric_parts.append(f"CPC {float(cpc):.2f} ₽")
        traffic_metrics_summary = ", ".join(traffic_metric_parts)
        if traffic_metrics_summary:
            evidence = list(dict.fromkeys([
                (
                    f"Трафик кампании: {traffic_metrics_summary}; "
                    "эти показатели рассчитаны независимо от доступности конверсий."
                ),
                *evidence,
            ]))[:5]
        raw_conversions = (
            row.get("goalConversions")
            if "goalConversions" in row
            else row.get("goal_conversions")
        )
        conversion_decision = classify_conversion_state(
            raw_conversions,
            sufficient_data=sufficient,
            cost=float(cost or 0),
            clicks=int(clicks or 0),
            impressions=int(impressions or 0),
        )
        scenario = select_audit_scenario(
            campaign_type=campaign_type,
            conversion_state=conversion_decision.state,
        )
        data_needed = not sufficient or metric in {"low_data", "conversion_data_unknown"}
        problem, recommendation, expected_effect = _campaign_insight_copy(
            metric=metric,
            subtype=subtype,
            verification_status=verification_status,
        )
        factor = _campaign_primary_factor(
            summaries,
            allow_traffic_proxy=conversion_decision.state in {"unknown", "low_sample"},
            allow_conversion_factors=conversion_decision.state != "low_sample",
        )
        if factor is None and conversion_decision.state in {"unknown", "low_sample"}:
            analysis_period = snapshot.get("analysisPeriod") or {}
            factor = _campaign_peer_traffic_factor(
                campaign_name,
                row,
                classification,
                rows=rows,
                classifications=classifications,
                period_days=int(
                    analysis_period.get("days")
                    or analysis_period.get("periodDays")
                    or 0
                ),
            )
        factor_matches_linked_hypothesis = bool(
            factor
            and hypothesis_id
            and str(factor.get("hypothesis_id") or "") == hypothesis_id
        )
        traffic_proxy_factor = bool(
            factor
            and str(factor.get("factor_type") or "").startswith("traffic_proxy_")
        )
        effective_verification_status = (
            "confirmed"
            if factor and not traffic_proxy_factor and (
                factor.get("backend_confirmed")
                or (
                    factor_matches_linked_hypothesis
                    and verification_status == "confirmed"
                )
            )
            else "unverified"
            if factor
            else verification_status
        )
        if factor:
            factor["backend_confirmed"] = effective_verification_status == "confirmed"
            factor["conversion_state"] = conversion_decision.state
            problem, recommendation = _factor_copy(
                factor,
                base_problem=problem,
                base_recommendation=recommendation,
                verification_status=effective_verification_status,
            )
            evidence = list(dict.fromkeys(evidence + _factor_evidence(factor)))[:5]
            factor_capability = str(factor.get("capability_id") or "")
            if factor.get("backend_confirmed") or int(factor.get("period_days") or 0) >= 90:
                missing = []
            elif factor_capability and not traffic_proxy_factor:
                missing = [factor_capability]
        traffic_hypothesis = None
        if conversion_decision.state in {"unknown", "low_sample"} and factor is None and traffic_metrics_summary:
            low_sample = conversion_decision.state == "low_sample"
            problem = (
                (
                    "Конверсионная выборка мала, но трафик не оставлен без анализа: "
                    if low_sample
                    else "Конверсионная метрика недоступна, но трафик не оставлен без анализа: "
                )
                + f"{traffic_metrics_summary}. Для безопасного сравнительного вывода "
                "пока недостаточно однородной контрольной группы."
            )
            traffic_hypothesis = (
                "CTR и CPC рассчитаны, но отклонение нельзя надёжно подтвердить без "
                "сопоставимой группы или детального среза; следующим шагом проверяются "
                "запросы, группы, устройства, регионы и площадки."
            )
            recommendation = (
                (
                    "Не ограничиваться расширением периода: использовать уже собранные "
                    if low_sample
                    else "Не ограничиваться проверкой выбранных целей: использовать уже собранные "
                )
                +
                "срезы для поиска запросов, групп, устройств, регионов или площадок с "
                "аномальными CTR/CPC; "
                + (
                    "параллельно расширить период до 60 дней и при необходимости до 90 дней."
                    if low_sample
                    else "корректность целей и передачу конверсий проверить параллельно."
                )
            )
            expected_effect = (
                "Выделить проверяемую причину отклонения качества трафика и подтвердить "
                "её на достаточной конверсионной выборке."
                if low_sample
                else "Выделить проверяемую причину отклонения качества трафика, не подменяя "
                "неизвестные конверсии нулевыми."
            )
        elif traffic_proxy_factor:
            expected_effect = (
                "Локализовать отклонение качества трафика по измеримым CTR/CPC и затем "
                "проверить его на конверсионных данных."
            )
        display_metric = metric
        if conversion_decision.state in {"unknown", "low_sample"}:
            factor_metric = str((factor or {}).get("metric") or "")
            if factor_metric == "cpc":
                display_metric = "high_cpc_traffic_proxy"
            elif factor_metric == "ctr":
                display_metric = "low_ctr"
            elif factor and factor.get("factor_type") == "traffic_proxy_within_peer_range":
                display_metric = "traffic_metrics_reviewed"
            elif traffic_metrics_summary:
                display_metric = "traffic_metrics_available"
        priority = (
            "data_needed" if data_needed
            else "opportunity" if opportunity
            else "critical" if metric == "spend_without_goal_conversions"
            else "high" if metric in {"cpa_above_target", "goal_conversions_drop", "budget_spike"}
            else "medium"
        )
        insights.append({
            "priority": priority,
            "campaign_name": campaign_name,
            "campaign_type": campaign_type,
            "signal_type": display_metric,
            "signal_status": "data_needed" if data_needed else "opportunity" if opportunity else "detected",
            "hypothesis_id": hypothesis_id,
            "verification_status": effective_verification_status,
            "cost": cost,
            "clicks": int(clicks) if clicks is not None else None,
            "impressions": int(impressions) if impressions is not None else None,
            "ctr": round(float(ctr), 4) if ctr is not None else None,
            "cpc": round(float(cpc), 4) if cpc is not None else None,
            "conversions": float(conversions) if conversions is not None else None,
            "cpa": float(cpa) if cpa is not None else None,
            "target_cpa": float(target_cpa) if target_cpa is not None else None,
            "cpa_delta_pct": float(cpa_delta) if cpa_delta is not None else None,
            "conversion_state": conversion_decision.state,
            "conversion_state_reason": conversion_decision.reason,
            "analysis_mode": scenario.analysis_mode,
            "scenario_id": scenario.scenario_id,
            "scenario_version": scenario.public_dict()["scenario_version"],
            "scenario_checks": list(scenario.must_analyze)[:10],
            "forbidden_claims": list(scenario.forbidden_claims)[:5],
            "problem": problem,
            "evidence": evidence,
            "hypothesis": (
                _factor_hypothesis(factor)
                if factor
                else traffic_hypothesis
                or str((linked or {}).get("hypothesis") or "")
                or None
            ),
            "checked_capabilities": checked,
            "missing_capabilities": missing,
            "recommendation": recommendation,
            "expected_effect": expected_effect,
            "confidence": (
                "high" if sufficient and effective_verification_status == "confirmed"
                else "medium" if sufficient
                else "low"
            ),
            "requires_human_approval": True,
        })
    insights.sort(key=lambda item: (
        _CAMPAIGN_SIGNAL_PRIORITY.get(item["signal_type"], 99),
        -float(item.get("cost") or 0),
        item["campaign_name"],
    ))
    primary_by_campaign: list[dict[str, Any]] = []
    seen_campaigns: set[str] = set()
    for item in insights:
        if item["campaign_name"] in seen_campaigns:
            continue
        seen_campaigns.add(item["campaign_name"])
        primary_by_campaign.append(item)
    return primary_by_campaign[:50]


def _final_rule_summaries(values: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    result = []
    for raw in values:
        if not isinstance(raw, dict):
            continue
        result.append({
            "ruleCode": str(raw.get("rule_code") or raw.get("ruleCode") or "")[:120] or None,
            "passed": bool(raw.get("passed")),
            "summary": _safe_final_text(raw.get("summary"), max_chars=500) or None,
        })
        if len(result) >= limit:
            break
    return result


def _final_diagnostics(value: Any, *, limit: int) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    def safe_factor(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        return {
            "segment": _safe_final_text(raw.get("segment"), max_chars=300),
            "cost": _number(raw.get("cost")),
            "costSharePct": _number(raw.get("cost_share_pct") or raw.get("costSharePct")),
            "clicks": _safe_coverage_count(raw.get("clicks"), default=0),
            "conversions": _number(raw.get("conversions")),
            "cpa": _number(raw.get("cpa")),
        }

    top_waste = [
        item for item in (safe_factor(raw) for raw in (value.get("top_waste") or []))
        if item is not None
    ][:limit]
    top_high_cpa = [
        item for item in (safe_factor(raw) for raw in (value.get("top_high_cpa") or []))
        if item is not None
    ][:limit]
    return {
        "kind": str(value.get("kind") or "")[:80] or None,
        "materialWaste": bool(value.get("material_waste")),
        "wasteCost": _number(value.get("waste_cost")),
        "wasteClicks": _safe_coverage_count(value.get("waste_clicks"), default=0),
        "wasteSharePct": _number(value.get("waste_share_pct")),
        "cpaRatio": _number(value.get("cpa_ratio")),
        "topWaste": top_waste,
        "topHighCpa": top_high_cpa,
        "worstSegment": safe_factor(value.get("worst_segment")),
        "bestSegment": safe_factor(value.get("best_segment")),
    }


def _final_evidence_summary(item: dict[str, Any], *, example_limit: int) -> dict[str, Any]:
    numeric = item.get("numeric_state_counts") or item.get("numericStateCounts") or {}
    return {
        "capabilityId": str(item.get("capability_id") or item.get("capabilityId") or item.get("dimension") or "")[:100],
        "status": str(item.get("status") or "unknown")[:50],
        "rowsAnalyzed": int(item.get("rows_total") or item.get("rowsAnalyzed") or item.get("segments") or 0),
        "metrics": _safe_metric_values(item.get("metrics")),
        "numericStateCounts": {
            "known": int(numeric.get("known") or 0),
            "missing": int(numeric.get("missing") or 0),
            "invalid": int(numeric.get("invalid") or 0),
        },
        "confirmationRules": _final_rule_summaries(
            item.get("matched_confirmation_rules") or item.get("confirmation_rules"), example_limit,
        ),
        "rejectionRules": _final_rule_summaries(
            item.get("matched_rejection_rules") or item.get("rejection_rules"), example_limit,
        ),
        "diagnostics": _final_diagnostics(item.get("diagnostics"), limit=example_limit),
        "limitations": _bounded_strings(
            item.get("limitations") or item.get("data_quality_warnings"), example_limit,
        ),
    }


def _final_classification_summary(classifications: list[dict[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, int] = {}
    by_subtype: dict[str, int] = {}
    for item in classifications:
        family = str(item.get("campaign_family") or item.get("campaignFamily") or "unknown")
        subtype = str(item.get("campaign_subtype") or item.get("campaignSubtype") or "unknown")
        by_family[family] = by_family.get(family, 0) + 1
        by_subtype[subtype] = by_subtype.get(subtype, 0) + 1
    return {"total": len(classifications), "byFamily": by_family, "bySubtype": by_subtype}


def _final_canonical_coverage_projection(
    snapshot: dict[str, Any], *, compaction_level: int,
) -> dict[str, Any]:
    """Keep model-facing coverage bounded without changing the UI/API matrix."""

    coverage = snapshot.get("canonicalEvidenceCoverage") or {}
    summary = coverage.get("summary") if isinstance(coverage, dict) else {}
    safe_summary = {
        str(key)[:80]: value
        for key, value in (summary.items() if isinstance(summary, dict) else [])
        if isinstance(value, (int, float, bool)) and not isinstance(value, str)
    }
    matrix = coverage.get("campaignMatrix") if isinstance(coverage, dict) else []
    compact_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for raw in matrix if isinstance(matrix, list) else []:
        if not isinstance(raw, dict):
            continue
        status_value = str(raw.get("status") or "unknown")[:50]
        status_counts[status_value] = status_counts.get(status_value, 0) + 1
        compact_rows.append({
            "campaignName": _safe_final_text(raw.get("campaignName"), max_chars=300) or "Кампания без названия",
            "capabilityId": str(raw.get("capabilityId") or "unknown")[:100],
            "status": status_value,
            "rowsReceived": _safe_coverage_count(raw.get("rowsReceived"), default=0) or 0,
            "rowsAnalyzedByBackend": _safe_coverage_count(raw.get("rowsAnalyzedByBackend"), default=0) or 0,
            "rowsSentToAi": _safe_coverage_count(raw.get("rowsSentToAi"), default=0) or 0,
            "dataQuality": str(raw.get("dataQuality") or "unknown")[:50],
            "applicable": bool(raw.get("applicable", True)),
            "absenceReason": _safe_final_text(raw.get("absenceReason"), max_chars=120),
        })

    status_rank = {
        "failed": 0,
        "unavailable": 1,
        "partial": 2,
        "insufficient_data": 3,
        "not_requested": 4,
        "collected": 5,
        "not_applicable": 6,
    }
    compact_rows.sort(key=lambda item: (
        status_rank.get(item["status"], 7), item["campaignName"], item["capabilityId"],
    ))
    row_limit = {0: 48, 1: 30, 2: 18, 3: 10}.get(max(0, min(int(compaction_level), 3)), 10)
    account_wide = coverage.get("accountWide") if isinstance(coverage, dict) else []
    account_wide = account_wide if isinstance(account_wide, list) else []
    compact_account = [
        {
            "capabilityId": str(item.get("capabilityId") or "unknown")[:100],
            "status": str(item.get("status") or "unknown")[:50],
            "rowsReceived": _safe_coverage_count(item.get("rowsReceived"), default=0) or 0,
            "rowsAnalyzedByBackend": _safe_coverage_count(item.get("rowsAnalyzedByBackend"), default=0) or 0,
        }
        for item in account_wide[:20]
        if isinstance(item, dict)
    ]
    return {
        "summary": safe_summary,
        "matrixRowsTotal": len(compact_rows),
        "matrixStatusCounts": status_counts,
        "accountWide": compact_account,
        "campaignMatrix": compact_rows[:row_limit],
    }


def build_final_audit_projection(
    snapshot: dict[str, Any],
    *,
    compaction_level: int = 0,
) -> dict[str, Any]:
    """Build the only snapshot projection allowed into the final model prompt."""

    level = max(0, min(int(compaction_level), 3))
    example_limit = 5 if level == 0 else 3 if level < 3 else 2
    limitation_limit = 10 if level == 0 else 3
    facts_by_id, all_facts = _final_fact_records(snapshot)
    registry = _hypothesis_registry(snapshot)
    verifications = _verification_registry(snapshot)
    evidence_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for raw in snapshot.get("drilldownEvidenceSummaries") or []:
        if not isinstance(raw, dict):
            continue
        hypothesis_id = str(raw.get("hypothesis_id") or raw.get("hypothesisId") or "")
        if hypothesis_id:
            evidence_by_hypothesis.setdefault(hypothesis_id, []).append(raw)

    hypotheses: list[dict[str, Any]] = []
    for hypothesis_id, raw in registry.items():
        if not isinstance(raw, dict):
            continue
        verification = verifications.get(hypothesis_id) or {}
        fact_ids = [str(value) for value in (raw.get("fact_ids") or raw.get("factIds") or [])]
        linked_facts = [facts_by_id[value] for value in fact_ids if value in facts_by_id]
        fact_summary = " ".join(item["summary"] for item in linked_facts)[:1200]
        evidence = [
            _final_evidence_summary(item, example_limit=example_limit)
            for item in evidence_by_hypothesis.get(hypothesis_id, [])[:example_limit]
        ]
        status_value = str(verification.get("status") or raw.get("current_status") or "unverified")
        limitations = _bounded_strings(verification.get("limitations"), limitation_limit)
        for item in evidence:
            limitations.extend(value for value in item["limitations"] if value not in limitations)
        priority = str(raw.get("priority") or "medium")
        hypotheses.append({
            "hypothesisId": hypothesis_id,
            "campaignName": str(raw.get("campaign_name") or raw.get("campaignName") or "Аккаунт")[:300],
            "campaignType": _final_campaign_type(raw),
            "hypothesisType": str(raw.get("hypothesis_type") or raw.get("hypothesisType") or "campaign_metadata_issue")[:100],
            "factSummary": fact_summary or _safe_final_text(
                raw.get("observed_fact") or "Исходный факт не детализирован.", max_chars=1200,
            ),
            "verificationStatus": status_value,
            "evidenceSummary": evidence,
            "supportingEvidence": _bounded_strings(verification.get("supporting_evidence"), example_limit),
            "contradictingEvidence": _bounded_strings(verification.get("contradicting_evidence"), example_limit),
            "limitations": limitations[:limitation_limit],
            "remainingDataNeeded": _bounded_strings(verification.get("remaining_data_needed"), limitation_limit),
            "priority": priority,
            "criticalUnverified": status_value == "unverified" and (
                priority in {"critical", "high"}
                or any(
                    facts_by_id.get(fact_id, {}).get("metric") in {
                        "spend_without_goal_conversions", "cpa_above_target",
                        "tracking_inconsistency", "conversion_data_unknown",
                    }
                    for fact_id in fact_ids
                )
            ),
        })

    status_rank = {"confirmed": 0, "partially_confirmed": 1, "unverified": 2, "rejected": 3, "not_applicable": 4}
    hypotheses.sort(key=lambda item: (
        status_rank.get(item["verificationStatus"], 5),
        0 if item["criticalUnverified"] else 1,
        item["campaignName"],
        item["hypothesisId"],
    ))
    all_hypotheses = list(hypotheses)
    if level == 2:
        hypotheses = hypotheses[:10]
    elif level >= 3:
        hypotheses = [
            item for item in hypotheses
            if item["verificationStatus"] in {"confirmed", "partially_confirmed"} or item["criticalUnverified"]
        ][:10]

    omitted = [item for item in all_hypotheses if item not in hypotheses]
    omitted_by_status: dict[str, int] = {}
    omitted_by_type: dict[str, int] = {}
    for item in omitted:
        omitted_by_status[item["verificationStatus"]] = omitted_by_status.get(item["verificationStatus"], 0) + 1
        omitted_by_type[item["campaignType"]] = omitted_by_type.get(item["campaignType"], 0) + 1
    for item in hypotheses:
        item.pop("criticalUnverified", None)
        item.pop("priority", None)

    classifications = [item for item in (snapshot.get("campaignClassifications") or []) if isinstance(item, dict)]
    selected_campaigns = {item["campaignName"] for item in hypotheses}
    compact_classifications = [{
        "campaignName": str(item.get("campaign_name") or item.get("campaignName") or "Кампания без названия")[:300],
        "campaignFamily": str(item.get("campaign_family") or item.get("campaignFamily") or "unknown")[:50],
        "campaignSubtype": str(item.get("campaign_subtype") or item.get("campaignSubtype") or "unknown")[:80],
    } for item in classifications]
    if level >= 2:
        compact_classifications = [
            item for item in compact_classifications if item["campaignName"] in selected_campaigns
        ][:20 if level == 2 else 10]

    selected_fact_summaries = {
        item["factSummary"] for item in hypotheses if item.get("factSummary")
    }
    fact_limit = 100 if level == 0 else 40 if level == 1 else 15 if level == 2 else 10
    observed_facts = [item for item in all_facts if item["summary"] not in selected_fact_summaries][:fact_limit]

    numeric_counts = {"known": 0, "missing": 0, "invalid": 0}
    for items in evidence_by_hypothesis.values():
        for item in items:
            counts = item.get("numeric_state_counts") or item.get("numericStateCounts") or {}
            for key in numeric_counts:
                numeric_counts[key] += int(counts.get(key) or 0)
    source_counts: dict[str, int] = {}
    for item in snapshot.get("baselineEvidenceSummary") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unavailable")
        source_counts[source] = source_counts.get(source, 0) + 1
    analysis_period = snapshot.get("analysisPeriod") or {}
    if analysis_period.get("source"):
        source = str(analysis_period["source"])
        source_counts[source] = source_counts.get(source, 0) + 1

    warnings = _bounded_strings((snapshot.get("trackingStatus") or {}).get("warnings"), limitation_limit)
    warnings.extend(_bounded_strings(snapshot.get("missingData"), limitation_limit))
    warnings.extend(_bounded_strings(snapshot.get("limitations"), limitation_limit))
    warnings.extend(
        _safe_final_text(item.get("message"), max_chars=500)
        for item in (snapshot.get("auditWarnings") or [])[:limitation_limit]
        if isinstance(item, dict) and item.get("message")
    )
    limitations = list(dict.fromkeys(value for value in warnings if value))[:limitation_limit]
    policy_coverage = public_evidence_coverage(snapshot)
    incomplete_requirements = [
        item
        for item in policy_coverage.get("requirements") or []
        if item.get("status") in {"partial", "blocked", "missing", "processing"}
    ][:20 if level < 2 else 10]
    missing_requirements = [
        item for item in incomplete_requirements
        if item.get("status") in {"blocked", "missing", "processing"}
    ]
    partial_requirements = [
        item for item in incomplete_requirements
        if item.get("status") == "partial"
    ]

    coverage = _final_canonical_coverage_projection(snapshot, compaction_level=level)
    decision_limit = 20 if level < 2 else 10
    decision_scenarios = [
        {
            "campaignName": item["campaign_name"],
            "campaignType": item["campaign_type"],
            "conversionState": item["conversion_state"],
            "conversionStateReason": item["conversion_state_reason"],
            "analysisMode": item["analysis_mode"],
            "scenarioId": item["scenario_id"],
            "scenarioVersion": item["scenario_version"],
            "mustAnalyze": item["scenario_checks"][:6 if level < 2 else 3],
            "forbiddenClaims": item["forbidden_claims"][:3],
        }
        for item in build_campaign_insights(snapshot)[:decision_limit]
    ]
    return {
        "analysisPeriod": {
            key: analysis_period.get(key)
            for key in (
                "dateFrom", "dateTo", "days", "comparisonDateFrom", "comparisonDateTo",
                "requestedMatchesAvailableData", "source",
            )
            if key in analysis_period
        },
        "dataCoverage": coverage,
        "accountTotals": _safe_metric_values(snapshot.get("accountTotals")),
        "targetKpis": _safe_metric_values(snapshot.get("targetKpis")),
        "selectedGoals": {
            "ids": [str(value)[:64] for value in ((snapshot.get("selectedGoals") or {}).get("ids") or [])[:20]],
            "hasGoalData": bool((snapshot.get("selectedGoals") or {}).get("hasGoalData")),
            "message": _safe_final_text(
                (snapshot.get("selectedGoals") or {}).get("message"), max_chars=500,
            ) or None,
        },
        "campaignClassificationSummary": _final_classification_summary(classifications),
        "campaignClassifications": compact_classifications,
        "campaignDecisionScenarios": decision_scenarios,
        "observedFacts": observed_facts,
        "verificationRegistry": hypotheses,
        "omittedHypothesesSummary": {
            "count": len(omitted), "byStatus": omitted_by_status, "byCampaignType": omitted_by_type,
        },
        "dataQualitySummaries": {"numericStateCounts": numeric_counts},
        "sourceSummaries": source_counts,
        "auditCompletionState": policy_coverage.get("completionState"),
        "evidenceCoverageSummary": {
            **(policy_coverage.get("summary") or {}),
            "required": int((policy_coverage.get("summary") or {}).get("requiredTotal") or 0),
        },
        "missingRequiredEvidence": missing_requirements,
        "partialRequiredEvidence": partial_requirements,
        "incompleteRequiredEvidence": incomplete_requirements,
        "limitations": limitations,
        "stopReason": _safe_final_text(
            (snapshot.get("auditRuntime") or {}).get("stopReason"), max_chars=300,
        ) or None,
        "compactionLevel": level,
    }


def _provider_error_fragments(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 4 or value is None:
        return []
    if isinstance(value, dict):
        fragments: list[str] = []
        for key, item in value.items():
            if str(key).lower() in {"code", "type", "error_code", "message", "detail", "error"}:
                fragments.extend(_provider_error_fragments(item, depth=depth + 1))
        return fragments
    if isinstance(value, (list, tuple)):
        fragments = []
        for item in value[:20]:
            fragments.extend(_provider_error_fragments(item, depth=depth + 1))
        return fragments
    return [str(value)[:2000]]


def is_provider_context_overflow(exc: Exception) -> bool:
    """Recognize provider-confirmed context overflow without exposing provider text."""

    if isinstance(exc, HTTPException) and exc.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_408_REQUEST_TIMEOUT,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_504_GATEWAY_TIMEOUT,
    }:
        return False
    detail = getattr(exc, "detail", None)
    fragments = _provider_error_fragments(detail)
    fragments.extend(_provider_error_fragments(str(exc)))
    normalized = " ".join(fragments).lower()
    normalized_code = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if any(code in normalized_code for code in _PROVIDER_CONTEXT_OVERFLOW_CODES):
        return True
    return any(marker in normalized for marker in _PROVIDER_CONTEXT_OVERFLOW_MARKERS)


def final_provider_timeout_code(exc: Exception) -> str | None:
    """Return only normalized final-provider timeout codes that are safe to expose."""

    if not isinstance(exc, HTTPException) or not isinstance(exc.detail, dict):
        return None
    error_code = str(exc.detail.get("error_code") or "")
    return error_code if error_code in _FINAL_PROVIDER_TIMEOUT_CODES else None


def _effective_final_output_tokens(job: AiAuditJob) -> int:
    return max(1, min(int(job.max_tokens or 0), FINAL_AUDIT_PROVIDER_MAX_TOKENS))


def _effective_final_model(job: AiAuditJob) -> str:
    """Use the latency-optimized structured model for the five-minute summary."""

    profile = execution_profile_for_scope(job.requested_scope)
    return AI_FALLBACK_ECONOMY_MODEL if profile.id == "short_summary" else job.model


def _remaining_final_provider_seconds(snapshot: dict[str, Any]) -> float | None:
    """Return the provider budget left before the audit hard deadline."""

    remaining = scheduler_deadline_state(snapshot).get("remainingSeconds")
    if remaining is None:
        return float(AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS["generate_answer"])
    return max(
        0.0,
        min(
            float(AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS["generate_answer"]),
            float(remaining) - FINALIZATION_COMMIT_RESERVE_SECONDS,
        ),
    )


def _verification_can_start(job: AiAuditJob, snapshot: dict[str, Any]) -> bool:
    """Reserve enough wall time for the final model before helper verification."""

    remaining = scheduler_deadline_state(snapshot).get("remainingSeconds")
    if remaining is None:
        return True
    profile = _audit_execution_profile(job, snapshot)
    required_seconds = (
        profile.finalization_reserve_seconds
        + int(AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS["verify_hypotheses"])
        + FINALIZATION_COMMIT_RESERVE_SECONDS
    )
    return int(remaining) > required_seconds


def _final_schema_repair_timeout(job: AiAuditJob, snapshot: dict[str, Any]) -> httpx.Timeout | None:
    """Bound a formatting-only retry by both the stage lease and audit deadline."""
    expires_at = _as_aware(job.stage_lease_expires_at) if job.stage_lease_expires_at else None
    if expires_at is None:
        return None
    deadline_budget = _remaining_final_provider_seconds(snapshot)
    remaining_seconds = int((expires_at - _now()).total_seconds())
    if deadline_budget is not None:
        remaining_seconds = min(remaining_seconds, int(deadline_budget))
    if remaining_seconds < FINAL_SCHEMA_REPAIR_MIN_REMAINING_SECONDS:
        return None
    read_seconds = min(FINAL_SCHEMA_REPAIR_MAX_SECONDS, max(1, remaining_seconds - 10))
    connect_seconds = min(10.0, float(read_seconds))
    return httpx.Timeout(
        connect=connect_seconds,
        read=float(read_seconds),
        write=connect_seconds,
        pool=connect_seconds,
    )


def _build_final_schema_repair_prompt(snapshot: dict[str, Any], job: AiAuditJob) -> tuple[str, dict[str, Any]]:
    """Re-run the final analysis from trusted evidence, never from an invalid model response."""
    bundle = build_final_audit_prompt_bundle(
        snapshot,
        job,
        compact_retry=True,
        minimum_compaction_level=2,
    )
    prompt = str(bundle.get("prompt") or "")
    return (
        f"""{prompt}

Форматное восстановление: предыдущий ответ не прошёл JSON-контракт.
Сформируй новый результат только по trusted evidence projection выше. Не используй и не пересказывай предыдущий ответ.
Верни ровно один валидный JSON-объект по указанному контракту: без Markdown, пояснений или текста вне JSON.""",
        dict(bundle.get("diagnostics") or {}),
    )


def build_final_audit_prompt_bundle(
    snapshot: dict[str, Any],
    job: AiAuditJob,
    *,
    compact_retry: bool = False,
    minimum_compaction_level: int | None = None,
) -> dict[str, Any]:
    start_level = (
        max(0, min(int(minimum_compaction_level), 3))
        if minimum_compaction_level is not None
        else (2 if compact_retry else 0)
    )
    context_limit = context_limit_for_model(job.model)
    requested_output = max(1, min(int(job.max_tokens or 0), AI_AUDIT_FINAL_MAX_TOKENS))
    reserved_output = _effective_final_output_tokens(job)
    safety_margin = min(FINAL_PROMPT_SAFETY_MARGIN_TOKENS, max(512, context_limit // 50))
    candidate: dict[str, Any] | None = None
    for level in FINAL_COMPACTION_LEVELS[start_level:]:
        projection = build_final_audit_projection(snapshot, compaction_level=level)
        prompt = build_full_audit_prompt(
            projection,
            output_budget_tokens=reserved_output,
            compact_retry=compact_retry or level > 0,
        )
        prompt_tokens = estimate_tokens(f"{DEFAULT_SYSTEM_PROMPT}\n{prompt}")
        diagnostics = {
            "finalProjectionEstimatedTokens": estimate_tokens(_json_dump(projection)),
            "finalPromptEstimatedTokens": prompt_tokens,
            "modelContextLimit": context_limit,
            "reservedOutputTokens": reserved_output,
            "requestedOutputTokens": requested_output,
            "effectiveFinalOutputTokens": reserved_output,
            "safetyMarginTokens": safety_margin,
            "finalCompactionLevel": level,
            "fitsModelContext": prompt_tokens + reserved_output + safety_margin <= context_limit,
            "preflightFitsModelContext": prompt_tokens + reserved_output + safety_margin <= context_limit,
            "providerContextRejected": False,
            "providerContextErrorCode": None,
        }
        candidate = {"projection": projection, "prompt": prompt, "diagnostics": diagnostics}
        if diagnostics["fitsModelContext"]:
            return candidate
    return candidate or {"projection": {}, "prompt": "", "diagnostics": {}}


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
    return f"""Задача: провести полный read-only аудит Яндекс.Директа по compact evidence projection DirectPilot.
Фактический источник данных: {_audit_source_description(snapshot)}.
Scope: {scope_instruction}
Доступный максимум ответа — {output_budget_tokens} токенов. Это потолок, а не целевой объём. Дай полный, но компактный ответ.
Не обрывай разделы и finding. Если данных много, сокращай второстепенные примеры и повторяющиеся evidence.
Зарезервируй место для action_plan, limitations и conclusion. {compact_retry_instruction}

{build_direct_analyst_instructions(snapshot)}

Релевантные фрагменты базы знаний:
{knowledge_text or '- Дополнительные фрагменты не выбраны.'}

Final audit projection:
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

Evidence policy обязателен: сначала проверь auditCompletionState и evidenceCoverageSummary.
campaignDecisionScenarios выбраны backend по фактическому состоянию данных. Соблюдай mustAnalyze и forbiddenClaims. При conversionState=unknown продолжай traffic-proxy анализ, но не рассчитывай CPA и не называй неизвестную метрику нулём.
Если auditCompletionState=partial_coverage, явно перечисли ограничения и не выдавай частично подтверждённую причину за установленный факт.
Если auditCompletionState=blocked_missing_evidence, полный причинный аудит не завершён: не формируй уверенный action_plan по затронутым сигналам и укажи недостающие обязательные данные.
Статусы unavailable, partial и missing не заменяй нулевыми значениями.

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


_COVERAGE_AVAILABLE_TRUE = {"true", "available", "collected", "partial", "live"}
_COVERAGE_AVAILABLE_FALSE = {"false", "unavailable", "missing", "failed", "not_applicable"}
_COVERAGE_PERIOD_KEYS = ("dateFrom", "dateTo", "date_from", "date_to", "days")
_COVERAGE_MAX_COUNT = 2_147_483_647


def _safe_coverage_count(value: Any, *, default: int | None) -> int | None:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed_float = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if not parsed_float.is_integer():
        return default
    parsed = int(parsed_float)
    if parsed < 0 or parsed > _COVERAGE_MAX_COUNT:
        return default
    return parsed


def _safe_coverage_text(value: Any, *, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = _safe_final_text(value, max_chars=max_chars)
    return text or None


def _safe_coverage_period(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    period: dict[str, Any] = {}
    for key in _COVERAGE_PERIOD_KEYS:
        raw_value = value.get(key)
        if key == "days":
            days = _safe_coverage_count(raw_value, default=None)
            if days is not None:
                period[key] = days
        elif isinstance(raw_value, str) and raw_value.strip():
            period[key] = raw_value.strip()[:100]
    return period or None


def build_trusted_result_data_coverage(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Convert internal coverage diagnostics to the strict public audit-result contract."""
    raw_coverage = snapshot.get("dataCoverage") if isinstance(snapshot, dict) else None
    if not isinstance(raw_coverage, dict):
        raw_coverage = {}

    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, raw_item in raw_coverage.items():
        if not isinstance(raw_item, dict):
            continue
        name = str(raw_name).strip()[:100]
        if not name:
            continue

        analyzed = _safe_coverage_count(raw_item.get("analyzed"), default=0)
        total = _safe_coverage_count(raw_item.get("total"), default=None)
        raw_available = raw_item.get("available")
        numeric_available = (
            _safe_coverage_count(raw_available, default=None)
            if not isinstance(raw_available, (bool, str))
            else None
        )
        if name == "campaigns" and total is None and numeric_available is not None:
            # The live campaign builder stores the number of fetched campaigns in this field.
            total = numeric_available

        inferred_available = bool((analyzed or 0) > 0 or (total or 0) > 0)
        if isinstance(raw_available, bool):
            available = raw_available
        elif numeric_available is not None:
            available = numeric_available > 0
        elif isinstance(raw_available, str):
            normalized_available = raw_available.strip().lower()
            if normalized_available in _COVERAGE_AVAILABLE_TRUE:
                available = True
            elif normalized_available in _COVERAGE_AVAILABLE_FALSE:
                available = False
            else:
                available = inferred_available
        else:
            available = inferred_available

        raw_limitations = raw_item.get("limitations")
        limitations = _bounded_strings(
            [item for item in raw_limitations if isinstance(item, str)]
            if isinstance(raw_limitations, list)
            else [],
            20,
            max_chars=500,
        )
        normalized[name] = {
            "available": available,
            "total": total,
            "analyzed": analyzed or 0,
            "source": _safe_coverage_text(raw_item.get("source"), max_chars=200),
            "period": _safe_coverage_period(raw_item.get("period")),
            "reason": _safe_coverage_text(raw_item.get("reason"), max_chars=500),
            "limitations": limitations,
        }

    # Staged collection is campaign-scoped, while dataCoverage originates from
    # the initial account snapshot. Reconcile the public result with the
    # canonical evidence matrix so the final report cannot call collected
    # Direct slices `not_collected`.
    coverage_key_by_capability = {
        "ad_groups": "adGroups",
        "ad_group_performance": "adGroups",
        "keywords": "keywords",
        "keyword_performance": "keywords",
        "search_queries": "searchQueries",
        "placements": "placements",
        "audiences": "audiences",
        "audience_targets": "audiences",
        "ads": "adsAndCreatives",
        "ads_creatives": "adsAndCreatives",
        "demographics": "demographics",
        "devices": "devices",
        "geo": "geo",
        "goals": "goals",
        "conversions_by_goal": "goals",
        "lead_quality": "crmLeadQuality",
    }
    canonical = snapshot.get("canonicalEvidenceCoverage") if isinstance(snapshot, dict) else None
    campaign_entries = (
        canonical.get("campaignScoped")
        if isinstance(canonical, dict) and isinstance(canonical.get("campaignScoped"), list)
        else []
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in campaign_entries:
        if not isinstance(item, dict):
            continue
        rows_received = _safe_coverage_count(item.get("rowsReceived"), default=0) or 0
        if rows_received <= 0 or item.get("status") not in AVAILABLE_AUDIT_DATA_STATUSES:
            continue
        capability = str(item.get("capabilityId") or "").strip()
        if not capability:
            continue
        grouped.setdefault(coverage_key_by_capability.get(capability, capability), []).append(item)

    for name, items in grouped.items():
        total = sum(_safe_coverage_count(item.get("rowsReceived"), default=0) or 0 for item in items)
        analyzed = sum(
            _safe_coverage_count(
                item.get("rowsAnalyzedByBackend"),
                default=_safe_coverage_count(item.get("rowsReceived"), default=0),
            ) or 0
            for item in items
        )
        sources = list(dict.fromkeys(
            str(item.get("source")).strip()
            for item in items
            if str(item.get("source") or "").strip()
        ))
        limitations = list(dict.fromkeys(
            str(value).strip()[:500]
            for item in items
            for value in (item.get("limitations") or [])
            if isinstance(value, str) and value.strip()
        ))[:20]
        normalized[name] = {
            "available": True,
            "total": total,
            "analyzed": analyzed,
            "source": ", ".join(sources)[:200] or None,
            "period": _safe_coverage_period(items[0].get("period")),
            "reason": None,
            "limitations": limitations,
        }
    return normalized


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
        "data_coverage": build_trusted_result_data_coverage(snapshot),
        "model": response.get("model") or job.model,
        "output_budget_tokens": _effective_final_output_tokens(job),
    }


def _safe_final_schema_repair_diagnostics(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    def response_metadata(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        return {
            "sha256": str(item.get("sha256") or "")[:64] or None,
            "length": max(0, int(item.get("length") or 0)),
            "sourceFormat": str(item.get("sourceFormat") or "")[:100] or None,
            "fullResponseStored": bool(item.get("fullResponseStored")),
        }

    return {
        "attempted": bool(value.get("attempted")),
        "status": str(value.get("status") or "unknown")[:100],
        "errorCode": str(value.get("errorCode") or "")[:100] or None,
        "returnedModel": str(value.get("returnedModel") or "")[:200] or None,
        "promptEstimatedTokens": max(0, int(value.get("promptEstimatedTokens") or 0)),
        "compactionLevel": max(0, int(value.get("compactionLevel") or 0)),
        "initialParsing": _safe_model_response_parsing(value.get("initialParsing")),
        "parsing": _safe_model_response_parsing(value.get("parsing")),
        "initialResponse": response_metadata(value.get("initialResponse")),
        "response": response_metadata(value.get("response")),
    }


def _record_final_generation_diagnostics(
    snapshot: dict[str, Any],
    job: AiAuditJob,
    diagnostics: dict[str, Any],
    *,
    status_value: str,
    backend_fallback_used: bool = False,
) -> None:
    safe_diagnostics = {
        key: diagnostics.get(key)
        for key in (
            "finalProjectionEstimatedTokens", "finalPromptEstimatedTokens", "modelContextLimit",
            "reservedOutputTokens", "safetyMarginTokens", "finalCompactionLevel", "fitsModelContext",
            "preflightFitsModelContext", "providerContextRejected", "providerContextErrorCode",
            "requestedOutputTokens", "effectiveFinalOutputTokens", "providerTimedOut", "providerErrorCode",
        )
    }
    safe_diagnostics["schemaRepair"] = _safe_final_schema_repair_diagnostics(
        diagnostics.get("schemaRepair"),
    )
    runtime = _audit_runtime(snapshot)
    runtime.update(safe_diagnostics)
    runtime["finalGenerationStatus"] = status_value
    runtime["backendFallbackUsed"] = backend_fallback_used
    stored = _json_load(job.prompt_snapshot_json, {}) or {}
    stage_metadata = stored.setdefault("stages", {}).setdefault("generate_answer", {})
    stage_metadata.update(safe_diagnostics)
    stage_metadata["finalGenerationStatus"] = status_value
    stage_metadata["backendFallbackUsed"] = backend_fallback_used
    stored["fullPromptStored"] = False
    job.prompt_snapshot_json = _json_dump(stored)


_JSON_FENCE_PATTERN = re.compile(
    r"\A```[ \t]*(?P<language>json)?[ \t]*\r?\n(?P<body>.*?)(?:\r?\n)?```[ \t]*\Z",
    re.IGNORECASE | re.DOTALL,
)
_UNSUPPORTED_AUDIT_FORMAT_MESSAGE = (
    "AI вернул результат в неподдерживаемом формате. Сохранены только безопасные метаданные аудита."
)


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


def _validation_error_diagnostics(exc: ValidationError) -> dict[str, Any]:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    return {
        "validationErrorsCount": len(errors),
        "validationErrorPaths": [
            ".".join(str(part) for part in item.get("loc") or ())[:300]
            for item in errors[:20]
        ],
        "validationErrorTypes": [str(item.get("type") or "validation_error")[:100] for item in errors[:20]],
    }


def _safe_model_response_parsing(parsing: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(parsing, dict):
        return None
    paths = [str(item)[:300] for item in (parsing.get("validationErrorPaths") or [])[:20]]
    error_types = [str(item)[:100] for item in (parsing.get("validationErrorTypes") or [])[:20]]
    return {
        "status": str(parsing.get("status") or "fallback")[:50],
        "errorCode": str(parsing.get("errorCode") or "")[:100] or None,
        "validationErrorsCount": max(0, int(parsing.get("validationErrorsCount") or 0)),
        "validationErrorPaths": paths,
        "validationErrorTypes": error_types,
        "sourceFormat": str(parsing.get("sourceFormat") or "unknown")[:100],
        "parseOutcome": str(parsing.get("parseOutcome") or "unknown")[:100],
    }


def _safe_provider_token_usage(response: dict[str, Any] | None) -> dict[str, int] | None:
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return None

    def count(*keys: str) -> int:
        for key in keys:
            try:
                return max(0, int(usage.get(key)))
            except (TypeError, ValueError):
                continue
        return 0

    prompt = count("prompt_tokens", "input_tokens")
    completion = count("completion_tokens", "output_tokens")
    total = count("total_tokens") or (prompt + completion)
    return {"prompt": prompt, "completion": completion, "total": total}


def _parse_model_json(answer: str, model_type: Any) -> tuple[Any | None, dict[str, Any]]:
    parsed, source_format = extract_model_json_object(answer)
    metadata: dict[str, Any] = {
        "status": "fallback",
        "requestedResponseMode": "plain_json",
        "actualResponseMode": "plain_json" if source_format == "plain_json" else "json_parser_fallback",
        "parsingSource": source_format,
        "fallbackReason": "provider_structured_output_not_configured",
        "sourceFormat": source_format,
        "parseOutcome": source_format if parsed is not None else "invalid",
        "errorCode": None,
        "validationErrorsCount": 0,
        "validationErrorPaths": [],
        "validationErrorTypes": [],
    }
    if parsed is None:
        metadata["errorCode"] = "json_parse_failed"
        return None, metadata
    try:
        validated = model_type.model_validate(parsed)
    except ValidationError as exc:
        metadata.update(_validation_error_diagnostics(exc))
        metadata["parseOutcome"] = "schema_validation_failed"
        metadata["errorCode"] = "json_schema_validation_failed"
        return None, metadata
    metadata["status"] = "success"
    return validated, metadata


def _reconcile_structured_evidence_claims(
    result: dict[str, Any], snapshot: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconcile only against evidence from the exact trusted campaign/account scope."""

    coverage = snapshot.get("canonicalEvidenceCoverage") or {}
    trusted_names = set((snapshot.get("_trustedCampaignScopes") or {}).keys())
    ambiguous_names = {str(item) for item in (snapshot.get("_ambiguousCampaignNames") or [])}

    def available(item: Any) -> bool:
        return (
            isinstance(item, dict)
            and int(item.get("rowsReceived") or 0) > 0
            and item.get("status") in AVAILABLE_AUDIT_DATA_STATUSES
        )

    def add_aliases(target: dict[str, dict[str, Any]], item: dict[str, Any]) -> None:
        for candidate in capability_candidates(item.get("capabilityId")):
            target[candidate] = item

    campaign_entries: dict[str, dict[str, dict[str, Any]]] = {}
    ambiguous_entries: dict[str, dict[str, dict[str, Any]]] = {}
    for item in coverage.get("campaignScoped") or []:
        if not available(item):
            continue
        campaign = str(item.get("campaignName") or "")
        target = ambiguous_entries if campaign in ambiguous_names else campaign_entries
        if campaign in trusted_names or campaign in ambiguous_names:
            add_aliases(target.setdefault(campaign, {}), item)

    account_collected: dict[str, dict[str, Any]] = {}
    for item in coverage.get("accountWide") or []:
        if available(item):
            add_aliases(account_collected, item)

    any_campaign_coverage: dict[str, dict[str, Any]] = {}
    campaign_coverage_by_capability: dict[str, set[str]] = {}
    for campaign_name, entries in campaign_entries.items():
        for item in entries.values():
            capability = str(item.get("capabilityId") or "")
            if not capability:
                continue
            add_aliases(any_campaign_coverage, item)
            campaign_coverage_by_capability.setdefault(capability, set()).add(campaign_name)

    capability_coverage_counts: dict[str, tuple[int, int]] = {}
    for item in coverage.get("capabilitySummary") or []:
        if not isinstance(item, dict):
            continue
        capability = str(item.get("capabilityId") or "")
        applicable = int(item.get("applicableCampaigns") or 0)
        covered = int(item.get("coveredCampaigns") or 0)
        if capability and applicable > 0:
            capability_coverage_counts[capability] = (covered, applicable)

    complete_account_coverage: dict[str, dict[str, Any]] = {}
    if capability_coverage_counts:
        for capability, (covered, applicable) in capability_coverage_counts.items():
            if covered < applicable:
                continue
            evidence = next((
                any_campaign_coverage.get(candidate)
                for candidate in capability_candidates(capability)
                if any_campaign_coverage.get(candidate)
            ), None)
            if evidence:
                add_aliases(complete_account_coverage, evidence)
    elif trusted_names and not ambiguous_names:
        capabilities = {
            str(item.get("capabilityId") or "")
            for entries in campaign_entries.values()
            for item in entries.values()
            if item.get("capabilityId")
        }
        for capability in capabilities:
            candidates = capability_candidates(capability)
            matched = [
                next((campaign_entries.get(name, {}).get(value) for value in candidates if campaign_entries.get(name, {}).get(value)), None)
                for name in trusted_names
            ]
            if matched and all(matched):
                for candidate in candidates:
                    complete_account_coverage[candidate] = matched[0]
    account_available = {**complete_account_coverage, **account_collected}
    account_claim_available = {**any_campaign_coverage, **account_collected}
    if capability_coverage_counts:
        partial_account_capabilities = {
            capability
            for capability, (covered, applicable) in capability_coverage_counts.items()
            if 0 < covered < applicable
            and not any(candidate in account_collected for candidate in capability_candidates(capability))
        }
    else:
        partial_account_capabilities = {
            capability
            for capability, campaign_names in campaign_coverage_by_capability.items()
            if len(campaign_names) < len(trusted_names)
            and not any(candidate in account_collected for candidate in capability_candidates(capability))
        }

    removed: list[dict[str, str]] = []
    quality_limitations: list[str] = []
    partial_claim_capabilities: set[str] = set()
    text_conflicts = 0
    ambiguous_text_conflicts = 0
    capability_terms = {
        "search_queries": ("search_queries", "search queries", "поисков", "запрос"),
        "placements": ("placements", "placement", "площадк"),
        "devices": ("devices", "device", "устройств"),
        "geo": ("geo", "географ", "регион"),
        "goals": ("goals", "целям", "цели", "конверси"),
        "conversions_by_goal": ("conversions_by_goal", "conversion_data", "конверси"),
        "retargeting_segments": ("retargeting_segments", "retargeting", "ретаргет"),
        "campaign_daily_dynamics": ("campaign_daily_dynamics", "динамик"),
        "ad_group_performance": ("ad_group_performance", "ad_group", "групп объяв"),
        "ad_groups": ("ad_groups", "ad groups", "групп объяв"),
        "keyword_performance": ("keyword_performance", "keyword", "ключев"),
        "keywords": ("keywords", "keyword", "ключев"),
        "campaign_settings": ("campaign_settings", "настройк камп"),
        "audience_targets": ("audience", "аудитор"),
        "audiences": ("audiences", "audience", "аудитор"),
        "ads": ("ads_creatives", "объявлен", "креатив"),
        "demographics": ("demographics", "демограф"),
        "autotargeting": ("autotargeting", "автотаргет"),
    }
    missing_markers = (
        "не собран", "не получен", "нет данных", "данные отсутств", "отсутств", "недоступны данные",
        "missing", "not collected", "no data", "data unavailable",
    )
    public_capability_labels = {
        "campaigns": "кампаниям",
        "campaign_performance": "эффективности кампаний",
        "campaign_daily_dynamics": "динамике кампаний",
        "campaign_settings": "настройкам кампаний",
        "campaign_strategy": "стратегиям кампаний",
        "campaign_status": "статусам кампаний",
        "conversions_by_goal": "конверсиям по выбранным целям",
        "conversion_data": "конверсиям",
        "goals": "целям",
        "search_queries": "поисковым запросам",
        "placements": "площадкам РСЯ",
        "devices": "устройствам",
        "geo": "географии",
        "retargeting_segments": "сегментам ретаргетинга",
        "audience_targets": "аудиторным сегментам",
        "ad_group_performance": "эффективности групп объявлений",
        "ad_groups": "группам объявлений",
        "keyword_performance": "эффективности ключевых фраз",
        "keywords": "ключевым фразам",
        "ads": "объявлениям и креативам",
        "audiences": "аудиторным сегментам",
        "demographics": "демографии",
        "autotargeting": "автотаргетингу",
    }

    def evidence_for_scope(campaign_name: Any, *, account: bool = False) -> dict[str, dict[str, Any]]:
        if account:
            return account_available
        name = str(campaign_name or "").strip()
        return campaign_entries.get(name, {}) if name in trusted_names else {}

    def text_conflict(text: Any, campaign_name: Any = None, *, account: bool = False) -> tuple[bool, bool]:
        normalized = str(text or "").casefold()
        if not normalized or not any(marker in normalized for marker in missing_markers):
            return False, False
        candidates = account_claim_available if account else evidence_for_scope(campaign_name)
        matched_capabilities = {
            str(item.get("capabilityId"))
            for item in candidates.values()
            if item.get("capabilityId")
            and any(
                term in normalized
                for term in capability_terms.get(
                    str(item.get("capabilityId")),
                    (str(item.get("capabilityId")),),
                )
            )
        }
        if account:
            partial_claim_capabilities.update(matched_capabilities & partial_account_capabilities)
        conflict = bool(matched_capabilities)
        name = str(campaign_name or "").strip()
        ambiguous = name in ambiguous_names and any(
            any(term in normalized for term in capability_terms.get(str(item.get("capabilityId")), (str(item.get("capabilityId")),)))
            for item in ambiguous_entries.get(name, {}).values()
        )
        return conflict, ambiguous

    def public_capability_label(value: Any) -> str:
        for candidate in capability_candidates(value):
            if candidate in public_capability_labels:
                return public_capability_labels[candidate]
        return "дополнительному срезу данных"

    def quality_description(evidence: dict[str, Any]) -> str:
        reason = str(evidence.get("qualityReason") or "low_data")
        if reason == "unknown_conversion_metric":
            return "метрика конверсий недоступна или некорректна"
        if reason in {"low_data", "insufficient_data", "no_rows"}:
            return "выборка ограничена"
        return "качество выборки ограничивает вывод"

    def normalize_with_evidence(
        values: Any, campaign_name: Any, *, account: bool = False,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        scoped = evidence_for_scope(campaign_name, account=account)
        kept: list[str] = []
        collected: list[dict[str, Any]] = []
        for raw in values or []:
            capability = str(raw)
            evidence = next((scoped.get(candidate) for candidate in capability_candidates(capability) if scoped.get(candidate)), None)
            if evidence is None:
                kept.append(capability)
                continue
            canonical = str(evidence.get("capabilityId") or capability)
            removed.append({"campaignName": str(campaign_name or "account"), "capabilityId": canonical})
            collected.append(evidence)
            if evidence.get("dataQuality") != "sufficient":
                quality_limitations.append(
                    f"{campaign_name or 'Аккаунт'}: данные по {public_capability_label(canonical)} собраны, "
                    f"но {quality_description(evidence)}."
                )
        unique_collected = {
            str(item.get("capabilityId") or ""): item for item in collected
        }
        return list(dict.fromkeys(kept))[:5], list(unique_collected.values())

    def normalize(values: Any, campaign_name: Any, *, account: bool = False) -> list[str]:
        kept, _ = normalize_with_evidence(values, campaign_name, account=account)
        return kept

    def rebuild_insufficient_data_text(
        remaining: list[str], collected: list[dict[str, Any]],
    ) -> tuple[str, str]:
        sufficient = [
            public_capability_label(item.get("capabilityId"))
            for item in collected if item.get("dataQuality") == "sufficient"
        ]
        limited = [
            (public_capability_label(item.get("capabilityId")), quality_description(item))
            for item in collected if item.get("dataQuality") != "sufficient"
        ]
        missing = list(dict.fromkeys(public_capability_label(item) for item in remaining))
        reason_parts = [f"Данные по {label} собраны." for label in dict.fromkeys(sufficient)]
        reason_parts.extend(
            f"Данные по {label} собраны, но {description}."
            for label, description in dict.fromkeys(limited)
        )
        reason_parts.extend(f"Данные по {label} недоступны или недостаточны." for label in missing)

        recommendation_parts = [
            f"Проверить доступность и синхронизацию данных по {label}." for label in missing
        ]
        collected_labels = list(dict.fromkeys([*sufficient, *(label for label, _ in limited)]))
        if collected_labels:
            recommendation_parts.append(
                "Повторно запрашивать уже собранные данные по "
                f"{', '.join(collected_labels)} не требуется."
            )
        if not recommendation_parts:
            recommendation_parts.append(
                "Учитывать качество и объём уже собранной выборки без повторного запроса тех же данных."
            )
        return " ".join(reason_parts), " ".join(recommendation_parts)

    for section in ("critical_findings", "opportunities"):
        for finding in result.get(section) or []:
            campaign_name = finding.get("campaign_name")
            is_account = not campaign_name and finding.get("analysis_level") == "account"
            before = list(finding.get("next_data_needed") or [])
            finding["next_data_needed"] = normalize(before, campaign_name, account=is_account)
            if before and not finding["next_data_needed"]:
                finding["recommendation"] = (
                    "Использовать уже собранные backend-данные; при недостаточной выборке "
                    "ограничить уверенность вывода, а не запрашивать тот же срез повторно."
                )
            for field in ("problem", "fact", "hypothesis", "recommendation"):
                conflict, ambiguous = text_conflict(finding.get(field), campaign_name, account=is_account)
                ambiguous_text_conflicts += int(ambiguous)
                if conflict:
                    text_conflicts += 1
                    finding[field] = (
                        "Backend подтверждает наличие этого среза данных. "
                        "Ограничения следует описывать через качество и объём выборки."
                    )

    for item in result.get("insufficient_data_campaigns") or []:
        before = list(item.get("next_data_needed") or [])
        campaign_name = item.get("campaign_name")
        remaining, collected = normalize_with_evidence(before, campaign_name)
        item["next_data_needed"] = remaining
        if collected:
            reason, recommendation = rebuild_insufficient_data_text(remaining, collected)
            for field, value in (("reason", reason), ("recommendation", recommendation)):
                if str(item.get(field) or "") != value:
                    text_conflicts += 1
                    item[field] = value
        else:
            for field in ("reason", "recommendation"):
                _, ambiguous = text_conflict(item.get(field), campaign_name)
                ambiguous_text_conflicts += int(ambiguous)

    drilldown = result.get("drilldown_summary") or {}
    globally_analyzed = sorted({
        str(item.get("capabilityId"))
        for item in [*(coverage.get("accountWide") or []), *(coverage.get("campaignScoped") or [])]
        if available(item) and item.get("capabilityId")
    })
    drilldown["analyzed_levels"] = list(dict.fromkeys([
        *(drilldown.get("analyzed_levels") or []), *globally_analyzed,
    ]))
    drilldown["not_analyzed_levels"] = [
        item for item in (drilldown.get("not_analyzed_levels") or [])
        if not any(candidate in account_claim_available for candidate in capability_candidates(item))
    ]
    drilldown["next_data_needed"] = normalize(
        drilldown.get("next_data_needed") or [], None, account=True,
    )
    result["drilldown_summary"] = drilldown

    safe_actions = []
    account_scope_labels = {
        "account", "аккаунт", "весь аккаунт", "all account",
        "все кампании", "all campaigns",
    }
    for action in result.get("action_plan") or []:
        scope = str(action.get("scope") or "").strip()
        is_account = scope.casefold() in account_scope_labels
        conflict, ambiguous = text_conflict(
            " ".join((str(action.get("action") or ""), str(action.get("reason") or ""))),
            scope,
            account=is_account,
        )
        ambiguous_text_conflicts += int(ambiguous)
        if conflict:
            text_conflicts += 1
            continue
        safe_actions.append(action)
    result["action_plan"] = safe_actions

    safe_limitations = []
    for item in result.get("limitations") or []:
        conflict, _ = text_conflict(item, account=True)
        if conflict:
            text_conflicts += 1
            continue
        safe_limitations.append(item)
    result["limitations"] = safe_limitations
    for field in ("executive_summary", "conclusion"):
        conflict, _ = text_conflict(result.get(field), account=True)
        if conflict:
            text_conflicts += 1
            if partial_claim_capabilities:
                labels = list(dict.fromkeys(
                    public_capability_label(capability)
                    for capability in sorted(partial_claim_capabilities)
                ))
                result[field] = (
                    f"Данные по {', '.join(labels)} собраны для части кампаний. "
                    "Непокрытые кампании и ограничения выборки указаны в матрице покрытия."
                )
            else:
                result[field] = (
                    "Результат согласован с фактически собранными account-wide данными; "
                    "оставшиеся ограничения относятся к качеству и объёму выборки."
                )

    def account_coverage_count(capability: str) -> tuple[int, int]:
        return capability_coverage_counts.get(capability, (
            len(campaign_coverage_by_capability.get(capability, set())),
            len(trusted_names),
        ))

    partial_coverage_limitations = [
        (
            f"Данные по {public_capability_label(capability)} собраны для "
            f"{account_coverage_count(capability)[0]} из {account_coverage_count(capability)[1]} кампаний; "
            "для остальных кампаний выводы по этому срезу ограничены."
        )
        for capability in sorted(partial_claim_capabilities)
    ]
    if quality_limitations or partial_coverage_limitations:
        result["limitations"] = list(dict.fromkeys([
            *(result.get("limitations") or []), *quality_limitations, *partial_coverage_limitations,
        ]))
    diagnostics = {
        "status": "final_output_evidence_reconciled" if removed or text_conflicts else "consistent",
        "removedFalseMissingClaims": len(removed),
        "removedFreeTextConflicts": text_conflicts,
        "ambiguousFreeTextConflicts": ambiguous_text_conflicts,
        "requiresBackendFallback": bool(ambiguous_text_conflicts),
        "qualityLimitationsAdded": len(set(quality_limitations)),
        "capabilities": sorted({item["capabilityId"] for item in removed}),
        "accountCapabilities": sorted({str(item.get("capabilityId")) for item in account_collected.values()}),
        "completeAccountCoverage": sorted({str(item.get("capabilityId")) for item in complete_account_coverage.values()}),
        "partialAccountCoverage": sorted(partial_account_capabilities),
    }
    snapshot["finalOutputEvidenceReconciliation"] = diagnostics
    return result, diagnostics


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
        "requestedResponseMode": "plain_json",
        "actualResponseMode": "plain_json" if source_format == "plain_json" else "json_parser_fallback",
        "parsingSource": source_format,
        "fallbackReason": "provider_structured_output_not_configured",
        "sourceFormat": source_format,
        "parseOutcome": source_format if parsed is not None else "invalid",
        "errorCode": None,
        "validationErrorsCount": 0,
        "validationErrorPaths": [],
        "validationErrorTypes": [],
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
        parsing.update(_validation_error_diagnostics(exc))
        recovered, recovery_warnings = _recover_partial_audit_result(parsed)
        if recovered is None:
            parsing["errorCode"] = "truncated_provider_response" if finish_reason == "length" else "json_schema_validation_failed"
            parsing["parseOutcome"] = "schema_validation_failed"
            return None, parsing
        validated = recovered
        parsing["status"] = "partial"
        parsing["parseOutcome"] = "section_validation_recovered"
        parsing["errorCode"] = "partial_schema_validation"
        parsing["sectionWarnings"] = recovery_warnings
        enforced = _enforce_verified_result(validated, snapshot)
        reconciled, diagnostics = _reconcile_structured_evidence_claims(enforced, snapshot)
        parsing["evidenceReconciliation"] = diagnostics
        if diagnostics.get("requiresBackendFallback"):
            parsing["status"] = "fallback"
            parsing["errorCode"] = "final_output_evidence_scope_ambiguous"
            return None, parsing
        return reconciled, parsing
    parsing["status"] = "success"
    parsing["errorCode"] = "truncated_provider_response" if finish_reason == "length" else None
    enforced = _enforce_verified_result(validated, snapshot)
    reconciled, diagnostics = _reconcile_structured_evidence_claims(enforced, snapshot)
    parsing["evidenceReconciliation"] = diagnostics
    if diagnostics.get("requiresBackendFallback"):
        parsing["status"] = "fallback"
        parsing["errorCode"] = "final_output_evidence_scope_ambiguous"
        return None, parsing
    return reconciled, parsing


def _recover_partial_audit_result(parsed: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Keep valid audit sections when one model-generated item is malformed."""

    warnings: list[str] = []
    if not str(parsed.get("conclusion") or "").strip() or not isinstance(parsed.get("data_quality"), dict):
        return None, warnings

    def valid_items(key: str, model: Any, maximum: int) -> list[dict[str, Any]]:
        result = []
        for index, item in enumerate(parsed.get(key) or []):
            try:
                result.append(model.model_validate(item).model_dump(mode="json"))
            except ValidationError:
                warnings.append(f"{key}.{index} исключён после schema validation")
        return result[:maximum]

    executive = str(parsed.get("executive_summary") or "Результат восстановлен частично; проверьте ограничения.")[:4000]
    conclusion = str(parsed.get("conclusion") or "Доступна только валидная часть аудита.")[:4000]
    try:
        data_quality = AiAuditDataQuality.model_validate(parsed.get("data_quality") or {}).model_dump(mode="json")
    except ValidationError:
        data_quality = AiAuditDataQuality(
            status="partial", limitations=["Раздел качества данных модели не прошёл проверку."],
        ).model_dump(mode="json")
        warnings.append("data_quality восстановлен безопасным fallback")
    try:
        drilldown = AiAuditDrilldownSummary.model_validate(parsed.get("drilldown_summary") or {}).model_dump(mode="json")
    except ValidationError:
        drilldown = AiAuditDrilldownSummary().model_dump(mode="json")
        warnings.append("drilldown_summary восстановлен безопасным fallback")
    candidate = {
        "meta": parsed.get("meta") or {},
        "executive_summary": executive,
        "data_quality": data_quality,
        "critical_findings": valid_items("critical_findings", AiAuditFinding, 5),
        "opportunities": valid_items("opportunities", AiAuditFinding, 5),
        "insufficient_data_campaigns": valid_items(
            "insufficient_data_campaigns", AiAuditInsufficientDataCampaign, 100,
        ),
        "tracking_and_goals": parsed.get("tracking_and_goals") if isinstance(parsed.get("tracking_and_goals"), dict) else {},
        "drilldown_summary": drilldown,
        "action_plan": valid_items("action_plan", AiAuditAction, 10),
        "prohibited_actions": [str(item)[:1000] for item in (parsed.get("prohibited_actions") or []) if isinstance(item, str)],
        "limitations": [str(item)[:1000] for item in (parsed.get("limitations") or []) if isinstance(item, str)] + warnings,
        "conclusion": conclusion,
    }
    try:
        return AiAuditResult.model_validate(candidate).model_dump(mode="json"), warnings
    except ValidationError:
        return None, warnings


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


READ_ONLY_AUDIT_ACTIONS = frozenset({
    "inspect_data", "validate_tracking", "collect_more_data", "compare_periods", "monitor",
    "manual_review", "prepare_dry_run", "review_search_queries", "review_campaign_settings",
})
MODIFYING_AUDIT_ACTIONS = frozenset({
    "budget_reallocation", "budget_increase", "budget_decrease", "pause_campaign",
    "disable_campaign", "change_strategy", "change_bid", "add_negative_keyword",
    "exclude_placement", "disable_keyword", "change_targeting", "scale_campaign", "tracking_fix",
})
_READ_ONLY_ACTION_MARKERS = (
    "inspect", "review", "validate", "collect", "compare", "monitor", "dry run", "dry_run",
    "провер", "проанализ", "собрать", "сравнить", "монитор", "ручн", "подготовить",
)
_MODIFYING_ACTION_MARKERS = (
    "reallocat", "increase budget", "decrease budget", "raise budget", "pause", "disable",
    "change strategy", "change bid", "add negative", "exclude placement", "change targeting", "scale campaign",
    "перераспредел", "увеличить бюджет", "снизить бюджет", "приостанов", "отключ",
    "изменить стратег", "изменить став", "добавить минус", "исключить площад", "изменить таргет", "масштаб",
)


def _audit_action_safety_class(action_value: Any) -> str:
    text = str(action_value or "").strip().lower()
    semantic_code = re.sub(r"[^a-z0-9а-яё]+", "_", text).strip("_")
    if semantic_code in READ_ONLY_AUDIT_ACTIONS:
        return "read_only"
    if semantic_code in MODIFYING_AUDIT_ACTIONS:
        return "modifying"
    if any(marker in text for marker in _MODIFYING_ACTION_MARKERS):
        return "modifying"
    if any(marker in text for marker in _READ_ONLY_ACTION_MARKERS):
        return "read_only"
    return "unknown"


def _append_safety_warning(result: dict[str, Any], code: str, message: str) -> None:
    warning = f"{code}: {message}"
    limitations = result.setdefault("limitations", [])
    if warning not in limitations:
        limitations.append(warning)


def _safe_manual_action(action: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **action,
        "hypothesis_id": None,
        "action": "Собрать дополнительные данные и провести ручную проверку.",
        "reason": reason,
        "mode": "manual_review",
        "requires_human_approval": True,
    }


def _trusted_tracking_and_goals(snapshot: dict[str, Any]) -> dict[str, Any]:
    selected = snapshot.get("selectedGoals") if isinstance(snapshot.get("selectedGoals"), dict) else {}
    tracking = snapshot.get("trackingStatus") if isinstance(snapshot.get("trackingStatus"), dict) else {}
    diagnostics = tracking.get("syncDiagnostics") if isinstance(tracking.get("syncDiagnostics"), dict) else {}
    warnings = [str(item)[:500] for item in (tracking.get("warnings") or [])[:10]]
    goal_ids = [str(item) for item in (selected.get("ids") or [])[:20]]
    has_goal_data = bool(selected.get("hasGoalData"))
    return {
        "status": "partial" if goal_ids or has_goal_data else "unverified",
        "selected_goal_ids": goal_ids,
        "has_goal_data": has_goal_data,
        "goal_conversions": _number((snapshot.get("accountTotals") or {}).get("goalConversions")),
        "sync_status": diagnostics.get("dataQualityLevel") or diagnostics.get("status") or "unverified",
        "warnings": warnings,
        "limitations": [] if has_goal_data else ["Данные по выбранным целям не подтверждены trusted backend context."],
    }


def _enforce_verified_result(result: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    verification = _verification_registry(snapshot)
    for key in ("critical_findings", "opportunities"):
        for finding in result.get(key) or []:
            hypothesis_id = finding.get("hypothesis_id")
            verified = verification.get(hypothesis_id) if hypothesis_id else None
            status_value = str((verified or {}).get("status") or "unverified")
            if finding.get("hypothesis") and not hypothesis_id:
                _append_safety_warning(
                    result,
                    "missing_hypothesis_id",
                    f"Гипотеза для «{finding.get('campaign_name') or 'Аккаунт'}» оставлена неподтверждённой.",
                )
                finding["next_data_needed"] = list(dict.fromkeys(
                    [*(finding.get("next_data_needed") or []), "hypothesis_id и проверка гипотезы"]
                ))[:5]
            finding["verification_status"] = status_value
            if status_value in {"rejected", "not_applicable"}:
                finding["hypothesis"] = None
                finding["recommendation"] = "Не выполнять действие по отклонённой или неприменимой гипотезе."
            elif status_value == "unverified":
                remaining = (verified or {}).get("remaining_data_needed") or finding.get("next_data_needed") or []
                finding["hypothesis"] = f"Неподтверждённая гипотеза: {finding.get('hypothesis') or 'причина не установлена'}"
                finding["recommendation"] = "Собрать недостающие данные: " + (", ".join(remaining) if remaining else "проверить гипотезу вручную")
            if _audit_action_safety_class(finding.get("recommendation")) == "modifying" and status_value not in {
                "confirmed", "partially_confirmed",
            }:
                finding["recommendation"] = "Собрать недостающие данные и проверить вывод вручную до любых изменений."
                _append_safety_warning(
                    result,
                    "unverified_modifying_recommendation",
                    "Изменяющая рекомендация заменена безопасной ручной проверкой.",
                )
            finding["requires_human_approval"] = True
    safe_actions = []
    for action in result.get("action_plan") or []:
        hypothesis_id = action.get("hypothesis_id")
        status_value = str((verification.get(hypothesis_id) or {}).get("status") or "unverified")
        safety_class = _audit_action_safety_class(action.get("action"))
        if status_value in {"rejected", "not_applicable"}:
            continue
        modifying_is_verified = (
            safety_class == "modifying"
            and bool(hypothesis_id)
            and status_value in {"confirmed", "partially_confirmed"}
            and action.get("mode") in {"manual_review", "dry_run"}
            and action.get("requires_human_approval") is True
        )
        if safety_class == "modifying" and not modifying_is_verified:
            action = _safe_manual_action(action, "Изменяющее действие не связано с подтверждённой гипотезой.")
            _append_safety_warning(
                result,
                "unsafe_modifying_action_downgraded",
                "Изменяющее действие заменено сбором данных и ручной проверкой.",
            )
        elif safety_class == "unknown" and (not hypothesis_id or status_value not in {"confirmed", "partially_confirmed"}):
            action = _safe_manual_action(action, "Неизвестный тип действия требует подтверждённой гипотезы.")
            _append_safety_warning(
                result,
                "unknown_action_downgraded",
                "Неизвестное действие заменено безопасной ручной проверкой.",
            )
        elif status_value == "unverified" and hypothesis_id:
            action = _safe_manual_action(action, "Причина не подтверждена собранными данными.")
        action["requires_human_approval"] = True
        safe_actions.append(action)
    result["action_plan"] = safe_actions[:10]
    # The primary campaign table is always rebuilt from trusted backend facts.
    # Model prose cannot remove, rename or overstate these conclusions.
    result["campaign_insights"] = build_campaign_insights(snapshot)
    result["tracking_and_goals"] = _trusted_tracking_and_goals(snapshot)
    return result


def build_backend_fallback_audit_result(
    snapshot: dict[str, Any],
    job: AiAuditJob,
    *,
    reason_code: str = "final_prompt_too_large",
) -> dict[str, Any]:
    """Build a safe result from already verified backend evidence without an LLM call."""

    projection = build_final_audit_projection(snapshot, compaction_level=3)
    findings: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for item in projection.get("verificationRegistry") or []:
        status_value = str(item.get("verificationStatus") or "unverified")
        campaign_name = str(item.get("campaignName") or "Аккаунт")
        evidence = _bounded_strings(item.get("supportingEvidence"), 3)
        if not evidence:
            evidence = _bounded_strings([item.get("factSummary")], 1)
        if status_value in {"confirmed", "partially_confirmed"} and len(findings) < 5:
            hypothesis_id = str(item.get("hypothesisId") or "") or None
            findings.append({
                "hypothesis_id": hypothesis_id,
                "verification_status": status_value,
                "campaign_name": campaign_name,
                "campaign_type": item.get("campaignType") or "unknown",
                "analysis_level": "campaign",
                "problem": "Backend-проверка обнаружила сигнал, требующий внимания.",
                "fact": str(item.get("factSummary") or "Факт подтверждён собранными данными."),
                "evidence": evidence,
                "hypothesis": "Причина подтверждена полностью или частично backend-проверкой.",
                "confidence": "high" if status_value == "confirmed" else "medium",
                "risk": "medium",
                "recommendation": "Проверить доказательства и подготовить решение в ручном режиме.",
                "requires_human_approval": True,
                "next_data_needed": _bounded_strings(item.get("remainingDataNeeded"), 5),
            })
            actions.append({
                "priority": len(actions) + 1,
                "hypothesis_id": hypothesis_id,
                "action": "Провести ручную проверку подтверждённого сигнала.",
                "scope": campaign_name,
                "reason": str(item.get("factSummary") or "Сигнал подтверждён backend-проверкой."),
                "mode": "manual_review",
                "requires_human_approval": True,
            })
        elif status_value == "unverified":
            insufficient.append({
                "campaign_name": campaign_name,
                "reason": "Гипотеза не подтверждена собранными данными.",
                "recommendation": "Собрать недостающие данные и повторить проверку без изменений в Директе.",
                "next_data_needed": _bounded_strings(item.get("remainingDataNeeded"), 5),
            })

    policy_coverage = public_evidence_coverage(snapshot)
    completion_state = str(policy_coverage.get("completionState") or "complete")
    incomplete_requirements = [
        item
        for item in policy_coverage.get("requirements") or []
        if item.get("status") in {"partial", "blocked", "missing", "processing"}
    ]
    if completion_state == "blocked_missing_evidence":
        findings = []
        actions = []
        for item in incomplete_requirements[:25]:
            insufficient.append({
                "campaign_name": str(item.get("campaignName") or "Аккаунт"),
                "reason": (
                    "Не собран обязательный срез данных "
                    f"«{item.get('dimension') or 'unknown'}» для сигнала «{item.get('signal') or 'unknown'}»."
                ),
                "recommendation": "Проверить доступность read-only данных и повторить аудит.",
                "next_data_needed": [str(item.get("dimension") or "unknown")],
            })

    totals = projection.get("accountTotals") or {}
    raw_goal_conversions = (
        totals.get("goalConversions")
        if "goalConversions" in totals
        else totals.get("goal_conversions")
    )
    goal_metric = parse_numeric_metric(raw_goal_conversions)
    goal_conversions_label = (
        f"{goal_metric.value:g}" if goal_metric.state == "known" and goal_metric.value is not None
        else "недоступны"
    )
    cost_metric = parse_numeric_metric(totals.get("cost"))
    cost_label = (
        f"{cost_metric.value:g}" if cost_metric.state == "known" and cost_metric.value is not None
        else "недоступен"
    )
    data_facts = [
        f"Проанализировано кампаний: {(projection.get('campaignClassificationSummary') or {}).get('total') or 0}.",
        f"Расход в доступном периоде: {cost_label}.",
        f"Конверсии по выбранным целям: {goal_conversions_label}.",
    ]
    limitations = list(projection.get("limitations") or [])
    if completion_state == "partial_coverage":
        limitations.append(
            "Часть обязательных срезов доступна не полностью; причинные выводы по ним ограничены."
        )
    elif completion_state == "blocked_missing_evidence":
        limitations.append(
            "Обязательные данные собраны не полностью; полный причинный аудит и план действий не сформированы."
        )
    if reason_code == PROVIDER_CONTEXT_OVERFLOW_CODE:
        fallback_limitation = (
            "Провайдер отклонил фактический размер контекста; расширенный AI-отчёт заменён "
            "безопасным backend-результатом."
        )
        executive_summary = (
            "Аудит завершён по собранным read-only данным. Провайдер отклонил финальный контекст, "
            "поэтому расширенный AI-текст заменён безопасным backend-результатом."
        )
    elif reason_code == "final_prompt_too_large":
        fallback_limitation = "Расширенный AI-отчёт не сформирован из-за размера финального контекста."
        executive_summary = (
            "Аудит завершён по собранным read-only данным. Финальный AI-запрос не отправлялся: "
            "контекст не поместился в безопасный бюджет выбранной модели."
        )
    elif reason_code == FINAL_PROVIDER_TIMEOUT_WARNING_CODE:
        fallback_limitation = (
            "Финальная модель не завершила ответ за отведённое время; расширенный AI-текст заменён "
            "безопасным backend-результатом по уже собранным данным."
        )
        executive_summary = (
            "Аудит завершён по собранным и проверенным read-only данным. Финальная модель не успела "
            "оформить ответ, поэтому показан безопасный backend-результат."
        )
    elif reason_code == "final_stage_stale":
        fallback_limitation = (
            "Финальный этап был прерван после сбора данных; аудит восстановлен безопасным "
            "backend-результатом без повторных запросов к Яндекс.Директу."
        )
        executive_summary = (
            "Аудит завершён по сохранённым read-only данным после восстановления прерванного "
            "финального этапа."
        )
    elif reason_code == "json_schema_validation_failed":
        fallback_limitation = (
            "Ответ модели не прошёл структурный контракт AiAuditResult; показан безопасный "
            "backend-отчёт по уже собранным данным."
        )
        executive_summary = (
            "Аудит завершён по собранным и проверенным read-only данным. Ответ модели не прошёл "
            "структурный контракт, поэтому показан безопасный backend-результат."
        )
    else:
        fallback_limitation = (
            "Ответ модели не удалось безопасно разобрать; показан backend-отчёт по уже собранным данным."
        )
        executive_summary = (
            "Аудит завершён по собранным и проверенным read-only данным. Ответ модели не удалось "
            "безопасно разобрать, поэтому показан backend-результат."
        )
    if completion_state == "blocked_missing_evidence":
        executive_summary = (
            "Аудит завершён с неполным покрытием обязательных данных. Доступные факты сохранены, "
            "но уверенные причинные выводы и план действий не сформированы."
        )
    if fallback_limitation not in limitations:
        limitations.append(fallback_limitation)
    candidate = {
        "meta": _trusted_result_meta(snapshot, job, {"model": job.model}),
        "executive_summary": executive_summary,
        "data_quality": {
            "status": "partial",
            "facts": data_facts,
            "limitations": limitations[:10],
        },
        "critical_findings": findings,
        "opportunities": [],
        "insufficient_data_campaigns": insufficient[:25],
        "tracking_and_goals": _trusted_tracking_and_goals(snapshot),
        "drilldown_summary": {
            "analyzed_levels": sorted({
                str(item.get("capabilityId"))
                for hypothesis in projection.get("verificationRegistry") or []
                for item in hypothesis.get("evidenceSummary") or []
                if item.get("capabilityId")
            }),
            "not_analyzed_levels": [],
            "next_data_needed": list(dict.fromkeys(
                value
                for hypothesis in projection.get("verificationRegistry") or []
                for value in (hypothesis.get("remainingDataNeeded") or [])
            ))[:20],
        },
        "action_plan": actions[:10],
        "prohibited_actions": [
            "Не применять изменения в Яндекс.Директе автоматически.",
            "Не изменять бюджеты, ставки и статусы кампаний без явного подтверждения пользователя.",
        ],
        "limitations": limitations,
        "conclusion": (
            "Для полного вывода нужно собрать перечисленные обязательные данные."
            if completion_state == "blocked_missing_evidence"
            else "Доступен безопасный backend-результат по уже собранным и проверенным данным."
        ),
    }
    validated = AiAuditResult.model_validate(candidate).model_dump(mode="json")
    return _enforce_verified_result(validated, snapshot)


def _complete_backend_fallback_stage(
    db: Session,
    job: AiAuditJob,
    snapshot: dict[str, Any],
    diagnostics: dict[str, Any],
    timings: dict[str, Any],
    *,
    reason_code: str,
    final_status: str,
    warning: str,
    model_response_parsing: dict[str, Any] | None = None,
    provider_response_metadata: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    final_token_usage: dict[str, int] | None = None,
    preserve_job_error: bool = True,
    provider_error_code: str | None = None,
    warning_code: str | None = None,
    warning_retryable: bool = False,
    complete_immediately: bool = False,
) -> AiAuditJob:
    if warning_code:
        _append_audit_warning(
            snapshot,
            stage="generate_answer",
            code=warning_code,
            message=warning,
            retryable=warning_retryable,
        )
    if provider_error_code:
        diagnostics["providerErrorCode"] = provider_error_code
    structured = build_backend_fallback_audit_result(snapshot, job, reason_code=reason_code)
    evidence_coverage = public_evidence_coverage(snapshot)
    warnings = _helper_warning_messages(snapshot)
    if warning not in warnings:
        warnings.append(warning)
    _record_final_generation_diagnostics(
        snapshot,
        job,
        diagnostics,
        status_value=final_status,
        backend_fallback_used=True,
    )
    mark_scheduler_progress(snapshot, action=final_status, successful=True)
    job.context_snapshot_json = _json_dump(snapshot)
    job.answer_text = build_audit_answer_markdown(structured, snapshot)
    job.result_json = _json_dump({
        "structured": structured,
        "fallbackMarkdown": None,
        "technicalResponse": None,
        "structuredParsing": {
            "status": "success",
            "requestedResponseMode": "backend_generated",
            "actualResponseMode": "backend_generated",
            "parsingSource": "backend_generated",
            "fallbackReason": reason_code,
            "sourceFormat": "backend_generated",
            "parseOutcome": "backend_generated",
            "errorCode": reason_code,
            "validationErrorsCount": 0,
            "validationErrorPaths": [],
            "validationErrorTypes": [],
        },
        "modelResponseParsing": _safe_model_response_parsing(model_response_parsing),
        "providerResponseMetadata": provider_response_metadata,
        "warnings": warnings,
        "finishReason": finish_reason,
        "truncated": False,
        "compactRetryAvailable": False,
        "backendFallbackUsed": True,
        "providerErrorCode": provider_error_code,
        "finalWarning": (
            {
                "stage": "generate_answer",
                "code": warning_code,
                "message": warning,
                "retryable": warning_retryable,
            }
            if warning_code
            else None
        ),
        "completeness": (
            evidence_coverage["completionState"]
            if (
                snapshot.get("evidenceCoverageRegistry")
                or evidence_coverage["completionState"] == "partial_coverage"
            )
            else "backend_fallback"
        ),
        "auditCompletionState": evidence_coverage["completionState"],
        "evidenceCoverage": evidence_coverage,
        "analysisPeriod": snapshot.get("analysisPeriod") or {},
        "cachePolicy": (snapshot.get("metadata") or {}).get("cachePolicy") or "fresh",
        "directApiKnowledgeVersion": (snapshot.get("metadata") or {}).get("directApiKnowledgeVersion"),
        "dataCoverage": snapshot.get("dataCoverage") or {},
        "usage": final_token_usage,
        "finalTokenUsage": final_token_usage,
        "responseId": None,
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
    job.error_code = reason_code if preserve_job_error else None
    job.error_message = warning if preserve_job_error else None
    job.retryable = warning_retryable
    job.status = "completed" if complete_immediately else "context_ready"
    job.current_stage = "finalize"
    job.stage_attempt = 0
    job.progress_percent = 100 if complete_immediately else 95
    if complete_immediately:
        job.completed_at = _now()
        timings["finalizeMs"] = 0
    _complete_provider_stage(job, "generate_answer")
    timings["totalElapsedMs"] = max(
        0,
        round(
            (_now() - _as_aware(job.started_at or job.created_at or _now())).total_seconds()
            * 1000
        ),
    )
    job.timings_json = _json_dump(timings)
    job.stage_version += 1
    db.commit()
    db.refresh(job)
    _log_timing(job, "generate_answer")
    return job


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
        "maxInvestigationRounds": MAX_INVESTIGATION_ROUNDS,
        "requestsCount": 0,
        "providerCallsCount": 0,
        "helperProviderCallsCount": 0,
        "finalProviderCallsCount": 0,
        "helperFallbacksCount": 0,
        "plannerPromptTokensEstimated": 0,
        "verificationPromptTokensEstimated": 0,
        "savedDataRequestsCount": 0,
        "directApiCallsCount": 0,
        "liveRequestCount": 0,
        "liveCompletedCount": 0,
        "processingReportCount": 0,
        "cacheHitCount": 0,
        "liveAttempts": 0,
        "liveSucceeded": 0,
        "liveProcessing": 0,
        "liveFailed": 0,
        "cacheHits": 0,
        "savedFallbacks": 0,
        "liveFailureReasons": {},
        "unavailableCapabilities": [],
        "policyVersion": AUDIT_EVIDENCE_POLICY_VERSION,
        "signalsDetected": 0,
        "mandatoryRequirementsCount": 0,
        "policyRequestsAdded": 0,
        "aiRequestsAdded": 0,
        "duplicateRequestsRemoved": 0,
        "forbiddenRequestsRejected": 0,
        "requirementsSatisfied": 0,
        "requirementsPartial": 0,
        "requirementsBlocked": 0,
        "completionState": "complete",
        "completionGateRuns": 0,
        "executionProfile": "full_account",
        "softTargetAt": None,
        "hardDeadlineAt": None,
        "collectionDeadlineAt": None,
        "finalizationReserveSeconds": 120,
        "requestSafetyLimit": 128,
        "maxDepthRounds": MAX_INVESTIGATION_ROUNDS,
        "schedulerPhase": "breadth",
        "lastProgressAt": None,
        "lastSuccessfulActionAt": None,
        "lastAction": None,
        "nextRetryAt": None,
        "waitingReason": None,
        "recoveryStatus": "idle",
        "campaignsTotal": 0,
        "campaignsCovered": 0,
        "breadthRequestsTotal": 0,
        "breadthRequestsCompleted": 0,
        "depthRequestsTotal": 0,
        "tokenUsage": {"prompt": 0, "completion": 0, "total": 0},
    }
    runtime = snapshot.setdefault("auditRuntime", {})
    for key, value in defaults.items():
        runtime.setdefault(key, value.copy() if isinstance(value, dict) else value)
    return runtime


def _sync_policy_runtime(snapshot: dict[str, Any], coverage: dict[str, Any] | None = None) -> dict[str, Any]:
    coverage = coverage or evaluate_audit_evidence_coverage(snapshot)
    diagnostics = snapshot.get("evidencePolicyDiagnostics") or {}
    runtime = _audit_runtime(snapshot)
    runtime.update({
        "policyVersion": AUDIT_EVIDENCE_POLICY_VERSION,
        "signalsDetected": len(snapshot.get("signalsDetected") or []),
        "mandatoryRequirementsCount": int(coverage.get("requiredTotal") or 0),
        "policyRequestsAdded": int(diagnostics.get("policyRequestsAdded") or 0),
        "aiRequestsAdded": int(diagnostics.get("aiRequestsAdded") or 0),
        "duplicateRequestsRemoved": int(diagnostics.get("duplicateRequestsRemoved") or 0),
        "forbiddenRequestsRejected": int(diagnostics.get("forbiddenRequestsRejected") or 0),
        "requirementsSatisfied": int(coverage.get("satisfied") or 0),
        "requirementsPartial": int(coverage.get("partial") or 0),
        "requirementsBlocked": int(coverage.get("blocked") or 0) + int(coverage.get("missing") or 0),
        "completionState": str(coverage.get("completionState") or "complete"),
    })
    return runtime


def _audit_execution_profile(job: AiAuditJob, snapshot: dict[str, Any]):
    runtime = _audit_runtime(snapshot)
    profile_id = str(runtime.get("executionProfile") or "")
    return execution_profile_for_scope(profile_id or job.requested_scope)


def _minimum_coverage_plan(
    requests: list[AuditDataRequest], snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    plan = [
        {
            "campaignName": item.campaign_name,
            "capabilityId": item.capability_id or item.dimension,
            "applicable": True,
        }
        for item in requests
    ]
    for classification in (snapshot or {}).get("campaignClassifications") or []:
        campaign_name = str(classification.get("campaign_name") or "")
        if not campaign_name:
            continue
        plan.extend([
            {"campaignName": campaign_name, "capabilityId": "campaign_settings", "applicable": True},
            {"campaignName": campaign_name, "capabilityId": "campaign_performance", "applicable": True},
        ])
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in plan:
        unique[(str(item["campaignName"]), str(item["capabilityId"]))] = item
    return list(unique.values())


def _request_key(item: AuditDataRequest) -> tuple[str, str]:
    return item.campaign_name, str(item.capability_id or item.dimension)


def _deduplicate_requests(requests: list[AuditDataRequest]) -> list[AuditDataRequest]:
    result: list[AuditDataRequest] = []
    seen: set[tuple[str, str]] = set()
    for item in requests:
        key = _request_key(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _pending_report_wait(db: Session, job: AiAuditJob) -> tuple[str | None, datetime | None]:
    report_jobs = list(db.scalars(select(DirectReportJob).where(
        DirectReportJob.audit_job_id == job.id,
        DirectReportJob.client_id == job.client_id,
        DirectReportJob.status.in_(("queued", "requested", "processing", "waiting_for_report_queue")),
    )))
    retry_values = [_as_aware(item.next_retry_at) for item in report_jobs if item.next_retry_at]
    next_retry = min(retry_values) if retry_values else None
    if any(item.status == "waiting_for_report_queue" for item in report_jobs):
        return "direct_report_queue", next_retry
    if any(item.status in {"queued", "requested", "processing"} for item in report_jobs):
        return "offline_report_processing", next_retry
    return None, next_retry


def _refresh_scheduler_coverage(snapshot: dict[str, Any], full_results: list[dict[str, Any]]) -> None:
    index = build_canonical_evidence_index(snapshot, full_results)
    projection = canonical_coverage_projection(index, snapshot)
    snapshot["canonicalEvidenceCoverage"] = projection
    runtime = _audit_runtime(snapshot)
    summary = projection.get("summary") or {}
    runtime["campaignsTotal"] = int(summary.get("applicableCampaigns") or 0)
    runtime["campaignsCovered"] = int(summary.get("coveredCampaigns") or 0)
    breadth_keys = {
        (str(item.get("campaignName") or ""), str(item.get("capabilityId") or ""))
        for item in snapshot.get("minimumCoveragePlan") or []
        if isinstance(item, dict)
    }
    completed = {
        (str(item.get("campaignName") or ""), str(item.get("capabilityId") or ""))
        for item in projection.get("campaignMatrix") or []
        if item.get("status") in {
            "collected", "partial", "insufficient_data", "not_applicable", "unavailable", "failed",
        }
    }
    runtime["breadthRequestsTotal"] = len(breadth_keys)
    runtime["breadthRequestsCompleted"] = len(breadth_keys & completed)


def _deadline_skip_results(requests: list[AuditDataRequest]) -> list[dict[str, Any]]:
    return [AuditDataRequestResult(
        request_id=item.request_id,
        hypothesis_id=item.hypothesis_id,
        capability_id=item.capability_id or item.dimension,
        dimension=item.dimension,
        campaign_name=item.campaign_name,
        status="skipped_budget_limit",
        source="backend_scheduler",
        summary="Временной бюджет сбора данных завершён; аудит продолжен с частичным покрытием.",
        error_code="audit_collection_deadline_reached",
    ).model_dump(mode="json") for item in requests]


def _finish_collection_for_deadline(
    db: Session,
    job: AiAuditJob,
    snapshot: dict[str, Any],
    requests: list[AuditDataRequest],
    *,
    reason: str,
) -> None:
    skipped = _deadline_skip_results(_deduplicate_requests(requests))
    full_results = _merge_full_drilldown_results(
        _load_full_drilldown_results(db, job), skipped,
    )
    _save_full_drilldown_results(db, job, full_results)
    _refresh_drilldown_projections(snapshot, full_results)
    evidence_results = _load_full_evidence_results(db, job)
    refresh_evidence_coverage_registry(snapshot, evidence_results)
    _refresh_scheduler_coverage(snapshot, evidence_results)
    snapshot["pendingDataRequests"] = []
    snapshot["processingDataRequests"] = []
    snapshot["deferredDepthDataRequests"] = []
    runtime = _audit_runtime(snapshot)
    runtime["schedulerPhase"] = "finalization"
    runtime["stopReason"] = reason
    runtime["deadlineReached"] = True
    mark_scheduler_progress(snapshot, action=reason)
    job.context_snapshot_json = _json_dump(snapshot)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.stage_attempt = 0
    job.progress_percent = 78


def _activate_deferred_depth(snapshot: dict[str, Any]) -> bool:
    deferred = [
        AuditDataRequest.model_validate(item)
        for item in snapshot.pop("deferredDepthDataRequests", [])
    ]
    if not deferred:
        return False
    snapshot["pendingDataRequests"] = [item.model_dump(mode="json") for item in deferred]
    snapshot["processingDataRequests"] = []
    runtime = _audit_runtime(snapshot)
    runtime["schedulerPhase"] = "depth"
    mark_scheduler_progress(snapshot, action="breadth_coverage_completed", successful=True)
    return True


def _policy_rejection_result(item: dict[str, Any]) -> dict[str, Any]:
    return AuditDataRequestResult(
        request_id=f"policy_rejected_{uuid.uuid4().hex[:12]}",
        hypothesis_id="policy_validation",
        capability_id=str(item.get("dimension") or "") or None,
        dimension=str(item.get("dimension") or "policy_validation"),
        campaign_name=str(item.get("campaignName") or "") or None,
        status="not_applicable",
        source="backend_evidence_policy",
        summary="Запрос отклонён deterministic evidence policy.",
        error_code=str(item.get("reasonCode") or "forbidden_dimension_for_campaign_subtype"),
    ).model_dump(mode="json")


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
        "next_round_planner": {"model": AI_AUDIT_HELPER_MODEL, "status": "pending", "warningCode": None},
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
        "next_round_planner_returned_model": None,
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
    parsing: dict[str, Any] | None = None,
) -> None:
    helper_stage = _helper_stages(snapshot).setdefault(stage_name, {})
    helper_stage.update({
        "model": AI_AUDIT_HELPER_MODEL,
        "status": status_value,
        "warningCode": warning_code,
    })
    if returned_model:
        helper_stage["returnedModel"] = returned_model
    if parsing is not None:
        helper_stage["parsing"] = parsing


def _helper_warning(stage: str, code: str, message: str) -> dict[str, Any]:
    return {"stage": stage, "code": code, "message": message, "retryable": False}


def _append_audit_warning(
    snapshot: dict[str, Any],
    *,
    stage: str,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    warnings = snapshot.setdefault("auditWarnings", [])
    if not any(item.get("code") == code for item in warnings if isinstance(item, dict)):
        warnings.append({"stage": stage, "code": code, "message": message, "retryable": retryable})


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
    parsing: dict[str, Any] | None = None,
) -> None:
    warnings = snapshot.setdefault("auditWarnings", [])
    if not any(item.get("code") == code for item in warnings if isinstance(item, dict)):
        warnings.append(_helper_warning(stage, code, message))
    runtime = _audit_runtime(snapshot)
    runtime["helperFallbacksCount"] = int(runtime.get("helperFallbacksCount") or 0) + 1
    _set_helper_stage(
        snapshot,
        stage_name,
        status_value="fallback",
        warning_code=code,
        parsing=parsing,
    )
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


_AI_SAMPLE_PRIVATE_KEYS = {
    "request_hash", "campaign_id", "campaignid", "ad_group_id", "adgroupid",
    "criterion_id", "criterionid", "organization_id", "client_id", "job_id",
    "authorization", "client-login", "access_token", "refresh_token",
}


def _safe_ai_sample(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe_ai_sample(item)
            for key, item in value.items()
            if str(key).lower() not in _AI_SAMPLE_PRIVATE_KEYS
        }
    if isinstance(value, list):
        return [_safe_ai_sample(item) for item in value]
    return value


def _cap_drilldown_results(results: list[dict[str, Any]], token_target: int = DRILLDOWN_TOKEN_TARGET) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    used = 0
    for original in results:
        item = _safe_ai_sample(dict(original))
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
        item["ai_sample_rows"] = len(included)
        if len(included) < len(rows):
            item["limitations"] = list(item.get("limitations") or []) + [f"В AI-контекст включено {len(included)} из {len(rows)} строк."]
        compact.append(item)
    return compact


def _merge_full_drilldown_results(
    existing: list[dict[str, Any]],
    collected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in existing + collected:
        request_id = str(item.get("request_id") or "")
        key = request_id or f"anonymous-{len(order)}"
        if key not in merged:
            order.append(key)
        merged[key] = dict(item)
    return [merged[key] for key in order]


def _load_full_drilldown_results(db: Session, job: AiAuditJob) -> list[dict[str, Any]]:
    return load_audit_evidence_results(db, job, evidence_kind="drilldown")


def _save_full_drilldown_results(db: Session, job: AiAuditJob, results: list[dict[str, Any]]) -> None:
    save_audit_evidence_results(db, job, evidence_kind="drilldown", results=results)
    stored = _json_load(job.prompt_snapshot_json, {}) or {}
    stored.pop("privateExecution", None)
    stored["evidenceStorage"] = {
        "kind": "persistent_reference",
        "resultsCount": len(results),
        "rowsCount": sum(len(item.get("data") or []) for item in results),
    }
    stored["fullPromptStored"] = False
    job.prompt_snapshot_json = _json_dump(stored)


def _load_full_baseline_results(db: Session, job: AiAuditJob) -> list[dict[str, Any]]:
    return load_audit_evidence_results(db, job, evidence_kind="baseline")


def _load_full_evidence_results(db: Session, job: AiAuditJob) -> list[dict[str, Any]]:
    """Return all persisted read-only evidence, including the fresh baseline.

    Baseline campaign and performance rows are account-wide requests, but they
    are canonically derived into campaign-scoped evidence after campaign IDs
    are trusted.  Dropping them when drilldown evidence is refreshed makes the
    coverage matrix report zero covered campaigns despite collected live data.
    """
    return _merge_full_drilldown_results(
        _load_full_baseline_results(db, job),
        _load_full_drilldown_results(db, job),
    )


def _save_full_baseline_results(db: Session, job: AiAuditJob, results: list[dict[str, Any]]) -> None:
    save_audit_evidence_results(db, job, evidence_kind="baseline", results=results)


def _refresh_baseline_projections(snapshot: dict[str, Any], full_results: list[dict[str, Any]]) -> None:
    samples = _cap_drilldown_results(full_results)
    snapshot["baselineEvidenceSummary"] = [{
        "requestId": item.get("request_id"),
        "capabilityId": item.get("capability_id") or item.get("dimension"),
        "status": item.get("status"),
        "source": item.get("source"),
        "rowsReceived": int(item.get("rows_total") or len(item.get("data") or [])),
        "rowsAnalyzed": len(item.get("data") or []),
        "rowsSentToAi": len((sample.get("data") or [])),
    } for item, sample in zip(full_results, samples)]
    snapshot["aiBaselineSamples"] = samples


def _drilldown_evidence_summaries(
    snapshot: dict[str, Any], full_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    target_cpa = float((snapshot.get("targetKpis") or {}).get("targetCpa") or 0)
    period_days = int((snapshot.get("analysisPeriod") or {}).get("days") or 30)
    summaries = []
    for item in full_results:
        summary, rules = evaluate_capability_evidence(
            item, target_cpa=target_cpa, period_days=period_days,
        )
        capability_id = str(item.get("capability_id") or item.get("dimension") or "")
        confirmation_code = CONFIRMATION_RULE_BY_CAPABILITY.get(capability_id)
        rejection_code = REJECTION_RULE_BY_CAPABILITY.get(capability_id)
        numeric_counts = {"known": 0, "missing": 0, "invalid": 0}
        for row in item.get("data") or []:
            for key, value in row.items():
                key_text = str(key).lower()
                if key_text in {"impressions", "clicks", "cost", "ctr", "avg_cpc", "conversions", "cpa", "goal_conversions", "goal_cpa", "conversion_rate"} or key_text.startswith(("conversions_", "cost_per_conversion_", "conversion_rate_")):
                    numeric_counts[parse_numeric_metric(value).state] += 1
        summaries.append({
            **summary,
            "campaign_name": item.get("campaign_name"),
            "numeric_state_counts": numeric_counts,
            "confirmation_rules": [rule for rule in rules if rule.get("rule_code") == confirmation_code],
            "rejection_rules": [rule for rule in rules if rule.get("rule_code") == rejection_code],
        })
    return summaries


def _refresh_drilldown_projections(
    snapshot: dict[str, Any], full_results: list[dict[str, Any]],
) -> None:
    samples = _cap_drilldown_results(full_results)
    snapshot["drilldownEvidenceSummaries"] = _drilldown_evidence_summaries(snapshot, full_results)
    snapshot["aiDrilldownSamples"] = samples
    # Compatibility alias for existing metadata/UI paths. Backend evaluation never reads it.
    snapshot["drilldownResults"] = samples


def _merge_drilldown_results(
    existing: list[dict[str, Any]],
    collected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in existing + collected:
        request_id = str(item.get("request_id") or "")
        key = request_id or f"anonymous-{len(order)}"
        if key not in merged:
            order.append(key)
        merged[key] = item
    return _cap_drilldown_results([merged[key] for key in order])


def _refresh_direct_read_runtime(snapshot: dict[str, Any], direct_api_calls: int) -> None:
    results = snapshot.get("drilldownResults") or []
    runtime = _audit_runtime(snapshot)
    runtime["directApiCallsCount"] = int(runtime.get("directApiCallsCount") or 0) + direct_api_calls
    runtime["liveRequestCount"] = runtime["directApiCallsCount"]
    runtime["liveCompletedCount"] = sum(
        1
        for item in results
        if item.get("live") and item.get("status") in AVAILABLE_AUDIT_DATA_STATUSES
    )
    runtime["processingReportCount"] = sum(1 for item in results if item.get("status") == "processing")
    runtime["cacheHitCount"] = sum(1 for item in results if item.get("cached"))
    runtime["savedDataRequestsCount"] = sum(
        1 for item in results if item.get("source") == "directpilot_saved_stats"
    )
    runtime["liveAttempts"] = sum(1 for item in results if item.get("live_attempted"))
    runtime["liveSucceeded"] = sum(
        1
        for item in results
        if item.get("live_attempted")
        and not item.get("saved_fallback")
        and item.get("status") in AVAILABLE_AUDIT_DATA_STATUSES
    )
    runtime["liveProcessing"] = sum(
        1 for item in results if item.get("live_attempted") and item.get("status") == "processing"
    )
    runtime["liveFailed"] = sum(
        1
        for item in results
        if item.get("live_attempted")
        and (item.get("saved_fallback") or item.get("status") in {"failed", "unavailable"})
    )
    runtime["cacheHits"] = runtime["cacheHitCount"]
    runtime["savedFallbacks"] = sum(1 for item in results if item.get("saved_fallback"))
    safe_reason_codes = {
        "direct_auth_error",
        "direct_permission_denied",
        "direct_invalid_field_combination",
        "direct_report_processing",
        "direct_report_queue_full",
        "direct_report_queue_full_timeout",
        "direct_rate_limited",
        "direct_no_data",
        "adapter_failed",
        "saved_fallback_used",
    }
    failure_reasons: dict[str, int] = {}
    for item in results:
        if not item.get("live_attempted") or not (item.get("live_error_code") or item.get("saved_fallback")):
            continue
        reason = str(item.get("live_error_code") or "saved_fallback_used")
        if item.get("saved_fallback") and not reason:
            reason = "saved_fallback_used"
        if reason not in safe_reason_codes:
            reason = "direct_request_failed"
        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    runtime["liveFailureReasons"] = failure_reasons
    runtime["unavailableCapabilities"] = sorted({
        str(item.get("capability_id") or item.get("dimension"))
        for item in results
        if item.get("status") in {"unavailable", "unsupported", "not_applicable", "failed"}
    })


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


def _read_job(db: Session, job_id: str, organization_id: str) -> AiAuditJob:
    """Read a job without taking the row lock used by state-changing stages."""
    job = db.scalar(
        select(AiAuditJob).where(
            AiAuditJob.id == job_id,
            AiAuditJob.organization_id == organization_id,
        )
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI audit job not found")
    return job


def is_audit_stage_stale(job: AiAuditJob, now: datetime | None = None) -> bool:
    current = _as_aware(now or _now())
    if job.status == "queued":
        created = job.created_at or job.updated_at
        return bool(
            created
            and _as_aware(created) + timedelta(seconds=QUEUED_AUDIT_STALE_SECONDS) < current
        )
    if job.status == "collecting_context":
        last_update = job.stage_started_at or job.updated_at or job.started_at or job.created_at
        return bool(
            last_update
            and _as_aware(last_update) + timedelta(seconds=NON_PROVIDER_STAGE_STALE_SECONDS) < current
        )
    if job.status != "generating":
        return False
    lease_expires_at = job.stage_lease_expires_at
    if not lease_expires_at:
        legacy_started_at = job.stage_started_at or job.updated_at
        if not legacy_started_at:
            return False
        lease_seconds = AUDIT_STAGE_LEASE_SECONDS.get(job.current_stage, 180)
        lease_expires_at = _as_aware(legacy_started_at) + timedelta(seconds=lease_seconds)
    return _as_aware(lease_expires_at) < current


def _prepare_saved_evidence_for_final_fallback(
    db: Session,
    job: AiAuditJob,
    snapshot: dict[str, Any],
) -> bool:
    """Validate persisted evidence without collecting any new Direct data."""

    if not isinstance(snapshot.get("analysisPeriod"), dict) or not isinstance(snapshot.get("accountTotals"), dict):
        return False
    policy_active = (
        snapshot.get("policyVersion") == AUDIT_EVIDENCE_POLICY_VERSION
        or "evidenceCoverageRegistry" in snapshot
    )
    if not policy_active:
        verification = snapshot.get("verificationRegistry") or snapshot.get("verifiedHypotheses")
        classifications = snapshot.get("campaignClassifications")
        return bool(verification) and isinstance(classifications, list) and bool(classifications)
    try:
        coverage = refresh_evidence_coverage_registry(
            snapshot, _load_full_evidence_results(db, job),
        )
    except Exception:
        logger.exception("AI_AUDIT_SAVED_EVIDENCE_INVALID job_id=%s", job.id)
        return False
    completion_state = str(coverage.get("completionState") or "")
    if completion_state not in {"complete", "partial_coverage", "blocked_missing_evidence"}:
        return False
    _sync_policy_runtime(snapshot, coverage)
    return True


def recover_stale_audit_job(
    job: AiAuditJob,
    now: datetime | None = None,
    *,
    db: Session | None = None,
) -> bool:
    if not is_audit_stage_stale(job, now):
        return False
    logger.warning(
        "AI_AUDIT_STAGE_STALE job_id=%s stage=%s attempt=%s",
        job.id,
        job.current_stage,
        job.stage_attempt,
    )
    if job.current_stage == "generate_answer" and db is not None:
        snapshot = _json_load(job.context_snapshot_json, {}) or {}
        if _prepare_saved_evidence_for_final_fallback(db, job, snapshot):
            runtime = _audit_runtime(snapshot)
            diagnostics = {
                key: runtime.get(key)
                for key in (
                    "finalProjectionEstimatedTokens", "finalPromptEstimatedTokens", "modelContextLimit",
                    "reservedOutputTokens", "requestedOutputTokens", "effectiveFinalOutputTokens",
                    "safetyMarginTokens", "finalCompactionLevel", "fitsModelContext",
                    "preflightFitsModelContext", "providerContextRejected", "providerContextErrorCode",
                )
            }
            _complete_backend_fallback_stage(
                db,
                job,
                snapshot,
                diagnostics,
                _json_load(job.timings_json, {}) or {},
                reason_code="final_stage_stale",
                final_status="backend_fallback_after_final_stage_stale",
                warning=(
                    "Финальный этап аудита был прерван. Использован безопасный backend-отчёт по уже "
                    "собранным данным без повторных запросов к Яндекс.Директу."
                ),
                warning_code="final_stage_stale",
                complete_immediately=True,
            )
            return True
    if job.current_stage in {"create_investigation_plan", "verify_hypotheses", "plan_next_investigation_round"}:
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
        elif job.current_stage == "verify_hypotheses":
            verification = _verification_fallback(snapshot)
            _apply_verification_statuses(snapshot, verification)
            stage_name = "verification"
            warning_code = "verification_fallback_used"
            message = "AI-проверка гипотез не ответила; неподтверждённые выводы безопасно помечены как требующие проверки."
            next_stage = "plan_next_investigation_round"
            progress_percent = 78
            prompt_tokens = int(runtime.get("verificationPromptTokensEstimated") or 0)
        else:
            stage_name = "next_round_planner"
            warning_code = "next_round_planner_fallback_used"
            message = "AI-планировщик следующего раунда не ответил; используется безопасный backend fallback."
            fallback_requests = _second_round_requests(snapshot)
            snapshot["fallbackNextRoundRequests"] = [item.model_dump(mode="json") for item in fallback_requests]
            next_stage = "apply_next_investigation_round"
            progress_percent = 74
            prompt_tokens = int(runtime.get("nextRoundPromptTokensEstimated") or 0)
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


async def _call_audit_provider(
    stage: str,
    *args: Any,
    total_timeout_seconds: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if stage == "generate_answer":
        # Qwen3 can spend most of max_tokens on hidden reasoning and truncate the
        # JSON report. Trusted calculations already happen on the backend, so the
        # final model only needs to synthesize a compact machine-readable result.
        model = str(args[0]) if args else ""
        if model.startswith("qwen/"):
            kwargs.setdefault("reasoning", {"effort": "none"})
        kwargs.setdefault("response_format", {"type": "json_object"})
    stage_timeout = (
        float(total_timeout_seconds)
        if total_timeout_seconds is not None
        else float(AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS[stage])
    )
    try:
        async with asyncio.timeout(stage_timeout):
            try:
                return await generate_openrouter_response(*args, **kwargs)
            except HTTPException as exc:
                # A permanent request incompatibility of the selected final model
                # must not discard already collected read-only evidence. The helper
                # model is already used for the staged audit and can return the same
                # structured final schema without exposing credentials to the client.
                model = str(args[0]) if args else ""
                if (
                    stage == "generate_answer"
                    and exc.status_code in {
                        status.HTTP_400_BAD_REQUEST,
                        status.HTTP_502_BAD_GATEWAY,
                    }
                    and not is_provider_context_overflow(exc)
                    and model
                ):
                    fallback_model = (
                        AI_FALLBACK_ECONOMY_MODEL
                        if model == AI_AUDIT_HELPER_MODEL
                        else AI_AUDIT_HELPER_MODEL
                    )
                    logger.warning(
                        "AI_AUDIT_FINAL_MODEL_FALLBACK stage=%s requested_model=%s fallback_model=%s reason=http_%s",
                        stage,
                        model,
                        fallback_model,
                        exc.status_code,
                    )
                    return await generate_openrouter_response(
                        fallback_model, *args[1:], **kwargs,
                    )
                raise
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
    if recover_stale_audit_job(current, _now(), db=db):
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
    job = _read_job(db, job_id, organization_id)
    if not is_audit_stage_stale(job):
        return job

    # Status polling is lock-free. Only a stale-recovery write needs to claim
    # the row, otherwise a frequent browser poll can block an active scheduler.
    job = _locked_job(db, job_id, organization_id)
    if recover_stale_audit_job(job, _now(), db=db):
        db.commit()
        db.refresh(job)
    return job


def get_latest_active_audit_job(
    db: Session,
    *,
    client_id: str,
    organization_id: str,
) -> AiAuditJob | None:
    """Return the most recently updated non-terminal audit for an owned client.

    The browser keeps a job id as a convenience only. This lookup is the
    server-side recovery path after a reload or local storage loss, and is
    deliberately scoped to both the current organization and selected client.
    """
    client = db.get(ClientAccount, client_id)
    if not client or client.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    jobs = db.scalars(
        select(AiAuditJob)
        .where(
            AiAuditJob.organization_id == organization_id,
            AiAuditJob.client_id == client_id,
            AiAuditJob.status.notin_(TERMINAL_AUDIT_STATUSES),
        )
        .order_by(AiAuditJob.updated_at.desc(), AiAuditJob.created_at.desc())
    ).all()
    for job in jobs:
        if recover_stale_audit_job(job, _now(), db=db):
            db.commit()
            db.refresh(job)
        if job.status not in TERMINAL_AUDIT_STATUSES:
            return job
    return None


def _context_metadata(job: AiAuditJob, db: Session | None = None) -> dict[str, Any]:
    snapshot = _json_load(job.context_snapshot_json, {}) or {}
    drilldowns = snapshot.get("drilldownResults") or []
    runtime = snapshot.get("auditRuntime") or {}
    requested_dimensions = sorted({str(item.get("dimension")) for item in drilldowns if item.get("dimension")})
    status_counts: dict[str, int] = {}
    for item in drilldowns:
        value = str(item.get("status") or "unknown")
        status_counts[value] = status_counts.get(value, 0) + 1
    result_by_request = {item.get("request_id"): item for item in drilldowns}
    public_rounds = []
    for round_item in snapshot.get("investigationRounds") or []:
        public_rounds.append({
            "roundNumber": round_item.get("round_number"),
            "facts": [
                {
                    "factId": item.get("fact_id"), "campaignName": item.get("campaign_name"),
                    "metric": item.get("metric"), "evidence": item.get("evidence") or [],
                    "sufficientData": bool(item.get("sufficient_data")),
                }
                for item in (round_item.get("observed_facts") or [])
            ],
            "hypotheses": [
                {
                    "hypothesisId": item.get("hypothesis_id"),
                    "hypothesisType": item.get("hypothesis_type"),
                    "parentHypothesisId": item.get("parent_hypothesis_id"),
                    "factIds": item.get("fact_ids") or [],
                    "campaignName": item.get("campaign_name"),
                    "hypothesis": item.get("hypothesis"),
                    "rationale": item.get("rationale"),
                    "status": item.get("status") or "proposed",
                    "priority": item.get("priority") or "medium",
                    "requiredCapabilities": item.get("required_capabilities") or [],
                    "remainingDataNeeded": item.get("remaining_data_needed") or [],
                }
                for item in (round_item.get("hypotheses") or [])
            ],
            "requests": [
                {
                    "requestId": item.get("request_id"),
                    "hypothesisId": item.get("hypothesis_id"),
                    "campaignName": item.get("campaign_name"),
                    "capabilityId": item.get("capability_id") or item.get("dimension"),
                    "status": (result_by_request.get(item.get("request_id")) or {}).get("status") or "pending",
                    "source": (result_by_request.get(item.get("request_id")) or {}).get("source_type"),
                    "rows": (result_by_request.get(item.get("request_id")) or {}).get("rows_analyzed") or 0,
                    "freshness": (result_by_request.get(item.get("request_id")) or {}).get("freshness"),
                }
                for item in (round_item.get("planned_requests") or [])
            ],
            "verifications": round_item.get("verification_results") or [],
            "stopReason": round_item.get("stop_reason"),
        })
    public_trace = {
        "publicRequestTrace": [], "requestDiagnostics": {},
        "dataSourceSummary": {}, "dataQualitySummary": {},
    }
    canonical_coverage = snapshot.get("canonicalEvidenceCoverage") or {
        "accountWide": [],
        "campaignScoped": [],
        "campaignMatrix": [],
        "capabilitySummary": [],
        "summary": {},
    }
    if db is not None:
        evidence_results = _merge_full_drilldown_results(
            _load_full_baseline_results(db, job),
            _load_full_drilldown_results(db, job),
        )
        report_jobs = list(db.scalars(select(DirectReportJob).where(
            DirectReportJob.audit_job_id == job.id,
            DirectReportJob.client_id == job.client_id,
        )))
        public_trace = build_public_audit_trace(snapshot, evidence_results, report_jobs)
        canonical_coverage = canonical_coverage_projection(
            build_canonical_evidence_index(snapshot, evidence_results), snapshot,
        )
    runtime_public = dict(runtime)
    if db is not None and job.status not in TERMINAL_AUDIT_STATUSES and runtime_public.get("schedulerPhase") != "finalization":
        waiting_reason, next_retry_at = _pending_report_wait(db, job)
        if waiting_reason:
            runtime_public["waitingReason"] = waiting_reason
        if next_retry_at:
            runtime_public["nextRetryAt"] = _as_aware(next_retry_at).isoformat()
    if job.status in TERMINAL_AUDIT_STATUSES:
        runtime_public["waitingReason"] = None
        runtime_public["nextRetryAt"] = None
        runtime_public["recoveryStatus"] = "idle"
    runtime_snapshot = {**snapshot, "auditRuntime": runtime_public}
    runtime_public["schedulerHealth"] = (
        {
            "status": job.status,
            "secondsSinceProgress": 0,
            "waitingReason": None,
            "nextRetryAt": None,
        }
        if job.status in TERMINAL_AUDIT_STATUSES
        else scheduler_health(runtime_snapshot)
    )
    runtime_public["deadline"] = scheduler_deadline_state(runtime_snapshot)
    elapsed_until = (
        job.completed_at or job.updated_at or _now()
        if job.status in TERMINAL_AUDIT_STATUSES
        else _now()
    )
    runtime_public["elapsedSeconds"] = max(
        0,
        int(
            (
                _as_aware(elapsed_until)
                - _as_aware(job.started_at or job.created_at or elapsed_until)
            ).total_seconds()
        ),
    )
    verification_public = [
        {
            "hypothesisId": hypothesis_id,
            "status": item.get("status"),
            "summary": item.get("verification_summary"),
            "supportingEvidence": list(item.get("supporting_evidence") or [])[:8],
            "contradictingEvidence": list(item.get("contradicting_evidence") or [])[:8],
            "limitations": list(item.get("limitations") or [])[:8],
            "remainingDataNeeded": list(item.get("remaining_data_needed") or [])[:8],
        }
        for hypothesis_id, item in _verification_registry(snapshot).items()
    ]
    evidence_coverage = public_evidence_coverage(
        snapshot,
        legacy_completed=job.status == "completed",
    )
    return {
        **(snapshot.get("metadata") or {}),
        "analysisPeriod": snapshot.get("analysisPeriod") or {},
        "cachePolicy": (snapshot.get("metadata") or {}).get("cachePolicy") or "fresh",
        "directApiKnowledgeVersion": (snapshot.get("metadata") or {}).get("directApiKnowledgeVersion"),
        "dataCoverage": snapshot.get("dataCoverage") or {},
        "investigation": {
            "hypothesesCount": len(_hypothesis_registry(snapshot)),
            "activeHypothesesCount": len(_active_hypothesis_ids(snapshot)),
            "requestedDimensions": requested_dimensions,
            "requestStatusCounts": status_counts,
            "verifiedStatusCounts": {
                status_name: sum(
                    1 for item in _verification_registry(snapshot).values()
                    if item.get("status") == status_name
                )
                for status_name in ("confirmed", "partially_confirmed", "rejected", "unverified", "not_applicable")
            },
            "rounds": public_rounds,
            "stopReason": runtime.get("stopReason"),
            "dataRequests": {
                "planned": int(runtime.get("requestsCount") or 0),
                "allowed": sum(
                    1
                    for item in drilldowns
                    if item.get("status") in {
                        "collected", "cached", "partial", "processing", "unavailable", "insufficient_data", "failed"
                    }
                ),
                "saved": int(runtime.get("savedDataRequestsCount") or 0),
                "live": int(runtime.get("liveRequestCount") or runtime.get("directApiCallsCount") or 0),
                "liveCompleted": int(runtime.get("liveCompletedCount") or 0),
                "processing": int(runtime.get("processingReportCount") or 0),
                "cacheHits": int(runtime.get("cacheHitCount") or 0),
                "liveAttempts": int(runtime.get("liveAttempts") or 0),
                "liveSucceeded": int(runtime.get("liveSucceeded") or 0),
                "liveProcessing": int(runtime.get("liveProcessing") or 0),
                "liveFailed": int(runtime.get("liveFailed") or 0),
                "savedFallbacks": int(runtime.get("savedFallbacks") or 0),
                "liveFailureReasons": runtime.get("liveFailureReasons") or {},
                "statusCounts": status_counts,
                "unavailableDimensions": sorted({
                    str(item.get("dimension"))
                    for item in drilldowns
                    if item.get("dimension") and item.get("status") in {
                        "unavailable", "unsupported", "skipped_budget_limit", "failed"
                    }
                }),
                "unavailableCapabilities": runtime.get("unavailableCapabilities") or [],
                "freshestDataAt": max(
                    (str(item.get("fetched_at")) for item in drilldowns if item.get("fetched_at")),
                    default=None,
                ),
                "pending": len(snapshot.get("pendingDataRequests") or []),
                "processing": len(snapshot.get("processingDataRequests") or []),
                "completed": len(snapshot.get("completedDataRequests") or []),
                "failed": len(snapshot.get("failedDataRequests") or []),
                "unavailable": len(snapshot.get("unavailableDataRequests") or []),
            },
        },
        "investigationTree": public_rounds,
        "publicRequestTrace": public_trace["publicRequestTrace"],
        "requestDiagnostics": public_trace["requestDiagnostics"],
        "verificationRegistryPublic": verification_public,
        "activeHypothesisIds": _active_hypothesis_ids(snapshot),
        "dataSourceSummary": public_trace["dataSourceSummary"],
        "dataQualitySummary": public_trace["dataQualitySummary"],
        "auditCompletionState": evidence_coverage["completionState"],
        "evidenceCoverage": evidence_coverage,
        "canonicalEvidenceCoverage": canonical_coverage,
        "auditStopReason": runtime.get("stopReason"),
        "baselineEvidenceSummary": snapshot.get("baselineEvidenceSummary") or [],
        "runtime": runtime_public,
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
    if not structured:
        candidates = []
        if result:
            candidates.extend((result.get("technicalResponse"), result.get("rawResponse"), result.get("fallbackMarkdown")))
        candidates.append(job.answer_text)
        response = {"model": job.returned_model or job.model}
        for candidate in candidates:
            if not candidate:
                continue
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
            if not result.get("truncated") and not result.get("backendFallbackUsed"):
                result["completeness"] = (
                    "partial_coverage"
                    if result.get("auditCompletionState") == "partial_coverage"
                    else "structured"
                )
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
            result.pop("technicalResponse", None)
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


_INTERNAL_RESULT_SCHEMA_ERROR_MESSAGE = (
    "Не удалось сформировать итоговый структурированный отчёт. Собранные данные сохранены."
)
_INTERNAL_VALIDATION_ERROR_MARKERS = (
    "validation error for",
    "validation errors for",
    "errors.pydantic.dev",
    "input_value=",
)


def _public_audit_error_message(job: AiAuditJob) -> str | None:
    message = str(job.error_message or "").strip()
    if not message:
        return None
    normalized = message.lower()
    if job.error_code == "ai_audit_result_schema_error" or (
        job.current_stage in {"generate_answer", "finalize"}
        and any(marker in normalized for marker in _INTERNAL_VALIDATION_ERROR_MARKERS)
    ):
        return _INTERNAL_RESULT_SCHEMA_ERROR_MESSAGE
    return message[:1000]


def _audit_poll_after_ms(job: AiAuditJob, db: Session | None) -> int:
    if db is None or job.status in TERMINAL_AUDIT_STATUSES:
        return POLL_AFTER_MS
    now = _now()
    retry_times = [
        value
        for value in db.scalars(select(DirectReportJob.next_retry_at).where(
            DirectReportJob.audit_job_id == job.id,
            DirectReportJob.client_id == job.client_id,
            DirectReportJob.status.in_(("queued", "requested", "processing", "waiting_for_report_queue")),
            DirectReportJob.next_retry_at.is_not(None),
        ))
        if value is not None
    ]
    if not retry_times:
        return POLL_AFTER_MS
    retry_at = min(
        value.replace(tzinfo=UTC) if value.tzinfo is None else value
        for value in retry_times
    )
    return max(POLL_AFTER_MS, min(300_000, int(max(0, (retry_at - now).total_seconds()) * 1000)))


def audit_job_response(job: AiAuditJob, db: Session | None = None) -> AiAuditJobResponse:
    result, answer = _public_audit_result(job)
    return AiAuditJobResponse(
        job_id=job.id,
        client_id=job.client_id,
        status=job.status,
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        poll_after_ms=_audit_poll_after_ms(job, db),
        requested_scope=job.requested_scope,
        requested_period=job.requested_period,
        selected_campaign_name=job.selected_campaign_name,
        model=job.model,
        returned_model=job.returned_model,
        ai_preset=job.ai_preset,
        max_tokens=job.max_tokens,
        system_prompt_version=job.system_prompt_version,
        system_prompt_hash=job.system_prompt_hash,
        context_metadata=_context_metadata(job, db),
        timings=_json_load(job.timings_json, {}),
        result=result,
        answer=answer,
        error_code=job.error_code,
        error_message=_public_audit_error_message(job),
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
        input_options_json=_json_dump({
            **payload.options.model_dump(),
            "cache_policy": payload.cache_policy,
            "allow_saved_fallback": payload.allow_saved_fallback,
        }),
        timings_json="{}",
        expires_at=now + timedelta(days=30),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _save_failure(db: Session, job: AiAuditJob, exc: Exception, *, stage: str) -> AiAuditJob:
    internal_result_validation_error = isinstance(exc, ValidationError) and stage in {"generate_answer", "finalize"}
    detail = (
        _INTERNAL_RESULT_SCHEMA_ERROR_MESSAGE
        if internal_result_validation_error
        else (exc.detail if isinstance(exc, HTTPException) else str(exc))
    )
    error_code = detail.get("error_code") if isinstance(detail, dict) else None
    retryable = bool(detail.get("retryable")) if isinstance(detail, dict) else False
    job.status = "failed"
    job.current_stage = stage
    job.error_code = str(
        "ai_audit_result_schema_error"
        if internal_result_validation_error
        else (error_code or "ai_audit_stage_failed")
    )
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
    logger.info("AI_AUDIT_ADVANCE_LOCKING job_id=%s", job_id)
    job = _locked_job(db, job_id, organization_id)
    logger.info("AI_AUDIT_ADVANCE_LOCKED job_id=%s status=%s stage=%s", job.id, job.status, job.current_stage)
    if recover_stale_audit_job(job, _now(), db=db):
        db.commit()
        db.refresh(job)
        return job
    if job.status == "completed" and compact_retry:
        current_result = _json_load(job.result_json, {}) or {}
        if (
            current_result.get("truncated")
            or current_result.get("compactRetryAvailable")
        ):
            options = _json_load(job.input_options_json, {}) or {}
            options["compact_retry"] = True
            job.input_options_json = _json_dump(options)
            snapshot = _json_load(job.context_snapshot_json, {}) or {}
            runtime = _audit_runtime(snapshot)
            runtime["finalGenerationStatus"] = "compact_retry_pending"
            runtime["backendFallbackUsed"] = False
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
            logger.info("AI_AUDIT_CONTEXT_STATUS_COMMIT_START job_id=%s", job.id)
            job.status = "collecting_context"
            job.progress_percent = 10
            job.started_at = job.started_at or _now()
            job.stage_version += 1
            db.commit()
            logger.info("AI_AUDIT_CONTEXT_STATUS_COMMIT_DONE job_id=%s", job.id)
            context_started_at = perf_counter()
            logger.info("AI_AUDIT_CONTEXT_BUILD_START job_id=%s", job.id)
            input_options = _json_load(job.input_options_json, {}) or {}
            cache_policy = str(input_options.get("cache_policy") or "fresh")
            full_context = (
                _fresh_initial_audit_context(db, job)
                if cache_policy == "fresh"
                else build_client_ai_context_from_db(
                    db,
                    job.client_id,
                    selected_campaign_name=job.selected_campaign_name,
                )
            )
            timings["collectContextMs"] = _elapsed_ms(context_started_at)
            logger.info("AI_AUDIT_CONTEXT_BUILD_DONE job_id=%s elapsed_ms=%s", job.id, timings["collectContextMs"])
            compact_started_at = perf_counter()
            snapshot = build_compact_audit_context(
                full_context,
                requested_period=job.requested_period,
                options=_json_load(job.input_options_json, {}),
            )
            snapshot["requestedScope"] = job.requested_scope
            snapshot.setdefault("metadata", {})["cachePolicy"] = cache_policy
            snapshot["metadata"]["directApiKnowledgeVersion"] = DIRECT_API_KNOWLEDGE_VERSION
            snapshot["auditRuntime"] = {
                "investigationRound": 1,
                "maxInvestigationRounds": MAX_INVESTIGATION_ROUNDS,
                "requestsCount": 0,
                "providerCallsCount": 0,
                "helperProviderCallsCount": 0,
                "finalProviderCallsCount": 0,
                "helperFallbacksCount": 0,
                "plannerPromptTokensEstimated": 0,
                "verificationPromptTokensEstimated": 0,
                "savedDataRequestsCount": 0,
                "directApiCallsCount": 0,
                "liveRequestCount": 0,
                "liveCompletedCount": 0,
                "processingReportCount": 0,
                "cacheHitCount": 0,
                "liveAttempts": 0,
                "liveSucceeded": 0,
                "liveProcessing": 0,
                "liveFailed": 0,
                "cacheHits": 0,
                "savedFallbacks": 0,
                "liveFailureReasons": {},
                "unavailableCapabilities": [],
                "tokenUsage": {"prompt": 0, "completion": 0, "total": 0},
            }
            initialize_scheduler_state(
                snapshot,
                scope=job.requested_scope,
                started_at=_as_aware(job.started_at or _now()),
            )
            _helper_stages(snapshot)
            _audit_models(snapshot, job.model)
            snapshot["metadata"]["estimatedTokens"] = estimate_tokens(_json_dump(snapshot))
            timings["compactContextMs"] = _elapsed_ms(compact_started_at)
            job.context_snapshot_json = _json_dump(snapshot)
            internal_ids = []
            trusted_scopes: dict[str, str] = {}
            ambiguous_scope_names: set[str] = set()
            trusted_scope_names: dict[str, str] = {}
            for item in (full_context.get("campaigns") or []):
                if not isinstance(item, dict):
                    continue
                raw_id = item.get("campaign_id") or item.get("id")
                name = str(item.get("name") or item.get("campaign_name") or "").strip()
                if raw_id:
                    internal_ids.append(str(raw_id))
                    if name:
                        scope = campaign_scope_key(raw_id) or ""
                        if scope:
                            trusted_scope_names[scope] = name
                        if name in trusted_scopes and trusted_scopes[name] != scope:
                            ambiguous_scope_names.add(name)
                            trusted_scopes.pop(name, None)
                        elif name not in ambiguous_scope_names:
                            trusted_scopes[name] = scope
            snapshot["_trustedCampaignScopes"] = {
                key: value for key, value in trusted_scopes.items() if value
            }
            snapshot["_trustedCampaignScopeNames"] = trusted_scope_names
            snapshot["_ambiguousCampaignNames"] = sorted(ambiguous_scope_names)
            if ambiguous_scope_names:
                snapshot["evidenceIdentityLimitations"] = [{
                    "code": "ambiguous_campaign_identity",
                    "campaignName": name,
                    "message": "Имя кампании неоднозначно; доказательства не объединяются между кампаниями с одинаковым названием.",
                } for name in sorted(ambiguous_scope_names)]
            job.context_snapshot_json = _json_dump(snapshot)
            job.prompt_snapshot_json = _json_dump({"internalCampaignIds": internal_ids[:100]})
            job.status = "context_ready"
            job.current_stage = (
                "collect_fresh_baseline"
                if snapshot["metadata"]["cachePolicy"] == "fresh"
                else "classify_campaigns"
            )
            job.stage_attempt = 0
            job.progress_percent = 15
        elif stage == "collect_fresh_baseline":
            snapshot = _json_load(job.context_snapshot_json, {})
            pending_source = snapshot.get("pendingBaselineRequests")
            processing_source = snapshot.get("processingBaselineRequests") or []
            if pending_source is None:
                pending = _fresh_baseline_requests(snapshot)
            else:
                pending = [AuditDataRequest.model_validate(item) for item in pending_source]
            processing = [AuditDataRequest.model_validate(item) for item in processing_source]
            deadline = scheduler_deadline_state(snapshot)
            if deadline["collectionDeadlineReached"] or deadline["hardDeadlineReached"]:
                runtime = _audit_runtime(snapshot)
                runtime["schedulerPhase"] = "finalization"
                runtime["stopReason"] = (
                    "hard_deadline_reached"
                    if deadline["hardDeadlineReached"]
                    else "collection_deadline_reached"
                )
                snapshot["pendingBaselineRequests"] = []
                snapshot["processingBaselineRequests"] = []
                mark_scheduler_progress(snapshot, action=runtime["stopReason"])
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "generate_answer"
                job.stage_attempt = 0
                job.progress_percent = 78
                timings["collectFreshBaselineMs"] = int(timings.get("collectFreshBaselineMs") or 0) + _elapsed_ms(started_at)
                timings["totalElapsedMs"] = max(
                    0,
                    round((_now() - _as_aware(job.created_at or _now())).total_seconds() * 1000),
                )
                job.timings_json = _json_dump(timings)
                job.stage_version += 1
                db.commit()
                db.refresh(job)
                return job
            waiting_reason, next_retry_at = _pending_report_wait(db, job)
            if (
                waiting_reason
                and next_retry_at is not None
                and _as_aware(next_retry_at) > _now()
            ):
                mark_scheduler_waiting(
                    snapshot,
                    reason=waiting_reason,
                    next_retry_at=_as_aware(next_retry_at),
                )
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "collect_fresh_baseline"
                job.stage_attempt = 0
                job.progress_percent = max(job.progress_percent, 18)
                timings["collectFreshBaselineMs"] = int(timings.get("collectFreshBaselineMs") or 0) + _elapsed_ms(started_at)
                timings["totalElapsedMs"] = max(
                    0,
                    round((_now() - _as_aware(job.created_at or _now())).total_seconds() * 1000),
                )
                job.timings_json = _json_dump(timings)
                job.stage_version += 1
                db.commit()
                db.refresh(job)
                return job
            selected, deferred = select_live_request_batch(processing + pending)
            input_options = _json_load(job.input_options_json, {}) or {}
            collected, direct_api_calls = collect_audit_data_requests(
                db,
                job.client_id,
                selected,
                audit_job_id=job.id,
                cache_policy="fresh",
                allow_saved_fallback=False,
            )
            full_baseline_results = _merge_full_drilldown_results(
                _load_full_baseline_results(db, job),
                [item.model_dump(mode="json") for item in collected],
            )
            _save_full_baseline_results(db, job, full_baseline_results)
            _refresh_baseline_projections(snapshot, full_baseline_results)
            if collected or direct_api_calls:
                mark_scheduler_progress(
                    snapshot,
                    action="fresh_baseline_collected",
                    successful=any(item.status in AVAILABLE_AUDIT_DATA_STATUSES for item in collected),
                )
            selected_by_id = {item.request_id: item for item in selected}
            pending_ids = {item.request_id for item in pending}
            processing_ids = {item.request_id for item in processing}
            next_processing = [
                selected_by_id[item.request_id].model_dump(mode="json")
                for item in collected
                if item.status == "processing" and item.request_id in selected_by_id
            ]
            next_processing.extend(item.model_dump(mode="json") for item in deferred if item.request_id in processing_ids)
            next_pending = [item.model_dump(mode="json") for item in deferred if item.request_id in pending_ids]
            snapshot["pendingBaselineRequests"] = next_pending
            snapshot["processingBaselineRequests"] = next_processing
            _refresh_direct_read_runtime(snapshot, direct_api_calls)
            if not next_pending and not next_processing:
                _apply_live_baseline(
                    snapshot,
                    full_baseline_results,
                    allow_saved_fallback=False,
                )
            job.context_snapshot_json = _json_dump(snapshot)
            job.status = "context_ready"
            job.current_stage = (
                "collect_fresh_baseline" if next_pending or next_processing else "classify_campaigns"
            )
            job.stage_attempt = 0
            job.progress_percent = 18 if next_pending or next_processing else 22
            timings["collectFreshBaselineMs"] = int(timings.get("collectFreshBaselineMs") or 0) + _elapsed_ms(started_at)
        elif stage == "classify_campaigns":
            snapshot = _json_load(job.context_snapshot_json, {})
            snapshot["campaignClassifications"] = classify_audit_campaigns(snapshot)
            classification_summary = _classification_summary(snapshot["campaignClassifications"])
            breadth_requests = build_minimum_coverage_requests(snapshot)
            snapshot["minimumCoveragePlan"] = _minimum_coverage_plan(breadth_requests, snapshot)
            runtime = _audit_runtime(snapshot)
            runtime["campaignsTotal"] = len(snapshot["campaignClassifications"])
            runtime["breadthRequestsTotal"] = len(breadth_requests)
            runtime["classificationSummary"] = classification_summary
            runtime["schedulerPhase"] = "breadth"
            observed_facts = build_observed_facts(snapshot)
            snapshot["observedFacts"] = [item.model_dump(mode="json") for item in observed_facts]
            base_plan = build_rule_based_investigation_plan(snapshot)
            snapshot["ruleBasedInvestigationPlan"] = base_plan.model_dump(mode="json")
            ensure_evidence_coverage_registry(snapshot)
            _sync_policy_runtime(snapshot)
            logger.info(
                "CASCADE_AUDIT_FACTS_CREATED audit_job_id=%s round=1 campaign_count=%s fact_count=%s",
                job.id,
                len(snapshot["campaignClassifications"]),
                len(observed_facts),
            )
            logger.info(
                "CASCADE_AUDIT_CLASSIFICATION_SUMMARY audit_job_id=%s classifications=%s breadth_requests=%s",
                job.id,
                classification_summary,
                len(breadth_requests),
            )
            job.context_snapshot_json = _json_dump(snapshot)
            job.status = "context_ready"
            job.current_stage = "create_investigation_plan"
            job.stage_attempt = 0
            job.progress_percent = 25
            timings["classifyCampaignsMs"] = _elapsed_ms(started_at)
        elif stage == "create_investigation_plan":
            snapshot = _json_load(job.context_snapshot_json, {})
            base_plan = AuditInvestigationPlan.model_validate(snapshot.get("ruleBasedInvestigationPlan") or {})
            planner_deadline = scheduler_deadline_state(snapshot)
            if planner_deadline["collectionDeadlineReached"] or not should_call_ai_investigation_planner(base_plan, snapshot):
                snapshot["investigationPlan"] = base_plan.model_dump(mode="json")
                _set_helper_stage(
                    snapshot,
                    "planner",
                    status_value=(
                        "skipped_deadline"
                        if planner_deadline["collectionDeadlineReached"]
                        else "skipped_not_needed"
                    ),
                )
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
                    plan, valid_plan, parsing = _parse_investigation_plan(
                        str(response.get("content") or ""), snapshot, base_plan,
                    )
                    snapshot["investigationPlan"] = plan.model_dump(mode="json")
                    if valid_plan:
                        _set_helper_stage(
                            snapshot,
                            "planner",
                            status_value="success",
                            returned_model=returned_model,
                            parsing=parsing,
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
                            parsing=parsing,
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
            _initialize_hypothesis_state(snapshot)
            ai_requests = [request for hypothesis in plan.hypotheses for request in hypothesis.data_requests]
            profile = _audit_execution_profile(job, snapshot)
            breadth_requests = build_minimum_coverage_requests(snapshot)
            policy_requests, policy_rejections, _ = merge_mandatory_and_ai_requests(
                snapshot,
                ai_requests,
                request_budget=profile.max_requests,
            )
            requests = _deduplicate_requests([*breadth_requests, *policy_requests])[:profile.max_requests]
            _log_audit_event(
                "AUDIT_REQUEST_PLANNED", job,
                round=1, request_count=len(requests), status="pending",
            )
            accepted, rejected = validate_audit_data_requests(
                requests, max_requests=profile.max_requests,
            )
            breadth, depth = partition_breadth_and_depth_requests(
                accepted, breadth_requests, profile=profile,
            )
            _log_audit_event(
                "AUDIT_REQUEST_VALIDATED", job,
                round=1, request_count=len(accepted), status="validated",
            )
            runtime = _audit_runtime(snapshot)
            runtime["requestsCount"] = len(accepted)
            runtime["requestSafetyLimit"] = profile.max_requests
            runtime["maxDepthRounds"] = profile.max_depth_rounds
            runtime["schedulerPhase"] = "breadth"
            runtime["breadthRequestsTotal"] = len(breadth)
            runtime["depthRequestsTotal"] = len(depth)
            snapshot["validatedDataRequests"] = [item.model_dump(mode="json") for item in accepted]
            snapshot["minimumCoveragePlan"] = _minimum_coverage_plan(breadth, snapshot)
            snapshot["deferredDepthDataRequests"] = [item.model_dump(mode="json") for item in depth]
            policy_rejection_results = [_policy_rejection_result(item) for item in policy_rejections]
            initial_full_results = [item.model_dump(mode="json") for item in rejected]
            initial_full_results.extend(policy_rejection_results)
            _save_full_drilldown_results(db, job, initial_full_results)
            _refresh_drilldown_projections(snapshot, initial_full_results)
            snapshot["pendingDataRequests"] = [item.model_dump(mode="json") for item in breadth]
            snapshot["processingDataRequests"] = []
            snapshot["completedDataRequests"] = []
            snapshot["failedDataRequests"] = []
            snapshot["unavailableDataRequests"] = [item.model_dump(mode="json") for item in rejected]
            snapshot["unavailableDataRequests"].extend(policy_rejection_results)
            coverage = refresh_evidence_coverage_registry(
                snapshot, _load_full_evidence_results(db, job),
            )
            _sync_policy_runtime(snapshot, coverage)
            facts = build_observed_facts(snapshot)
            cascade_hypotheses = build_cascade_hypotheses(plan, facts, round_number=1)
            round_state = create_investigation_round(
                round_number=1, facts=facts, hypotheses=cascade_hypotheses, requests=accepted,
            )
            snapshot["investigationRounds"] = [round_state.model_dump(mode="json")]
            logger.info(
                "CASCADE_AUDIT_HYPOTHESES_CREATED audit_job_id=%s round=1 hypothesis_count=%s request_count=%s",
                job.id, len(cascade_hypotheses), len(accepted),
            )
            logger.info(
                "CASCADE_AUDIT_DATA_REQUESTED audit_job_id=%s round=1 capability_ids=%s request_count=%s",
                job.id,
                ",".join(sorted({item.capability_id or item.dimension for item in accepted})),
                len(accepted),
            )
            deadline = scheduler_deadline_state(snapshot)
            if deadline["collectionDeadlineReached"] or deadline["hardDeadlineReached"]:
                _finish_collection_for_deadline(
                    db,
                    job,
                    snapshot,
                    [*breadth, *depth],
                    reason=(
                        "hard_deadline_reached"
                        if deadline["hardDeadlineReached"]
                        else "collection_deadline_reached"
                    ),
                )
            else:
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "collect_live_data"
                job.stage_attempt = 0
                job.progress_percent = 50
            timings["validateDataRequestsMs"] = _elapsed_ms(started_at)
        elif stage in {"collect_drilldowns", "collect_live_data", "wait_for_offline_reports"}:
            snapshot = _json_load(job.context_snapshot_json, {})
            pending_source = (
                snapshot.get("pendingDataRequests")
                if "pendingDataRequests" in snapshot
                else snapshot.get("validatedDataRequests")
            )
            pending = [AuditDataRequest.model_validate(item) for item in (pending_source or [])]
            processing = [AuditDataRequest.model_validate(item) for item in (snapshot.get("processingDataRequests") or [])]
            deferred_depth = [
                AuditDataRequest.model_validate(item)
                for item in (snapshot.get("deferredDepthDataRequests") or [])
            ]
            deadline = scheduler_deadline_state(snapshot)
            runtime = _audit_runtime(snapshot)
            if (
                runtime.get("schedulerPhase") == "finalization"
                or deadline["collectionDeadlineReached"]
                or deadline["hardDeadlineReached"]
                or not collection_batch_can_start(snapshot)
            ):
                _finish_collection_for_deadline(
                    db,
                    job,
                    snapshot,
                    [*pending, *processing, *deferred_depth],
                    reason=(
                        "hard_deadline_reached"
                        if deadline["hardDeadlineReached"]
                        else "collection_batch_reserve_protected"
                        if not deadline["collectionDeadlineReached"]
                        else "collection_deadline_reached"
                    ),
                )
                timings["collectLiveDataMs"] = int(timings.get("collectLiveDataMs") or 0) + _elapsed_ms(started_at)
                timings["totalElapsedMs"] = max(
                    0,
                    round((_now() - _as_aware(job.created_at or _now())).total_seconds() * 1000),
                )
                job.timings_json = _json_dump(timings)
                job.stage_version += 1
                db.commit()
                db.refresh(job)
                return job

            waiting_reason, next_retry_at = _pending_report_wait(db, job)
            if (
                waiting_reason
                and next_retry_at is not None
                and _as_aware(next_retry_at) > _now()
            ):
                mark_scheduler_waiting(
                    snapshot,
                    reason=waiting_reason,
                    next_retry_at=_as_aware(next_retry_at),
                )
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "wait_for_offline_reports"
                job.stage_attempt = 0
                job.progress_percent = max(job.progress_percent, 58)
                timings["collectLiveDataMs"] = int(timings.get("collectLiveDataMs") or 0) + _elapsed_ms(started_at)
                timings["totalElapsedMs"] = max(
                    0,
                    round((_now() - _as_aware(job.created_at or _now())).total_seconds() * 1000),
                )
                job.timings_json = _json_dump(timings)
                job.stage_version += 1
                db.commit()
                db.refresh(job)
                return job

            requests, deferred = select_live_request_batch(processing + pending)
            for request in requests:
                _log_audit_event(
                    "AUDIT_REQUEST_STARTED", job,
                    round=_audit_runtime(snapshot).get("investigationRound") or 1,
                    capability=request.capability_id or request.dimension,
                    status="processing",
                )
            input_options = _json_load(job.input_options_json, {}) or {}
            cache_policy = str(input_options.get("cache_policy") or "fresh")
            collected, direct_api_calls = collect_audit_data_requests(
                db,
                job.client_id,
                requests,
                audit_job_id=job.id,
                cache_policy=cache_policy,
                allow_saved_fallback=(
                    cache_policy != "fresh" and bool(input_options.get("allow_saved_fallback"))
                ),
            )
            full_results = _merge_full_drilldown_results(
                _load_full_drilldown_results(db, job),
                [item.model_dump(mode="json") for item in collected],
            )
            _save_full_drilldown_results(db, job, full_results)
            _refresh_drilldown_projections(snapshot, full_results)
            evidence_results = _load_full_evidence_results(db, job)
            coverage = refresh_evidence_coverage_registry(snapshot, evidence_results)
            _sync_policy_runtime(snapshot, coverage)
            _refresh_scheduler_coverage(snapshot, evidence_results)
            for item in collected:
                event_name = {
                    "processing": "AUDIT_REQUEST_PROCESSING",
                    "collected": "AUDIT_REQUEST_COMPLETED",
                    "cached": "AUDIT_REQUEST_COMPLETED",
                    "partial": "AUDIT_REQUEST_PARTIAL",
                }.get(item.status, "AUDIT_REQUEST_FAILED")
                _log_audit_event(
                    event_name, job,
                    round=_audit_runtime(snapshot).get("investigationRound") or 1,
                    capability=item.capability_id or item.dimension,
                    status=item.status,
                    rows=item.rows_analyzed,
                )
                if item.status == "processing" and item.rows_analyzed:
                    _log_audit_event(
                        "AUDIT_REPORT_PAGE_COMPLETED", job,
                        round=_audit_runtime(snapshot).get("investigationRound") or 1,
                        capability=item.capability_id or item.dimension,
                        rows=item.rows_analyzed,
                    )
                if item.status in AVAILABLE_AUDIT_DATA_STATUSES:
                    _log_audit_event(
                        "AUDIT_EVIDENCE_CALCULATED", job,
                        round=_audit_runtime(snapshot).get("investigationRound") or 1,
                        capability=item.capability_id or item.dimension,
                        rows=item.rows_analyzed,
                    )
            requests_by_id = {item.request_id: item for item in requests}
            next_processing = [
                requests_by_id[item.request_id].model_dump(mode="json")
                for item in collected
                if item.status == "processing" and item.request_id in requests_by_id
            ]
            pending_ids = {item.request_id for item in pending}
            processing_ids = {item.request_id for item in processing}
            next_processing.extend(
                item.model_dump(mode="json") for item in deferred if item.request_id in processing_ids
            )
            next_pending = [
                item.model_dump(mode="json") for item in deferred if item.request_id in pending_ids
            ]
            snapshot["pendingDataRequests"] = next_pending
            snapshot["processingDataRequests"] = next_processing
            snapshot["completedDataRequests"] = _merge_drilldown_results(
                snapshot.get("completedDataRequests") or [],
                [item.model_dump(mode="json") for item in collected if item.status in AVAILABLE_AUDIT_DATA_STATUSES],
            )
            snapshot["failedDataRequests"] = _merge_drilldown_results(
                snapshot.get("failedDataRequests") or [],
                [item.model_dump(mode="json") for item in collected if item.status == "failed"],
            )
            snapshot["unavailableDataRequests"] = _merge_drilldown_results(
                snapshot.get("unavailableDataRequests") or [],
                [
                    item.model_dump(mode="json") for item in collected
                    if item.status in {"unavailable", "unsupported", "insufficient_data", "not_applicable"}
                ],
            )
            if snapshot.get("investigationRounds"):
                current_round = snapshot["investigationRounds"][-1]
                current_round["pending_requests"] = next_pending
                current_round["processing_requests"] = next_processing
                current_round["completed_requests"] = _merge_drilldown_results(
                    current_round.get("completed_requests") or [],
                    [item.model_dump(mode="json") for item in collected if item.status in AVAILABLE_AUDIT_DATA_STATUSES],
                )
                current_round["failed_requests"] = _merge_drilldown_results(
                    current_round.get("failed_requests") or [],
                    [
                        item.model_dump(mode="json") for item in collected
                        if item.status in {"failed", "unavailable", "unsupported", "insufficient_data"}
                    ],
                )
            _refresh_direct_read_runtime(snapshot, direct_api_calls)
            terminal_results = [item for item in collected if item.status != "processing"]
            if terminal_results or direct_api_calls:
                mark_scheduler_progress(
                    snapshot,
                    action="direct_evidence_collected",
                    successful=any(item.status in AVAILABLE_AUDIT_DATA_STATUSES for item in terminal_results),
                )
            has_pending = bool(next_pending)
            has_processing = bool(next_processing)
            if not has_pending and not has_processing and _audit_runtime(snapshot).get("schedulerPhase") == "breadth":
                if _activate_deferred_depth(snapshot):
                    next_pending = list(snapshot.get("pendingDataRequests") or [])
                    has_pending = True
            has_hypotheses = bool(_active_hypotheses(snapshot))
            if not has_hypotheses:
                snapshot["activeVerifications"] = []
                snapshot["verifiedHypotheses"] = []
                _set_helper_stage(snapshot, "verification", status_value="skipped_not_needed")
            job.context_snapshot_json = _json_dump(snapshot)
            job.status = "context_ready"
            if has_pending:
                job.current_stage = "collect_live_data"
            elif has_processing:
                waiting_reason, next_retry_at = _pending_report_wait(db, job)
                mark_scheduler_waiting(
                    snapshot,
                    reason=waiting_reason or "offline_report_processing",
                    next_retry_at=next_retry_at,
                )
                job.current_stage = "wait_for_offline_reports"
            else:
                job.current_stage = "verify_hypotheses" if has_hypotheses else "generate_answer"
                _audit_runtime(snapshot)["schedulerPhase"] = (
                    "verification" if has_hypotheses else "finalization"
                )
            job.context_snapshot_json = _json_dump(snapshot)
            job.stage_attempt = 0
            job.progress_percent = 58 if (has_pending or has_processing) else (65 if has_hypotheses else 78)
            logger.info(
                "CASCADE_AUDIT_DATA_COMPLETED audit_job_id=%s round=%s batch=%s pending=%s processing=%s api_calls=%s",
                job.id, _audit_runtime(snapshot).get("investigationRound"), len(requests),
                len(next_pending), len(next_processing), direct_api_calls,
            )
            timings["collectLiveDataMs"] = int(timings.get("collectLiveDataMs") or 0) + _elapsed_ms(started_at)
        elif stage == "verify_hypotheses":
            snapshot = _json_load(job.context_snapshot_json, {})
            verification_deadline = scheduler_deadline_state(snapshot)
            protect_finalization = not _verification_can_start(job, snapshot)
            if verification_deadline["collectionDeadlineReached"] or protect_finalization:
                verification = _verification_fallback(snapshot, _load_full_drilldown_results(db, job))
                _apply_verification_statuses(snapshot, verification)
                _set_helper_stage(
                    snapshot,
                    "verification",
                    status_value=(
                        "skipped_finalization_reserve"
                        if protect_finalization and not verification_deadline["collectionDeadlineReached"]
                        else "skipped_deadline"
                    ),
                )
                runtime = _audit_runtime(snapshot)
                runtime["schedulerPhase"] = "finalization"
                runtime["stopReason"] = (
                    "hard_deadline_reached"
                    if verification_deadline["hardDeadlineReached"]
                    else (
                        "collection_deadline_reached"
                        if verification_deadline["collectionDeadlineReached"]
                        else "finalization_reserve_protected"
                    )
                )
                mark_scheduler_progress(snapshot, action=runtime["stopReason"])
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "generate_answer"
                job.stage_attempt = 0
                job.progress_percent = 78
                timings["verificationOpenrouterMs"] = 0
                timings["totalElapsedMs"] = max(
                    0,
                    round((_now() - _as_aware(job.created_at or _now())).total_seconds() * 1000),
                )
                job.timings_json = _json_dump(timings)
                job.stage_version += 1
                db.commit()
                db.refresh(job)
                return job
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
                verification = _verification_fallback(snapshot, _load_full_drilldown_results(db, job))
                _apply_verification_statuses(snapshot, verification)
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
                job.current_stage = "plan_next_investigation_round"
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
                verification, valid_verification, parsing = _parse_verifications(
                    str(response.get("content") or ""), snapshot, _load_full_drilldown_results(db, job),
                )
                _apply_verification_statuses(snapshot, verification)
                if snapshot.get("investigationRounds"):
                    snapshot["investigationRounds"][-1]["verification_results"] = _active_verifications(snapshot)
                for item in verification.verifications:
                    _log_audit_event(
                        "AUDIT_HYPOTHESIS_VERIFIED", job,
                        round=_audit_runtime(snapshot).get("investigationRound") or 1,
                        hypothesis_id=item.hypothesis_id,
                        status=item.status,
                    )
                    logger.info(
                        "CASCADE_AUDIT_HYPOTHESIS_VERIFIED audit_job_id=%s round=%s hypothesis_id=%s status=%s evidence_count=%s",
                        job.id,
                        _audit_runtime(snapshot).get("investigationRound") or 1,
                        item.hypothesis_id,
                        item.status,
                        len(item.supporting_evidence),
                    )
                if valid_verification:
                    _set_helper_stage(
                        snapshot,
                        "verification",
                        status_value="success",
                        returned_model=returned_model,
                        parsing=parsing,
                    )
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
                        parsing=parsing,
                    )
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = "plan_next_investigation_round"
                job.stage_attempt = 0
                job.progress_percent = 72
                _complete_provider_stage(job, stage)
        elif stage == "plan_next_investigation_round":
            runtime_snapshot = _json_load(job.context_snapshot_json, {})
            runtime = _audit_runtime(runtime_snapshot)
            deadline = scheduler_deadline_state(runtime_snapshot)
            stop_reason = (
                "hard_deadline_reached"
                if deadline["hardDeadlineReached"]
                else "collection_deadline_reached"
                if deadline["collectionDeadlineReached"]
                else round_stop_reason(
                    round_number=int(runtime.get("investigationRound") or 1),
                    pending=len(runtime_snapshot.get("pendingDataRequests") or []),
                    processing=len(runtime_snapshot.get("processingDataRequests") or []),
                    verifications=_active_verifications(runtime_snapshot),
                    request_count=int(runtime.get("requestsCount") or 0),
                    max_rounds=int(runtime.get("maxDepthRounds") or MAX_INVESTIGATION_ROUNDS),
                    max_requests=int(runtime.get("requestSafetyLimit") or MAX_DATA_REQUESTS_PER_AUDIT),
                )
            )
            if stop_reason:
                runtime["stopReason"] = stop_reason
                runtime["schedulerPhase"] = "finalization"
                mark_scheduler_progress(runtime_snapshot, action=stop_reason)
                job.context_snapshot_json = _json_dump(runtime_snapshot)
                job.status = "context_ready"
                job.current_stage = "generate_answer"
                job.progress_percent = 78
            else:
                deterministic_remediation = _validated_diagnostic_remediation_requests(
                    runtime_snapshot,
                )
                if deterministic_remediation:
                    _apply_next_round_requests(runtime_snapshot, deterministic_remediation)
                    runtime = _audit_runtime(runtime_snapshot)
                    _log_audit_event(
                        "AUDIT_NEXT_ROUND_PLANNED",
                        job,
                        round=int(runtime.get("investigationRound") or 1),
                        request_count=len(deterministic_remediation),
                        status="deterministic_remediation",
                    )
                    mark_scheduler_progress(
                        runtime_snapshot,
                        action="deterministic_remediation_planned",
                        successful=True,
                    )
                    job.context_snapshot_json = _json_dump(runtime_snapshot)
                    job.status = "context_ready"
                    job.current_stage = "collect_live_data"
                    job.stage_attempt = 0
                    job.progress_percent = 68
                    timings["totalElapsedMs"] = max(
                        0,
                        round(
                            (
                                _now()
                                - _as_aware(job.started_at or job.created_at or _now())
                            ).total_seconds()
                            * 1000
                        ),
                    )
                    job.timings_json = _json_dump(timings)
                    job.stage_version += 1
                    db.commit()
                    db.refresh(job)
                    _log_timing(job, stage)
                    return job
                execution_token = _claim_provider_stage(db, job, stage, progress_percent=74)
                snapshot = _json_load(job.context_snapshot_json, {})
                prompt = build_next_round_prompt(snapshot)
                prompt_metadata = _save_stage_prompt_metadata(
                    job,
                    stage,
                    prompt,
                    model=AI_AUDIT_HELPER_MODEL,
                    max_tokens=AI_AUDIT_PLANNER_MAX_TOKENS,
                    max_tokens_cap=AI_AUDIT_PLANNER_MAX_TOKENS,
                )
                runtime = _audit_runtime(snapshot)
                runtime["nextRoundPromptTokensEstimated"] = int(prompt_metadata["estimatedInputTokens"] or 0)
                _record_provider_attempt(snapshot, "helper")
                job.context_snapshot_json = _json_dump(snapshot)
                db.commit()
                openrouter_started_at = perf_counter()
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
                        db, job_id, organization_id, stage=stage, execution_token=execution_token,
                    )
                    if not owns_result:
                        return job
                    snapshot = _json_load(job.context_snapshot_json, {})
                    next_requests = _second_round_requests(snapshot)
                    _append_helper_fallback(
                        snapshot,
                        job_id=job.id,
                        stage=stage,
                        stage_name="next_round_planner",
                        code="next_round_planner_fallback_used",
                        message="AI-планировщик следующего раунда недоступен; используется backend fallback.",
                        reason=_helper_fallback_reason(helper_exc),
                        elapsed_ms=_elapsed_ms(openrouter_started_at),
                        prompt_tokens=int((_audit_runtime(snapshot).get("nextRoundPromptTokensEstimated") or 0)),
                    )
                    valid_plan = False
                    plan = None
                else:
                    job, owns_result = _reload_stage_owner(
                        db, job_id, organization_id, stage=stage, execution_token=execution_token,
                    )
                    if not owns_result:
                        return job
                    snapshot = _json_load(job.context_snapshot_json, {})
                    _record_provider_response(snapshot, response)
                    returned_model = str(response.get("model") or AI_AUDIT_HELPER_MODEL)
                    _audit_models(snapshot, job.model)["next_round_planner_returned_model"] = returned_model
                    plan, valid_plan, parsing = _parse_next_round_plan(str(response.get("content") or ""))
                    next_requests: list[AuditDataRequest] = []
                    rejected_requests: list[AuditDataRequestResult] = []
                    if valid_plan and plan is not None:
                        next_requests, rejected_requests = _next_round_requests_from_plan(snapshot, plan)
                        if plan.continue_investigation and not next_requests:
                            valid_plan = False
                    if not valid_plan:
                        next_requests = _second_round_requests(snapshot)
                        _append_helper_fallback(
                            snapshot,
                            job_id=job.id,
                            stage=stage,
                            stage_name="next_round_planner",
                            code="next_round_planner_fallback_used",
                            message="AI-планировщик вернул невалидный следующий раунд; используется backend fallback.",
                            reason="invalid_json_or_semantics",
                            elapsed_ms=_elapsed_ms(openrouter_started_at),
                            prompt_tokens=int((_audit_runtime(snapshot).get("nextRoundPromptTokensEstimated") or 0)),
                            parsing=parsing,
                        )
                    else:
                        _set_helper_stage(
                            snapshot,
                            "next_round_planner",
                            status_value="success",
                            returned_model=returned_model,
                            parsing=parsing,
                        )
                        snapshot["nextRoundPlan"] = plan.model_dump(mode="json")
                        if rejected_requests:
                            rejected_payloads = [item.model_dump(mode="json") for item in rejected_requests]
                            full_results = _merge_full_drilldown_results(
                                _load_full_drilldown_results(db, job), rejected_payloads,
                            )
                            _save_full_drilldown_results(db, job, full_results)
                            _refresh_drilldown_projections(snapshot, full_results)
                if next_requests:
                    _apply_next_round_requests(snapshot, next_requests)
                    _log_audit_event(
                        "AUDIT_NEXT_ROUND_PLANNED", job,
                        round=int((_audit_runtime(snapshot).get("investigationRound") or 1)) + 1,
                        request_count=len(next_requests), status="pending",
                    )
                    next_stage = "collect_live_data"
                    progress = 68
                else:
                    runtime = _audit_runtime(snapshot)
                    stop_reason = (
                        plan.stop_reason if valid_plan and plan is not None and not plan.continue_investigation
                        else "low_expected_information_gain"
                    )
                    runtime["stopReason"] = stop_reason
                    _log_audit_event(
                        "AUDIT_INVESTIGATION_STOPPED", job,
                        round=runtime.get("investigationRound") or 1,
                        stop_reason=stop_reason,
                    )
                    if snapshot.get("investigationRounds"):
                        snapshot["investigationRounds"][-1]["stop_reason"] = stop_reason
                        snapshot["investigationRounds"][-1]["completed_at"] = _now().isoformat()
                    next_stage = "generate_answer"
                    progress = 78
                    _audit_runtime(snapshot)["schedulerPhase"] = "finalization"
                job.context_snapshot_json = _json_dump(snapshot)
                job.status = "context_ready"
                job.current_stage = next_stage
                job.stage_attempt = 0
                job.progress_percent = progress
                _complete_provider_stage(job, stage)
        elif stage == "apply_next_investigation_round":
            snapshot = _json_load(job.context_snapshot_json, {})
            deadline = scheduler_deadline_state(snapshot)
            next_requests = [
                AuditDataRequest.model_validate(item)
                for item in snapshot.pop("fallbackNextRoundRequests", [])
            ]
            if next_requests and not deadline["collectionDeadlineReached"]:
                _apply_next_round_requests(snapshot, next_requests)
            else:
                runtime = _audit_runtime(snapshot)
                runtime["stopReason"] = (
                    "hard_deadline_reached"
                    if deadline["hardDeadlineReached"]
                    else "collection_deadline_reached"
                    if deadline["collectionDeadlineReached"]
                    else "low_expected_information_gain"
                )
                runtime["schedulerPhase"] = "finalization"
                next_requests = []
            job.context_snapshot_json = _json_dump(snapshot)
            job.status = "context_ready"
            job.current_stage = "collect_live_data" if next_requests else "generate_answer"
            job.stage_attempt = 0
            job.progress_percent = 68 if next_requests else 78
        elif stage == "generate_answer":
            snapshot = _json_load(job.context_snapshot_json, {})
            _audit_runtime(snapshot)["schedulerPhase"] = "finalization"
            policy_active = (
                snapshot.get("policyVersion") == AUDIT_EVIDENCE_POLICY_VERSION
                or "evidenceCoverageRegistry" in snapshot
            )
            full_results = _load_full_drilldown_results(db, job) if policy_active else []
            if policy_active:
                all_evidence_results = _load_full_evidence_results(db, job)
                coverage = refresh_evidence_coverage_registry(snapshot, all_evidence_results)
                reconcile_collected_audit_evidence(snapshot, all_evidence_results)
                coverage = refresh_evidence_coverage_registry(snapshot, all_evidence_results)
                runtime = _sync_policy_runtime(snapshot, coverage)
                runtime["completionGateRuns"] = int(runtime.get("completionGateRuns") or 0) + 1
            else:
                coverage = {"completionState": "legacy_unknown"}
                runtime = _audit_runtime(snapshot)

            if (
                policy_active
                and coverage.get("completionState") == "blocked_missing_evidence"
                and runtime.get("schedulerPhase") == "finalization"
                and not runtime.get("completionGateRemediationAttempted")
            ):
                # The scheduler already stopped read collection before finalization.
                # Keep the limitation public, but allow the final model to explain
                # the partial evidence instead of silently replacing it with a
                # generic backend report.
                runtime["completionGateLimitedByScheduler"] = True
                coverage = {**coverage, "completionState": "partial_coverage"}

            if policy_active and coverage.get("completionState") == "blocked_missing_evidence":
                remediation_attempted = bool(runtime.get("completionGateRemediationAttempted"))
                if not remediation_attempted and runtime.get("schedulerPhase") != "finalization":
                    used_requests = int(runtime.get("requestsCount") or 0)
                    request_limit = int(runtime.get("requestSafetyLimit") or MAX_AUDIT_DATA_REQUESTS)
                    remaining_budget = max(0, request_limit - used_requests)
                    remediation, policy_rejections, _ = merge_mandatory_and_ai_requests(
                        snapshot,
                        [],
                        request_budget=remaining_budget,
                    )
                    existing_keys = {
                        (
                            str(item.get("campaign_name") or ""),
                            str(item.get("capability_id") or item.get("dimension") or ""),
                        )
                        for item in (snapshot.get("validatedDataRequests") or [])
                        if isinstance(item, dict)
                    }
                    remediation = [
                        item
                        for item in remediation
                        if (item.campaign_name, item.capability_id or item.dimension) not in existing_keys
                    ]
                    accepted, rejected = validate_audit_data_requests(
                        remediation, max_requests=request_limit,
                    )
                    runtime["completionGateRemediationAttempted"] = True
                    if policy_rejections or rejected:
                        rejected_payloads = [_policy_rejection_result(item) for item in policy_rejections]
                        rejected_payloads.extend(item.model_dump(mode="json") for item in rejected)
                        full_results = _merge_full_drilldown_results(full_results, rejected_payloads)
                        _save_full_drilldown_results(db, job, full_results)
                        _refresh_drilldown_projections(snapshot, full_results)
                    if accepted:
                        _apply_next_round_requests(snapshot, accepted)
                        refreshed = refresh_evidence_coverage_registry(
                            snapshot, _load_full_evidence_results(db, job),
                        )
                        _sync_policy_runtime(snapshot, refreshed)
                        job.context_snapshot_json = _json_dump(snapshot)
                        job.status = "context_ready"
                        job.current_stage = "collect_live_data"
                        job.stage_attempt = 0
                        job.progress_percent = 68
                        timings["completionGateMs"] = _elapsed_ms(started_at)
                        timings["totalElapsedMs"] = max(
                            0,
                            round((_now() - _as_aware(job.created_at or _now())).total_seconds() * 1000),
                        )
                        job.timings_json = _json_dump(timings)
                        job.stage_version += 1
                        db.commit()
                        db.refresh(job)
                        return job

                coverage = refresh_evidence_coverage_registry(
                    snapshot, _load_full_evidence_results(db, job),
                )
                _sync_policy_runtime(snapshot, coverage)
                diagnostics = {
                    "finalCompactionLevel": None,
                    "fitsModelContext": None,
                    "preflightFitsModelContext": None,
                    "completionGateBlocked": True,
                }
                return _complete_backend_fallback_stage(
                    db,
                    job,
                    snapshot,
                    diagnostics,
                    timings,
                    reason_code="mandatory_evidence_blocked",
                    final_status="backend_fallback_missing_mandatory_evidence",
                    warning=(
                        "Часть обязательных данных недоступна или не поместилась в безопасный бюджет запросов. "
                        "Аудит завершён с ограничениями без уверенных причинных выводов по этим сигналам."
                    ),
                    preserve_job_error=False,
                )

            final_deadline = scheduler_deadline_state(snapshot)
            final_provider_budget = _remaining_final_provider_seconds(snapshot)
            if final_deadline["hardDeadlineReached"] or (
                final_provider_budget is not None and final_provider_budget <= 0
            ):
                runtime = _audit_runtime(snapshot)
                runtime["schedulerPhase"] = "finalization"
                runtime["stopReason"] = "hard_deadline_reached"
                runtime["deadlineReached"] = True
                return _complete_backend_fallback_stage(
                    db,
                    job,
                    snapshot,
                    {
                        "finalCompactionLevel": None,
                        "fitsModelContext": None,
                        "preflightFitsModelContext": None,
                        "hardDeadlineReached": True,
                    },
                    timings,
                    reason_code="audit_hard_deadline_reached",
                    final_status="backend_fallback_after_audit_deadline",
                    warning=(
                        "Временной бюджет полного аудита завершён. Собранные данные сохранены, "
                        "а результат сформирован backend без новых запросов к Яндекс.Директу."
                    ),
                    preserve_job_error=False,
                    complete_immediately=True,
                )

            execution_token = _claim_provider_stage(db, job, stage, progress_percent=82)
            input_options = _json_load(job.input_options_json, {}) or {}
            is_compact_retry = bool(input_options.get("compact_retry"))
            final_bundle = build_final_audit_prompt_bundle(
                snapshot,
                job,
                compact_retry=is_compact_retry,
            )
            effective_final_max_tokens = _effective_final_output_tokens(job)
            effective_final_model = _effective_final_model(job)
            prompt = str(final_bundle.get("prompt") or "")
            final_diagnostics = dict(final_bundle.get("diagnostics") or {})
            _save_stage_prompt_metadata(
                job,
                stage,
                prompt,
                model=effective_final_model,
                max_tokens=effective_final_max_tokens,
                max_tokens_cap=FINAL_AUDIT_PROVIDER_MAX_TOKENS,
            )
            _record_final_generation_diagnostics(
                snapshot,
                job,
                final_diagnostics,
                status_value="compact_retry_prepared" if is_compact_retry else "prepared",
            )
            if not final_diagnostics.get("fitsModelContext"):
                return _complete_backend_fallback_stage(
                    db,
                    job,
                    snapshot,
                    final_diagnostics,
                    timings,
                    reason_code="final_prompt_too_large",
                    final_status="backend_fallback",
                    warning=(
                        "Финальная проекция не поместилась в контекст выбранной модели; "
                        "сохранён безопасный backend-результат без вызова OpenRouter."
                    ),
                )
            _record_final_generation_diagnostics(
                snapshot,
                job,
                final_diagnostics,
                status_value="calling_provider_compact" if is_compact_retry else "calling_provider",
            )
            _record_provider_attempt(snapshot, "final")
            job.context_snapshot_json = _json_dump(snapshot)
            db.commit()
            openrouter_started_at = perf_counter()
            try:
                response = await _call_audit_provider(
                    stage, effective_final_model, prompt, max_tokens=effective_final_max_tokens,
                    max_tokens_cap=FINAL_AUDIT_PROVIDER_MAX_TOKENS,
                    timeout=AUDIT_STAGE_PROVIDER_TIMEOUTS[stage],
                    total_timeout_seconds=final_provider_budget,
                )
            except Exception as provider_exc:
                timeout_code = final_provider_timeout_code(provider_exc)
                if timeout_code:
                    job, owns_result = _reload_stage_owner(
                        db,
                        job_id,
                        organization_id,
                        stage=stage,
                        execution_token=execution_token,
                    )
                    if not owns_result:
                        return job
                    snapshot = _json_load(job.context_snapshot_json, {}) or {}
                    if not _prepare_saved_evidence_for_final_fallback(db, job, snapshot):
                        raise provider_exc
                    final_diagnostics.update({
                        "providerTimedOut": True,
                        "providerErrorCode": timeout_code,
                    })
                    timings["finalAnswerOpenrouterMs"] = _elapsed_ms(openrouter_started_at)
                    return _complete_backend_fallback_stage(
                        db,
                        job,
                        snapshot,
                        final_diagnostics,
                        timings,
                        reason_code=FINAL_PROVIDER_TIMEOUT_WARNING_CODE,
                        final_status="backend_fallback_after_provider_timeout",
                        warning=(
                            "Финальная модель не завершила ответ за отведённое время. Использован "
                            "безопасный backend-отчёт."
                        ),
                        provider_error_code=timeout_code,
                        warning_code=FINAL_PROVIDER_TIMEOUT_WARNING_CODE,
                        warning_retryable=True,
                        complete_immediately=True,
                    )
                if not is_provider_context_overflow(provider_exc):
                    raise
                final_diagnostics["providerContextRejected"] = True
                final_diagnostics["providerContextErrorCode"] = PROVIDER_CONTEXT_OVERFLOW_CODE
                _record_final_generation_diagnostics(
                    snapshot,
                    job,
                    final_diagnostics,
                    status_value=PROVIDER_CONTEXT_OVERFLOW_CODE,
                )
                current_level = int(final_diagnostics.get("finalCompactionLevel") or 0)
                if current_level >= 3:
                    timings["finalAnswerOpenrouterMs"] = _elapsed_ms(openrouter_started_at)
                    return _complete_backend_fallback_stage(
                        db,
                        job,
                        snapshot,
                        final_diagnostics,
                        timings,
                        reason_code=PROVIDER_CONTEXT_OVERFLOW_CODE,
                        final_status="backend_fallback_after_provider_context_rejection",
                        warning=(
                            "Данные аудита собраны, но провайдер отклонил фактический размер L3-контекста; "
                            "расширенный AI-текст заменён безопасным backend-результатом."
                        ),
                    )

                retry_bundle = build_final_audit_prompt_bundle(
                    snapshot,
                    job,
                    compact_retry=True,
                    minimum_compaction_level=current_level + 1,
                )
                prompt = str(retry_bundle.get("prompt") or "")
                retry_diagnostics = dict(retry_bundle.get("diagnostics") or {})
                retry_diagnostics["providerContextRejected"] = True
                retry_diagnostics["providerContextErrorCode"] = PROVIDER_CONTEXT_OVERFLOW_CODE
                final_diagnostics = retry_diagnostics
                _save_stage_prompt_metadata(
                    job,
                    stage,
                    prompt,
                    model=effective_final_model,
                    max_tokens=effective_final_max_tokens,
                    max_tokens_cap=FINAL_AUDIT_PROVIDER_MAX_TOKENS,
                )
                _record_final_generation_diagnostics(
                    snapshot,
                    job,
                    final_diagnostics,
                    status_value="retrying_after_provider_context_rejection",
                )
                if not final_diagnostics.get("fitsModelContext"):
                    timings["finalAnswerOpenrouterMs"] = _elapsed_ms(openrouter_started_at)
                    return _complete_backend_fallback_stage(
                        db,
                        job,
                        snapshot,
                        final_diagnostics,
                        timings,
                        reason_code=PROVIDER_CONTEXT_OVERFLOW_CODE,
                        final_status="backend_fallback_after_provider_context_rejection",
                        warning=(
                            "Данные аудита собраны, но более компактная финальная проекция не поместилась "
                            "в безопасный бюджет; сохранён backend-результат."
                        ),
                    )
                retry_provider_budget = _remaining_final_provider_seconds(snapshot)
                if retry_provider_budget is not None and retry_provider_budget <= 0:
                    timings["finalAnswerOpenrouterMs"] = _elapsed_ms(openrouter_started_at)
                    return _complete_backend_fallback_stage(
                        db,
                        job,
                        snapshot,
                        final_diagnostics,
                        timings,
                        reason_code="audit_hard_deadline_reached",
                        final_status="backend_fallback_after_audit_deadline",
                        warning=(
                            "Временной бюджет аудита завершён до повторного вызова модели. "
                            "Использован безопасный backend-отчёт по уже собранным данным."
                        ),
                        preserve_job_error=False,
                        complete_immediately=True,
                    )
                _record_provider_attempt(snapshot, "final")
                job.context_snapshot_json = _json_dump(snapshot)
                db.commit()
                try:
                    response = await _call_audit_provider(
                        stage, effective_final_model, prompt, max_tokens=effective_final_max_tokens,
                        max_tokens_cap=FINAL_AUDIT_PROVIDER_MAX_TOKENS,
                        timeout=AUDIT_STAGE_PROVIDER_TIMEOUTS[stage],
                        total_timeout_seconds=retry_provider_budget,
                    )
                except Exception as retry_exc:
                    timeout_code = final_provider_timeout_code(retry_exc)
                    if timeout_code:
                        job, owns_result = _reload_stage_owner(
                            db,
                            job_id,
                            organization_id,
                            stage=stage,
                            execution_token=execution_token,
                        )
                        if not owns_result:
                            return job
                        snapshot = _json_load(job.context_snapshot_json, {}) or {}
                        if not _prepare_saved_evidence_for_final_fallback(db, job, snapshot):
                            raise retry_exc
                        final_diagnostics.update({
                            "providerTimedOut": True,
                            "providerErrorCode": timeout_code,
                        })
                        timings["finalAnswerOpenrouterMs"] = _elapsed_ms(openrouter_started_at)
                        return _complete_backend_fallback_stage(
                            db,
                            job,
                            snapshot,
                            final_diagnostics,
                            timings,
                            reason_code=FINAL_PROVIDER_TIMEOUT_WARNING_CODE,
                            final_status="backend_fallback_after_provider_timeout",
                            warning=(
                                "Финальная модель не завершила компактный ответ за отведённое время. "
                                "Использован безопасный backend-отчёт."
                            ),
                            provider_error_code=timeout_code,
                            warning_code=FINAL_PROVIDER_TIMEOUT_WARNING_CODE,
                            warning_retryable=True,
                            complete_immediately=True,
                        )
                    if not is_provider_context_overflow(retry_exc):
                        raise
                    final_diagnostics["providerContextRejected"] = True
                    final_diagnostics["providerContextErrorCode"] = PROVIDER_CONTEXT_OVERFLOW_CODE
                    timings["finalAnswerOpenrouterMs"] = _elapsed_ms(openrouter_started_at)
                    return _complete_backend_fallback_stage(
                        db,
                        job,
                        snapshot,
                        final_diagnostics,
                        timings,
                        reason_code=PROVIDER_CONTEXT_OVERFLOW_CODE,
                        final_status="backend_fallback_after_provider_context_rejection",
                        warning=(
                            "Данные аудита собраны, но провайдер повторно отклонил компактный контекст; "
                            "расширенный AI-текст заменён безопасным backend-результатом."
                        ),
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
            _record_final_generation_diagnostics(
                snapshot,
                job,
                final_diagnostics,
                status_value="provider_response_received",
            )
            final_returned_model = str(response.get("model") or job.model)
            _audit_models(snapshot, job.model)["final_returned_model"] = final_returned_model
            job.context_snapshot_json = _json_dump(snapshot)
            answer = str(response.get("content") or "")
            finish_reason = str(response.get("finish_reason") or "") or None
            _record_final_generation_diagnostics(
                snapshot,
                job,
                final_diagnostics,
                status_value="validating_schema",
            )
            structured, parsing = _validate_structured_result_with_metadata(
                answer,
                snapshot=snapshot,
                job=job,
                response=response,
                finish_reason=finish_reason,
            )
            truncated = finish_reason == "length"
            final_token_usage = _safe_provider_token_usage(response)
            provider_response_metadata = {
                "sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest() if answer else None,
                "length": len(answer),
                "sourceFormat": parsing["sourceFormat"],
                "fullResponseStored": False,
            }
            job.returned_model = final_returned_model
            if structured is None and not truncated:
                initial_parsing = _safe_model_response_parsing(parsing)
                initial_response_metadata = dict(provider_response_metadata)
                repair_timeout = _final_schema_repair_timeout(job, snapshot)
                schema_repair = {
                    "attempted": False,
                    "status": "skipped_stage_time_budget" if repair_timeout is None else "pending",
                    "initialParsing": initial_parsing,
                    "initialResponse": initial_response_metadata,
                }
                if repair_timeout is not None:
                    repair_prompt, repair_diagnostics = _build_final_schema_repair_prompt(snapshot, job)
                    if repair_diagnostics.get("fitsModelContext"):
                        schema_repair["attempted"] = True
                        schema_repair["status"] = "calling_provider"
                        final_diagnostics["schemaRepair"] = {
                            "attempted": True,
                            "promptEstimatedTokens": repair_diagnostics.get("finalPromptEstimatedTokens"),
                            "compactionLevel": repair_diagnostics.get("finalCompactionLevel"),
                        }
                        _save_stage_prompt_metadata(
                            job,
                            stage,
                            repair_prompt,
                            model=AI_AUDIT_HELPER_MODEL,
                            max_tokens=effective_final_max_tokens,
                            max_tokens_cap=FINAL_AUDIT_PROVIDER_MAX_TOKENS,
                        )
                        _record_final_generation_diagnostics(
                            snapshot,
                            job,
                            final_diagnostics,
                            status_value="repairing_invalid_provider_response",
                        )
                        _record_provider_attempt(snapshot, "final")
                        job.context_snapshot_json = _json_dump(snapshot)
                        db.commit()
                        try:
                            repair_response = await _call_audit_provider(
                                stage,
                                AI_AUDIT_HELPER_MODEL,
                                repair_prompt,
                                max_tokens=effective_final_max_tokens,
                                max_tokens_cap=FINAL_AUDIT_PROVIDER_MAX_TOKENS,
                                timeout=repair_timeout,
                                total_timeout_seconds=_remaining_final_provider_seconds(snapshot),
                            )
                        except Exception as repair_exc:
                            schema_repair["status"] = "provider_error"
                            schema_repair["errorCode"] = final_provider_timeout_code(repair_exc) or type(repair_exc).__name__
                            logger.warning(
                                "AI_AUDIT_FINAL_SCHEMA_REPAIR_FAILED job_id=%s error_code=%s",
                                job.id,
                                schema_repair["errorCode"],
                            )
                        else:
                            _record_provider_response(snapshot, repair_response)
                            response = repair_response
                            answer = str(response.get("content") or "")
                            finish_reason = str(response.get("finish_reason") or "") or None
                            final_returned_model = str(response.get("model") or AI_AUDIT_HELPER_MODEL)
                            _audit_models(snapshot, job.model)["final_schema_repair_returned_model"] = final_returned_model
                            job.returned_model = final_returned_model
                            structured, parsing = _validate_structured_result_with_metadata(
                                answer,
                                snapshot=snapshot,
                                job=job,
                                response=response,
                                finish_reason=finish_reason,
                            )
                            truncated = finish_reason == "length"
                            final_token_usage = _safe_provider_token_usage(response)
                            provider_response_metadata = {
                                "sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest() if answer else None,
                                "length": len(answer),
                                "sourceFormat": parsing["sourceFormat"],
                                "fullResponseStored": False,
                            }
                            schema_repair.update({
                                "status": "recovered" if structured is not None else "invalid_response",
                                "returnedModel": final_returned_model,
                                "response": provider_response_metadata,
                                "parsing": _safe_model_response_parsing(parsing),
                            })
                    else:
                        schema_repair["status"] = "skipped_context_budget"
                final_diagnostics["schemaRepair"] = schema_repair
                _record_final_generation_diagnostics(
                    snapshot,
                    job,
                    final_diagnostics,
                    status_value="schema_repair_completed" if structured is not None else "schema_repair_unavailable",
                )
                parsing_error_code = str(parsing.get("errorCode") or "json_parse_failed")
                schema_failed = parsing_error_code == "json_schema_validation_failed"
                fallback_status = (
                    "backend_fallback_after_schema_validation"
                    if schema_failed
                    else "backend_fallback_after_json_parse"
                )
                fallback_warning = (
                    "Ответ модели не прошёл структурный контракт. Данные аудита сохранены, показан "
                    "безопасный backend-отчёт без повторных внешних запросов."
                    if schema_failed
                    else "Ответ модели не удалось безопасно разобрать. Данные аудита сохранены, показан "
                    "backend-отчёт без повторных внешних запросов."
                )
                if structured is None and not truncated:
                    return _complete_backend_fallback_stage(
                        db,
                        job,
                        snapshot,
                        final_diagnostics,
                        timings,
                        reason_code=parsing_error_code,
                        final_status=fallback_status,
                        warning=fallback_warning,
                        model_response_parsing=parsing,
                        provider_response_metadata=provider_response_metadata,
                        finish_reason=finish_reason,
                        final_token_usage=final_token_usage,
                        preserve_job_error=False,
                    )
            _record_final_generation_diagnostics(
                snapshot,
                job,
                final_diagnostics,
                status_value="provider_completed" if structured is not None else "provider_response_truncated",
            )
            mark_scheduler_progress(snapshot, action="final_provider_completed", successful=True)
            job.context_snapshot_json = _json_dump(snapshot)
            warnings = _helper_warning_messages(snapshot)
            if not (snapshot.get("analysisPeriod") or {}).get("requestedMatchesAvailableData"):
                warnings.append("Фактический период отличается от запрошенного или доступен не полностью.")
            if not structured:
                warnings.append("Модель вернула результат в неподдерживаемом формате; основной интерфейс показывает только безопасные метаданные.")
            if truncated:
                warnings.append("Ответ модели достиг лимита и мог быть обрезан.")
            fallback_markdown = None if structured else _UNSUPPORTED_AUDIT_FORMAT_MESSAGE
            job.answer_text = build_audit_answer_markdown(structured, snapshot) if structured else fallback_markdown
            evidence_coverage = public_evidence_coverage(snapshot)
            job.result_json = _json_dump({
                "structured": structured,
                "fallbackMarkdown": fallback_markdown,
                "technicalResponse": None,
                "structuredParsing": parsing,
                "providerResponseMetadata": provider_response_metadata,
                "warnings": warnings,
                "finishReason": finish_reason,
                "truncated": truncated,
                "compactRetryAvailable": truncated,
                "backendFallbackUsed": False,
                "completeness": (
                    "truncated"
                    if truncated
                    else evidence_coverage["completionState"]
                    if (
                        snapshot.get("evidenceCoverageRegistry")
                        or evidence_coverage["completionState"] == "partial_coverage"
                    )
                    else ("structured" if structured else "fallback")
                ),
                "auditCompletionState": evidence_coverage["completionState"],
                "evidenceCoverage": evidence_coverage,
                "analysisPeriod": snapshot.get("analysisPeriod") or {},
                "periodEvidenceLimitations": snapshot.get("periodEvidenceLimitations") or [],
                "cachePolicy": (snapshot.get("metadata") or {}).get("cachePolicy") or "fresh",
                "directApiKnowledgeVersion": (snapshot.get("metadata") or {}).get("directApiKnowledgeVersion"),
                "dataCoverage": snapshot.get("dataCoverage") or {},
                "canonicalEvidenceCoverage": snapshot.get("canonicalEvidenceCoverage") or {},
                "finalOutputEvidenceReconciliation": snapshot.get("finalOutputEvidenceReconciliation") or {},
                "usage": final_token_usage,
                "finalTokenUsage": final_token_usage,
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
        if job.context_snapshot_json and (
            job.current_stage != stage or job.status in TERMINAL_AUDIT_STATUSES
        ) and job.current_stage != "wait_for_offline_reports":
            progress_snapshot = _json_load(job.context_snapshot_json, {}) or {}
            mark_scheduler_progress(
                progress_snapshot,
                action=f"stage_completed:{stage}",
                successful=True,
            )
            job.context_snapshot_json = _json_dump(progress_snapshot)
        timings["totalElapsedMs"] = max(
            0,
            round(
                (_now() - _as_aware(job.started_at or job.created_at or _now())).total_seconds()
                * 1000
            ),
        )
        job.timings_json = _json_dump(timings)
        job.stage_version += 1
        logger.info("AI_AUDIT_ADVANCE_COMMIT_START job_id=%s stage=%s next_stage=%s", job.id, stage, job.current_stage)
        db.commit()
        db.refresh(job)
        logger.info("AI_AUDIT_ADVANCE_COMMIT_DONE job_id=%s stage=%s next_stage=%s", job.id, stage, job.current_stage)
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
    if recover_stale_audit_job(job, _now(), db=db):
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
    recovered = recover_stale_audit_job(job, _now(), db=db)
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
