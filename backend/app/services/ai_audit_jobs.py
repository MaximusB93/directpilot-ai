import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompt_loader import get_system_prompt_metadata
from app.core.config import (
    DEFAULT_PRODUCTION_AI_MODEL,
    normalize_ai_request_options,
    production_ai_model_ids,
)
from app.models import AiAuditJob, ClientAccount
from app.schemas import AiAuditCreateRequest, AiAuditJobResponse
from app.services.ai_prompt_debug import build_prompt_debug_snapshot, estimate_tokens
from app.services.ai_recommendations import build_client_ai_context_from_db
from app.services.direct_analyst_playbook import build_direct_analyst_instructions
from app.services.knowledge_base import select_knowledge_snippets
from app.services.openrouter import DEFAULT_SYSTEM_PROMPT, generate_openrouter_response

logger = logging.getLogger(__name__)

TERMINAL_AUDIT_STATUSES = {"completed", "failed", "cancelled"}
POLL_AFTER_MS = 1800
CONTEXT_TOKEN_TARGET = 12000
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
        "id": item.get("campaign_id") or item.get("id"),
        "name": item.get("campaign_name") or item.get("name"),
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
        "period": requested_period,
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
            "warnings": warnings,
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
        "campaignsIncluded": sum(len(items) for items in groups.values()),
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
    return snapshot


def build_full_audit_prompt(snapshot: dict[str, Any]) -> str:
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
    return f"""Задача: провести полный read-only аудит Яндекс.Директа по сохранённому compact snapshot DirectPilot.
Scope: {scope_instruction}

{build_direct_analyst_instructions(snapshot)}

Релевантные фрагменты базы знаний:
{knowledge_text or '- Дополнительные фрагменты не выбраны.'}

Compact audit snapshot:
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

Ответь по-русски в компактной Markdown-структуре:
1. Краткий итог.
2. Достаточность и качество данных.
3. До 5 критических проблем.
4. До 5 возможностей.
5. Кампании с недостаточным объёмом данных.
6. Tracking и выбранные цели.
7. Search/РСЯ drill-down только по доступным данным.
8. До 10 безопасных действий.
9. Что нельзя делать автоматически.
10. Ограничения анализа.

Для каждого finding отделяй факт, evidence, гипотезу, рекомендацию, риск и requires_human_approval.
Не повторяй всю статистику. Не выдумывай отсутствующие данные. Все действия — dry-run черновики; изменения в Яндекс.Директ не применялись."""


def _prompt_metadata(prompt: str, job: AiAuditJob) -> dict[str, Any]:
    debug = build_prompt_debug_snapshot(
        context={"auditContextMetadata": (_json_load(job.context_snapshot_json, {}).get("metadata") or {})},
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=job.model,
        max_tokens=job.max_tokens,
        include_preview=False,
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


def _locked_job(db: Session, job_id: str, organization_id: str) -> AiAuditJob:
    job = db.scalar(
        select(AiAuditJob)
        .where(AiAuditJob.id == job_id, AiAuditJob.organization_id == organization_id)
        .with_for_update()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI audit job not found")
    return job


def get_audit_job(db: Session, job_id: str, *, organization_id: str) -> AiAuditJob:
    job = db.scalar(
        select(AiAuditJob).where(AiAuditJob.id == job_id, AiAuditJob.organization_id == organization_id)
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI audit job not found")
    return job


def _context_metadata(job: AiAuditJob) -> dict[str, Any]:
    return (_json_load(job.context_snapshot_json, {}) or {}).get("metadata") or {}


def audit_job_response(job: AiAuditJob) -> AiAuditJobResponse:
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
        result=_json_load(job.result_json, None),
        answer=job.answer_text,
        error_code=job.error_code,
        error_message=job.error_message,
        retryable=job.retryable,
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
    options = normalize_ai_request_options(
        model=payload.model,
        ai_preset=payload.ai_preset,
        max_tokens=payload.max_tokens,
        models=production_ai_model_ids(),
        configured_default=DEFAULT_PRODUCTION_AI_MODEL,
        production_only=True,
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
) -> AiAuditJob:
    job = _locked_job(db, job_id, organization_id)
    if job.status in {"completed", "cancelled"}:
        return job
    if job.status == "failed":
        if not retry or not job.retryable:
            return job
        if job.prompt_snapshot_json:
            job.status = "context_ready"
            job.current_stage = "generate_answer"
        elif job.context_snapshot_json:
            job.status = "context_ready"
            job.current_stage = "build_prompt"
        else:
            job.status = "queued"
            job.current_stage = "collect_context"
        job.error_code = None
        job.error_message = None
        job.retryable = False
        db.commit()
        db.refresh(job)
        return job
    if job.status in {"collecting_context", "generating"}:
        return job

    timings = _json_load(job.timings_json, {})
    stage = job.current_stage
    started_at = perf_counter()
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
            snapshot["metadata"]["estimatedTokens"] = estimate_tokens(_json_dump(snapshot))
            timings["compactContextMs"] = _elapsed_ms(compact_started_at)
            job.context_snapshot_json = _json_dump(snapshot)
            job.status = "context_ready"
            job.current_stage = "build_prompt"
            job.progress_percent = 35
        elif stage == "build_prompt":
            snapshot = _json_load(job.context_snapshot_json, {})
            prompt = build_full_audit_prompt(snapshot)
            metadata = _prompt_metadata(prompt, job)
            if metadata["isTooLarge"]:
                raise HTTPException(
                    status_code=413,
                    detail={"error_code": "ai_prompt_too_large", "message": "Compact audit prompt exceeds model context.", "retryable": False},
                )
            job.prompt_snapshot_json = _json_dump(metadata)
            job.status = "context_ready"
            job.current_stage = "generate_answer"
            job.progress_percent = 55
            timings["buildPromptMs"] = _elapsed_ms(started_at)
        elif stage == "generate_answer":
            job.status = "generating"
            job.progress_percent = 65
            job.stage_version += 1
            db.commit()
            snapshot = _json_load(job.context_snapshot_json, {})
            prompt = build_full_audit_prompt(snapshot)
            expected_hash = (_json_load(job.prompt_snapshot_json, {}) or {}).get("promptHash")
            if expected_hash and hashlib.sha256(prompt.encode("utf-8")).hexdigest() != expected_hash:
                raise RuntimeError("Audit prompt snapshot changed between stages")
            openrouter_started_at = perf_counter()
            response = await generate_openrouter_response(job.model, prompt, max_tokens=job.max_tokens)
            timings["openrouterMs"] = _elapsed_ms(openrouter_started_at)
            answer = str(response.get("content") or "")
            structured = None
            try:
                parsed = json.loads(answer)
                structured = parsed if isinstance(parsed, dict) else None
            except (TypeError, ValueError):
                structured = None
            job.returned_model = str(response.get("model") or job.model)
            job.answer_text = answer
            job.result_json = _json_dump({
                "structured": structured,
                "warnings": [] if structured else ["Модель вернула Markdown/текст; результат сохранён без потери ответа."],
                "usage": response.get("usage"),
                "responseId": response.get("id"),
                "requestTrace": {
                    "jobId": job.id,
                    "model": job.model,
                    "systemPromptVersion": job.system_prompt_version,
                    "systemPromptHash": job.system_prompt_hash[:12],
                    "context": _context_metadata(job),
                },
                "safety": {"readOnly": True, "appliedToYandexDirect": False, "requiresHumanApproval": True},
            })
            job.status = "context_ready"
            job.current_stage = "finalize"
            job.progress_percent = 90
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
        job.timings_json = _json_dump(timings)
        failed = _save_failure(db, job, exc, stage=stage)
        _log_timing(failed, stage)
        return failed


def cancel_audit_job(db: Session, job_id: str, *, organization_id: str) -> AiAuditJob:
    job = _locked_job(db, job_id, organization_id)
    if job.status in {"completed", "cancelled", "generating"}:
        return job
    job.status = "cancelled"
    job.error_code = None
    job.error_message = None
    job.retryable = False
    job.stage_version += 1
    db.commit()
    db.refresh(job)
    return job
