import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import normalize_ai_request_options, settings
from app.db import SessionLocal
from app.models import ClientAccount, ConnectedAccount, OptimizationActionDraft, SyncJob
from app.schemas import AiGeneratedRecommendation, AiRecommendationResponse
from app.services.mock_data import AUDIT_ISSUES, CAMPAIGNS, CLIENTS, RECOMMENDATIONS
from app.services.openrouter import generate_openrouter_response
from app.services.performance_summary import build_optimization_plan, build_performance_summary

AI_RATE_LIMIT_MESSAGE = "Выбранная AI-модель временно перегружена или ограничена по лимитам. Выберите другую модель или повторите позже."


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _find_client(client_id: str) -> Any:
    for client in CLIENTS:
        if client.id == client_id:
            return client
    raise HTTPException(status_code=404, detail="Client not found")


def _summary_context(client_id: str) -> dict[str, Any] | None:
    if SessionLocal is None:
        return None
    with SessionLocal() as db:
        try:
            summary = build_performance_summary(db=db, client_id=client_id)
        except ValueError:
            return None
    return summary if summary.get("campaigns") else None


def build_client_ai_context(client_id: str, client_context: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = _summary_context(client_id)
    if summary:
        client = summary["client"]
        campaigns = summary["campaigns"]
        audit_issues = [
            {
                "priority": "high" if "spend_without_conversions" in item.get("issue_flags", []) else "medium",
                "title": f"Проверка кампании {item.get('campaign_name')}",
                "object": item.get("campaign_name"),
                "evidence": (
                    f"Расход {item.get('cost')} ₽, total conversions {item.get('total_conversions')}, "
                    f"goal conversions {item.get('goal_conversions')}, используется {item.get('conversions_used')} "
                    f"({item.get('conversion_source')}), CPA {item.get('cpa_used')}, flags {item.get('issue_flags')}"
                ),
                "action": item.get("recommended_focus") or "Проверить ставки и отправить изменение на preview/approval.",
            }
            for item in campaigns[:5]
        ]
        existing_recommendations = []
    elif client_context:
        client = {**client_context, "id": client_context.get("id") or client_id}
        campaigns = []
        audit_issues = []
        existing_recommendations = []
    else:
        client = _dump_model(_find_client(client_id))
        campaigns = [_dump_model(campaign) for campaign in CAMPAIGNS]
        audit_issues = [_dump_model(issue) for issue in AUDIT_ISSUES]
        existing_recommendations = [_dump_model(recommendation) for recommendation in RECOMMENDATIONS]
    return {
        "client": client,
        "campaigns": campaigns,
        "audit_issues": audit_issues,
        "existing_recommendations": existing_recommendations,
        "conversion_context": {
            "selected_goal_id": summary.get("selectedGoalId") if summary else None,
            "has_goal_data": summary.get("hasGoalData") if summary else False,
            "goal_conversions_total": summary.get("goalConversionsTotal") if summary else 0,
            "conversions_source_message": summary.get("conversionsSourceMessage") if summary else "Нет сохранённой статистики.",
        },
        "guardrails": {
            "allowed_actions": ["audit", "explain", "create_draft", "create_dry_run_preview"],
            "forbidden_actions": ["apply_changes_without_approval", "increase_total_budget_without_client_approval"],
            "approval_required_for": ["budget_change", "strategy_change", "bulk_pause", "new_ads_launch"],
        },
    }


def build_client_ai_context_from_db(db, client_id: str, selected_campaign_name: str | None = None) -> dict[str, Any]:
    client = db.get(ClientAccount, client_id)
    if not client:
        raise ValueError("Client not found")
    summary = build_performance_summary(db, client_id)
    plan = build_optimization_plan(db, client_id)
    latest_sync_job = db.scalar(
        select(SyncJob)
        .where(SyncJob.client_id == client_id)
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )
    bound_account = db.get(ConnectedAccount, client.yandex_account_id) if client.yandex_account_id else None
    saved_actions = db.scalars(
        select(OptimizationActionDraft)
        .where(
            OptimizationActionDraft.client_id == client_id,
            OptimizationActionDraft.organization_id == client.organization_id,
        )
        .order_by(OptimizationActionDraft.updated_at.desc())
    ).all()
    action_counts = {status: 0 for status in ["draft", "reviewed", "approved", "rejected", "needs_changes"]}
    for action in saved_actions:
        action_counts[action.status] = action_counts.get(action.status, 0) + 1
    campaigns = summary.get("campaigns", [])
    selected_campaign = None
    if selected_campaign_name:
        selected_campaign = next((item for item in campaigns if item.get("campaign_name") == selected_campaign_name), None)
        campaigns = [selected_campaign] if selected_campaign else campaigns
    warnings = list(summary.get("goalDataWarnings") or [])
    if client.conversion_goal_ids is None and client.main_goal_id is None:
        warnings.append("ID целей Метрики не указаны.")
    return {
        "client": {
            "id": client.id,
            "name": client.name,
            "direct_login": client.direct_login,
            "metrica_counter": client.metrica_counter,
            "main_goal_id": client.main_goal_id,
            "conversion_goal_ids": client.conversion_goal_ids,
            "target_cpa": client.target_cpa,
            "notes": client.notes,
            "sync_status": client.sync_status,
            "sync_error": client.sync_error,
            "last_synced_at": client.last_synced_at.isoformat() if client.last_synced_at else None,
            "sync_version": client.sync_version,
        },
        "yandex_binding": {
            "bound": bound_account is not None,
            "account": (
                {
                    "id": bound_account.id,
                    "provider": bound_account.provider,
                    "status": bound_account.status,
                    "login": bound_account.login,
                    "display_name": bound_account.display_name,
                    "connected_at": bound_account.connected_at.isoformat() if bound_account.connected_at else None,
                    "updated_at": bound_account.updated_at.isoformat() if bound_account.updated_at else None,
                }
                if bound_account
                else None
            ),
            "message": "Yandex account is bound to this client." if bound_account else "Yandex account is not bound to this client.",
        },
        "latest_sync_job": (
            {
                "id": latest_sync_job.id,
                "source_type": latest_sync_job.source_type,
                "status": latest_sync_job.status,
                "period_from": latest_sync_job.period_from.isoformat() if latest_sync_job.period_from else None,
                "period_to": latest_sync_job.period_to.isoformat() if latest_sync_job.period_to else None,
                "rows_loaded": latest_sync_job.rows_loaded,
                "error": latest_sync_job.error,
                "started_at": latest_sync_job.started_at.isoformat() if latest_sync_job.started_at else None,
                "finished_at": latest_sync_job.finished_at.isoformat() if latest_sync_job.finished_at else None,
                "created_at": latest_sync_job.created_at.isoformat() if latest_sync_job.created_at else None,
            }
            if latest_sync_job
            else None
        ),
        "goals": {
            "selected_goal_ids": summary.get("selectedGoalIds", []),
            "has_goal_data": summary.get("hasGoalData", False),
            "source_message": summary.get("conversionsSourceMessage"),
        },
        "summary": summary,
        "campaigns": campaigns,
        "diagnostics": [
            {
                "campaign_name": item.get("campaign_name"),
                "severity": item.get("severity"),
                "flags": item.get("issue_flags"),
                "explanation": item.get("diagnostic_explanation"),
                "recommended_focus": item.get("recommended_focus"),
            }
            for item in campaigns
        ],
        "optimization_plan": plan.get("actions", []),
        "saved_optimization_actions": {
            "total": len(saved_actions),
            "count_by_status": action_counts,
            "approved": [
                {"id": action.id, "campaign_name": action.campaign_name, "issue": action.issue, "comment": action.user_comment}
                for action in saved_actions
                if action.status == "approved"
            ][:5],
            "rejected": [
                {"id": action.id, "campaign_name": action.campaign_name, "issue": action.issue, "comment": action.user_comment}
                for action in saved_actions
                if action.status == "rejected"
            ][:5],
            "needs_changes": [
                {"id": action.id, "campaign_name": action.campaign_name, "issue": action.issue, "comment": action.user_comment}
                for action in saved_actions
                if action.status == "needs_changes"
            ][:5],
            "latest_comments": [
                {"id": action.id, "status": action.status, "comment": action.user_comment}
                for action in saved_actions
                if action.user_comment
            ][:5],
            "safety_note": "Approved means the user approved the draft only. No Yandex Direct changes were applied.",
        },
        "selected_campaign_name": selected_campaign_name,
        "selected_campaign": selected_campaign,
        "warnings": warnings,
        "safety": {
            "no_write_actions": True,
            "message": "Все действия являются черновиками и требуют approval. Изменения в Яндекс.Директ не применялись.",
        },
    }


def _build_prompt(context: dict[str, Any]) -> str:
    return f"""
Сформируй 3 проверяемые AI-рекомендации для PPC-специалиста DirectPilot AI.
Правила:
- Не выдумывай goal conversions.
- Если goal data недоступна, явно скажи это.
- Изменения в Яндекс.Директ не применялись.
- Рекомендации являются черновиками действий и требуют review/approval.
- Приоритизируй кампании по выбранной цели, если goal data доступна.
- Если ai_model_settings.preset = economy, отвечай кратко; если advanced, можно дать более глубокую структуру.

Верни строго JSON без markdown в формате:
{{
  "summary": "краткая сводка",
  "recommendations": [
    {{
      "title": "...",
      "evidence": ["факт 1", "факт 2"],
      "risk": "low|medium|high",
      "expected_impact": "...",
      "next_step": "...",
      "requires_approval": true
    }}
  ]
}}

Контекст клиента:
{json.dumps(context, ensure_ascii=False, indent=2)}
""".strip()


def _fallback_recommendations(context: dict[str, Any]) -> AiRecommendationResponse:
    client = context["client"]
    campaigns = context.get("campaigns") or []
    totals_cost = sum(float(item.get("cost", 0) or 0) for item in campaigns) if campaigns else 0.0
    totals_clicks = sum(int(float(item.get("clicks", 0) or 0)) for item in campaigns) if campaigns else 0
    totals_conversions = sum(float(item.get("conversions_used", item.get("conversions", 0)) or 0) for item in campaigns) if campaigns else 0.0

    if (not campaigns) or (totals_cost == 0 and totals_clicks == 0 and totals_conversions == 0):
        recommendations = [
            AiGeneratedRecommendation(
                title="Недостаточно данных для оптимизации",
                evidence=["Нет сохранённых данных Яндекс.Директа по выбранному клиенту"],
                risk="low",
                expected_impact="Невозможно оценить до загрузки реальных данных",
                next_step="Подключите Яндекс.Директ и запустите синхронизацию",
                requires_approval=False,
            )
        ]
        return AiRecommendationResponse(
            client_id=client["id"],
            source="deterministic_fallback",
            model=None,
            summary="Недостаточно данных: рекомендации по оптимизации кампаний пока недоступны.",
            recommendations=recommendations,
            raw_response=None,
        )

    top = sorted(campaigns, key=lambda x: float(x.get("cost", 0)), reverse=True)[0]
    recommendations = [
        AiGeneratedRecommendation(
            title=f"Проверить кампанию «{top.get('campaign_name', top.get('name', 'Без названия'))}»",
            evidence=[
                f"Расход: {top.get('cost')} ₽",
                f"Конверсии используются: {top.get('conversions_used', top.get('conversions'))}",
                f"Источник конверсий: {top.get('conversion_source', 'unknown')}",
                f"CTR: {top.get('ctr')}%",
            ],
            risk="medium",
            expected_impact="Снижение неэффективного расхода и стабилизация CPA",
            next_step="Подготовить preview изменений и отправить на approval",
            requires_approval=True,
        )
    ]
    return AiRecommendationResponse(
        client_id=client["id"],
        source="deterministic_fallback",
        model=None,
        summary=f"OpenRouter не настроен, показан безопасный черновик для клиента «{client.get('name', client['id'])}».",
        recommendations=recommendations,
        raw_response=None,
    )


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON object not found in OpenRouter response")
    return json.loads(stripped[start : end + 1])


def _is_rate_limit_error(exc: HTTPException) -> bool:
    detail = exc.detail
    text = json.dumps(detail, ensure_ascii=False).lower() if isinstance(detail, (dict, list)) else str(detail).lower()
    return exc.status_code == 429 or "429" in text or "rate limit" in text or "rate-limited" in text or "temporarily rate" in text


def normalize_openrouter_error(exc: HTTPException, model: str) -> dict[str, object] | None:
    if not _is_rate_limit_error(exc):
        return None
    return {
        "error": True,
        "error_code": "openrouter_rate_limited",
        "message": AI_RATE_LIMIT_MESSAGE,
        "model": model,
        "retryable": True,
        "suggested_preset": "economy",
    }


async def generate_client_recommendations(
    client_id: str,
    model: str | None = None,
    client_context: dict[str, Any] | None = None,
) -> AiRecommendationResponse:
    context = build_client_ai_context(client_id, client_context=client_context)
    return await generate_client_recommendations_from_context(context=context, model=model)


async def generate_client_recommendations_from_context(
    context: dict[str, Any],
    model: str | None = None,
    ai_preset: str | None = None,
    max_tokens: int | None = None,
) -> AiRecommendationResponse:
    ai_options = normalize_ai_request_options(
        model=model,
        ai_preset=ai_preset,
        max_tokens=max_tokens,
        models=settings.openrouter_models,
        configured_default=settings.openrouter_default_model,
    )
    context = {
        **context,
        "ai_model_settings": {
            "preset": ai_options["ai_preset"],
            "model": ai_options["model"],
            "max_tokens": ai_options["max_tokens"],
            "max_tokens_cap": ai_options["max_tokens_cap"],
            "cost_tier": ai_options["cost_tier"],
            "custom_model": ai_options["is_custom_model"],
        },
    }
    if not settings.openrouter_configured:
        return _fallback_recommendations(context)

    selected_model = str(ai_options["model"])
    try:
        response = await generate_openrouter_response(model=selected_model, prompt=_build_prompt(context))
    except HTTPException as exc:
        normalized = normalize_openrouter_error(exc, selected_model)
        if normalized:
            return AiRecommendationResponse(
                client_id=context["client"]["id"],
                source="openrouter_error_normalized",
                model=selected_model,
                summary=str(normalized["message"]),
                recommendations=[],
                **normalized,
            )
        raise
    raw_content = str(response.get("content", ""))
    try:
        parsed = _extract_json_object(raw_content)
        recommendations = [AiGeneratedRecommendation(**item) for item in parsed.get("recommendations", [])]
        summary = parsed.get("summary") or "OpenRouter сформировал рекомендации по контексту клиента."
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        fallback = _fallback_recommendations(context)
        fallback.source = "fallback_after_parse_error"
        fallback.model = str(response.get("model") or selected_model)
        fallback.summary = f"Модель ответила неструктурированно, поэтому показан fallback. Ошибка разбора: {exc}"
        fallback.raw_response = raw_content
        return fallback

    return AiRecommendationResponse(
        client_id=context["client"]["id"],
        source="openrouter",
        model=str(response.get("model") or selected_model),
        summary=summary,
        recommendations=recommendations,
        raw_response=raw_content,
    )
