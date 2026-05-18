import json
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.schemas import AiGeneratedRecommendation, AiRecommendationResponse
from app.services.mock_data import AUDIT_ISSUES, CAMPAIGNS, CLIENTS, RECOMMENDATIONS
from app.services.openrouter import generate_openrouter_response


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _find_client(client_id: str) -> Any:
    for client in CLIENTS:
        if client.id == client_id:
            return client
    raise HTTPException(status_code=404, detail="Client not found")


def build_client_ai_context(client_id: str) -> dict[str, Any]:
    client = _find_client(client_id)
    return {
        "client": _dump_model(client),
        "campaigns": [_dump_model(campaign) for campaign in CAMPAIGNS],
        "audit_issues": [_dump_model(issue) for issue in AUDIT_ISSUES],
        "existing_recommendations": [_dump_model(recommendation) for recommendation in RECOMMENDATIONS],
        "guardrails": {
            "allowed_actions": ["audit", "explain", "create_draft", "create_dry_run_preview"],
            "forbidden_actions": ["apply_changes_without_approval", "increase_total_budget_without_client_approval"],
            "approval_required_for": ["budget_change", "strategy_change", "bulk_pause", "new_ads_launch"],
        },
    }


def _build_prompt(context: dict[str, Any]) -> str:
    return f"""
Сформируй 3 проверяемые AI-рекомендации для PPC-специалиста DirectPilot AI.

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
    recommendations = [
        AiGeneratedRecommendation(
            title="Проверить расход без конверсий в РСЯ",
            evidence=["Кампания «РСЯ | Широкие интересы» потратила 48 700 ₽", "В кампании зафиксировано 0 лидов"],
            risk="low",
            expected_impact="Снижение wasted spend до проверки целей и поисковых запросов",
            next_step="Создать dry-run preview на ограничение бюджета и список объектов для ручной проверки",
            requires_approval=True,
        ),
        AiGeneratedRecommendation(
            title="Сверить цели Метрики перед оптимизацией CPA",
            evidence=["В аудите отмечено, что не все кампании связаны с целями Метрики", "Текущий AI score клиента: %s/100" % client["score"]],
            risk="medium",
            expected_impact="Более точный расчёт CPA и меньше ложных рекомендаций",
            next_step="Подключить цели заявки, звонка, корзины и покупки; затем пересчитать рекомендации",
            requires_approval=False,
        ),
        AiGeneratedRecommendation(
            title="Подготовить A/B-тест объявлений в поиске",
            evidence=["12 объявлений имеют CTR ниже медианы аккаунта на 31%", "В офферах не используется сильное УТП"],
            risk="low",
            expected_impact="Потенциальный рост CTR на 10–15% без изменения бюджета",
            next_step="Сгенерировать черновики объявлений и отправить специалисту на approval",
            requires_approval=True,
        ),
    ]
    return AiRecommendationResponse(
        client_id=client["id"],
        source="deterministic_fallback",
        model=None,
        summary=f"OpenRouter не настроен, поэтому показан безопасный локальный черновик для клиента «{client['name']}».",
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


async def generate_client_recommendations(client_id: str, model: str | None = None) -> AiRecommendationResponse:
    context = build_client_ai_context(client_id)
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
