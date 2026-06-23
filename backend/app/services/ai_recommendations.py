import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import normalize_ai_request_options, settings
from app.db import SessionLocal
from app.models import ClientAccount, ClientBusinessContext, ConnectedAccount, OptimizationActionDraft, SyncJob
from app.schemas import AiGeneratedRecommendation, AiRecommendationResponse
from app.services.direct_analyst_playbook import build_direct_analyst_instructions
from app.services.mock_data import AUDIT_ISSUES, CAMPAIGNS, CLIENTS, RECOMMENDATIONS
from app.services.ai_output_validation import structured_to_legacy_recommendations, validate_structured_recommendation_payload
from app.services.ai_prompt_debug import build_prompt_debug_snapshot
from app.services.knowledge_base import select_knowledge_snippets
from app.services.openrouter import DEFAULT_SYSTEM_PROMPT, generate_openrouter_response
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


def _business_context_dict(context: ClientBusinessContext | None) -> dict[str, Any]:
    if not context:
        return {
            "status": "empty",
            "message": "Контекст бизнеса не заполнен. Попросите пользователя заполнить раздел «Контекст бизнеса».",
            "fields": {},
        }
    fields = {
        "brand_name": context.brand_name,
        "business_niche": context.business_niche,
        "product_summary": context.product_summary,
        "target_audience": context.target_audience,
        "geography": context.geography,
        "seasonality": context.seasonality,
        "main_offers": context.main_offers,
        "conversion_actions": context.conversion_actions,
        "average_order_value": context.average_order_value,
        "lead_value_notes": context.lead_value_notes,
        "business_constraints": context.business_constraints,
        "negative_topics": context.negative_topics,
        "landing_page_notes": context.landing_page_notes,
        "competitor_notes": context.competitor_notes,
        "ai_summary": context.ai_summary,
        "manual_notes": context.manual_notes,
        "memory_notes": context.memory_notes,
        "source_notes": context.source_notes,
    }
    filled = {key: value for key, value in fields.items() if str(value or "").strip()}
    return {
        "status": "good" if len(filled) >= 6 else "partial" if filled else "empty",
        "filled_fields_count": len(filled),
        "message": "Контекст бизнеса доступен." if filled else "Контекст бизнеса не заполнен.",
        "fields": filled,
        "updated_at": context.updated_at.isoformat() if context.updated_at else None,
    }


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
                    f"Расход {item.get('cost')} ₽, конверсии по целям {item.get('goal_conversions')}, "
                    f"CPA по целям {item.get('cpa_used')}, CTR {item.get('ctr')}"
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
            "sync_diagnostics": summary.get("syncDiagnostics") if summary else {},
        },
        "yandex_direct_audit": summary.get("yandexDirectAudit") if summary else {},
        "yesterday_campaign_summary": summary.get("yesterdayCampaignSummary") if summary else {},
        "direct_analyst_playbook": build_direct_analyst_instructions(summary or {}),
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
    business_context = db.scalar(select(ClientBusinessContext).where(ClientBusinessContext.client_id == client_id))
    business_context_payload = _business_context_dict(business_context)
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
    context_payload = {
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
        "business_context": business_context_payload,
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
        "sync_diagnostics": summary.get("syncDiagnostics", {}),
        "search_query_insights": summary.get("searchQueryInsights", {}),
        "yesterday_campaign_summary": summary.get("yesterdayCampaignSummary", {}),
        "yandex_direct_audit": summary.get("yandexDirectAudit", {}),
        "direct_analyst_playbook": build_direct_analyst_instructions({
            "summary": summary,
            "business_context": business_context_payload,
            "goals": {"selected_goal_ids": summary.get("selectedGoalIds", [])},
        }),
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
            "execution_preview": {
                "available_for_statuses": ["approved", "reviewed"],
                "ready_count": action_counts.get("approved", 0) + action_counts.get("reviewed", 0),
                "can_apply": False,
                "apply_enabled": False,
                "message": "Execution preview is informational only. Approved drafts were not applied to Yandex Direct.",
            },
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
            "message": "Все действия являются черновиками и требуют approval. Предпросмотр применения только информационный. Изменения в Яндекс.Директ не применялись.",
        },
    }
    return _context_with_knowledge(context_payload)


def _knowledge_query_from_context(context: dict[str, Any]) -> str:
    parts = [
        str(context.get("user_request") or ""),
        str(context.get("message") or ""),
        str(context.get("selected_campaign_name") or ""),
    ]
    summary = context.get("summary") or {}
    if isinstance(summary, dict):
        parts.extend(
            [
                "yesterday summary" if summary.get("yesterdayCampaignSummary") else "",
                "search query insights" if summary.get("searchQueryInsights") else "",
                "goal conversions" if summary.get("selectedGoalIds") else "",
            ]
        )
    return " ".join(item for item in parts if item)


def _context_with_knowledge(context: dict[str, Any], query: str | None = None) -> dict[str, Any]:
    existing = context.get("knowledge_snippets")
    if existing:
        return context
    snippets = select_knowledge_snippets(query or _knowledge_query_from_context(context), context, limit=5)
    return {**context, "knowledge_snippets": snippets}


def _format_knowledge_snippets(snippets: list[dict[str, str]]) -> str:
    if not snippets:
        return "Нет выбранных фрагментов базы знаний."
    return "\n\n".join(
        (
            f"Источник: {item.get('source')}\n"
            f"Раздел: {item.get('title')}\n"
            f"{item.get('content')}"
        )
        for item in snippets[:5]
    )


def _build_prompt(context: dict[str, Any]) -> str:
    context = _context_with_knowledge(context)
    playbook = build_direct_analyst_instructions(context)
    knowledge_snippets = context.get("knowledge_snippets") or []
    return f"""
Сформируй 3 проверяемые AI-рекомендации для PPC-специалиста DirectPilot AI.
Используй методику DirectPilot ниже. Сохраняй порядок анализа: качество данных → цели → обзор аккаунта → сегменты кампаний → проблемы → черновики действий.

Методика DirectPilot:
{playbook}

База знаний DirectPilot:
{_format_knowledge_snippets(knowledge_snippets)}

Yandex Direct audit skill:
- If yandex_direct_audit is present, use audit score, grade, category scores, failed checks, quick wins, and limitations before generic advice.
- Treat N/A and needs_more_data checks as limitations, not confirmed failures.
- Never claim unavailable account settings were checked.

Yesterday campaign summary:
- If yesterday_campaign_summary.hasData is true, use it for operational daily analysis.
- Focus on selected goal conversions, CPA by goals, CTR, cost, clicks, and campaign issue flags for yesterday.
- If only yesterday data is available, do not claim trend. Say that trend/dynamics data is not loaded.
- Use business_context when available: brand, niche, seasonality, conversion actions, and negative topics.

Правила:
- Сначала используй business_context: бренд, нишу, офферы, сезонность, ограничения, negative_topics и память проекта.
- Если business_context пустой, явно попроси заполнить раздел «Контекст бизнеса» и не выдумывай нишу, бренд, сезонность или посадочные.
- При анализе поисковых запросов учитывай negative_topics как запрещённые/нерелевантные направления.
- Не выдумывай goal conversions.
- Используй selected Direct goal conversions как основной источник, если они доступны.
- Если данные по выбранным целям недоступны, явно скажи, что анализ CPA ограничен и нужна проверка ID целей.
- Изменения в Яндекс.Директ не применялись.
- Рекомендации являются черновиками действий и требуют review/approval.
- Приоритизируй кампании по выбранной цели, если goal data доступна.
- Если ai_model_settings.preset = economy, отвечай кратко; если advanced, можно дать более глубокую структуру.

Верни строго JSON без markdown по контракту DirectPilot AI:
{{
  "summary": "string",
  "confidence": "low|medium|high",
  "riskLevel": "low|medium|high",
  "missingData": ["string"],
  "findings": [
    {{
      "type": "string",
      "entityType": "account|campaign|ad_group|keyword|search_query|goal|landing|unknown",
      "entityId": "string|null",
      "entityName": "string|null",
      "metric": "string|null",
      "problem": "string",
      "evidence": "string",
      "recommendation": "string",
      "risk": "low|medium|high"
    }}
  ],
  "actions": [
    {{
      "type": "review_campaign|review_search_queries|review_goals|review_landing|prepare_negative_keywords|prepare_budget_change|prepare_bid_change|request_more_data",
      "entityType": "account|campaign|ad_group|keyword|search_query|goal|landing|unknown",
      "entityId": "string|null",
      "description": "string",
      "requiresHumanApproval": true
    }}
  ],
  "safetyNotes": ["string"]
}}

Контракт обязателен:
- Все actions должны быть только черновиками и всегда requiresHumanApproval=true.
- Не добавляй действий, которые выглядят как применение изменений в Яндекс.Директ.
- Если данных не хватает, заполни missingData и добавь action type=request_more_data.
- Если фрагмент базы знаний указывает на ограничение данных, добавь это в missingData или safetyNotes.
- Если выбран режим economy, summary и findings должны быть короче; advanced может быть подробнее.

Контекст клиента:
{json.dumps(context, ensure_ascii=False, indent=2)}
""".strip()


def build_recommendation_prompt_debug_snapshot(
    *,
    context: dict[str, Any],
    model: str | None,
    ai_preset: str | None = None,
    max_tokens: int | None = None,
    include_preview: bool = False,
) -> dict[str, Any]:
    ai_options = normalize_ai_request_options(
        model=model,
        ai_preset=ai_preset,
        max_tokens=max_tokens,
        models=settings.openrouter_models,
        configured_default=settings.openrouter_default_model,
    )
    context_with_model = {
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
    prompt = _build_prompt(context_with_model)
    return build_prompt_debug_snapshot(
        context=context_with_model,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=str(ai_options["model"]),
        max_tokens=int(ai_options["max_tokens"]),
        include_preview=include_preview,
    )


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
                f"Конверсии по целям: {top.get('goal_conversions', top.get('conversions_used'))}",
                f"CPA по целям: {top.get('cpa_used', '—')}",
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


def _prompt_too_large_response(context: dict[str, Any], model: str, debug_snapshot: dict[str, Any]) -> AiRecommendationResponse:
    sections = debug_snapshot.get("sections") or []
    top_sections = sections[:3]
    evidence = [
        f"{item.get('name')}: ~{item.get('estimatedTokens')} tokens, {item.get('chars')} chars"
        for item in top_sections
    ] or ["Не удалось определить крупнейшие секции контекста."]
    size = debug_snapshot.get("size") or {}
    warning = (
        f"Estimated total tokens: {size.get('estimatedTotalTokens')}; "
        f"context limit: {size.get('contextLimit')}; largest sections: "
        + ", ".join(item.get("name", "unknown") for item in top_sections)
    )
    return AiRecommendationResponse(
        client_id=context["client"]["id"],
        source="prompt_budget_guard",
        model=model,
        summary=(
            "Контекст слишком большой для выбранной модели. Сократите период, выберите конкретную кампанию "
            "или используйте сжатый контекст."
        ),
        recommendations=[
            AiGeneratedRecommendation(
                title="Сократить AI-контекст",
                evidence=evidence,
                risk="medium",
                expected_impact="AI-запрос станет меньше и сможет пройти лимит контекста выбранной модели.",
                next_step=(
                    "Выберите конкретную кампанию, уменьшите период или ограничьте поисковые запросы "
                    "перед повторным анализом."
                ),
                requires_approval=False,
            )
        ],
        validation_warnings=[warning],
        raw_response=None,
        error=True,
        error_code="ai_prompt_too_large",
        message=(
            "Контекст слишком большой для выбранной модели. Сократите период, выберите конкретную кампанию "
            "или используйте сжатый контекст."
        ),
        retryable=False,
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
    prompt = _build_prompt(context)
    prompt_debug = build_prompt_debug_snapshot(
        context=context,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=selected_model,
        max_tokens=int(ai_options["max_tokens"]),
        include_preview=False,
    )
    if prompt_debug["size"]["isTooLarge"]:
        return _prompt_too_large_response(context, selected_model, prompt_debug)

    try:
        response = await generate_openrouter_response(
            model=selected_model,
            prompt=prompt,
            max_tokens=int(ai_options["max_tokens"]),
        )
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
        structured_output, validation_warnings = validate_structured_recommendation_payload(parsed)
        recommendations = structured_to_legacy_recommendations(structured_output)
        summary = structured_output.summary
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        fallback = _fallback_recommendations(context)
        fallback.source = "fallback_after_parse_error"
        fallback.model = str(response.get("model") or selected_model)
        fallback.summary = f"Модель ответила неструктурированно, поэтому показан fallback. Ошибка разбора: {exc}"
        fallback.raw_response = raw_content
        fallback.validation_warnings = [
            "Structured output validation failed. Fallback recommendations are draft/manual review only."
        ]
        return fallback

    return AiRecommendationResponse(
        client_id=context["client"]["id"],
        source="openrouter",
        model=str(response.get("model") or selected_model),
        summary=summary,
        recommendations=recommendations,
        structured_output=structured_output,
        validation_warnings=validation_warnings,
        raw_response=raw_content,
    )
