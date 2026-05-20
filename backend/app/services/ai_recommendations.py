import json
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.db import SessionLocal
from app.schemas import AiGeneratedRecommendation, AiRecommendationResponse
from app.services.mock_data import AUDIT_ISSUES, CAMPAIGNS, CLIENTS, RECOMMENDATIONS
from app.services.openrouter import generate_openrouter_response
from app.services.performance_summary import build_performance_summary


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


def _build_prompt(context: dict[str, Any]) -> str:
    return f"""
Сформируй 3 проверяемые AI-рекомендации для PPC-специалиста DirectPilot AI.
Правила:
- Не выдумывай goal conversions.
- Если goal data недоступна, явно скажи это.
- Изменения в Яндекс.Директ не применялись.
- Рекомендации являются черновиками действий и требуют review/approval.
- Приоритизируй кампании по выбранной цели, если goal data доступна.

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


async def generate_client_recommendations(
    client_id: str,
    model: str | None = None,
    client_context: dict[str, Any] | None = None,
) -> AiRecommendationResponse:
    context = build_client_ai_context(client_id, client_context=client_context)
    if not settings.openrouter_configured:
        return _fallback_recommendations(context)

    selected_model = model or settings.openrouter_default_model
    response = await generate_openrouter_response(model=selected_model, prompt=_build_prompt(context))
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
