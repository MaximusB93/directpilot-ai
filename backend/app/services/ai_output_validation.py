from __future__ import annotations

from typing import Any

from app.schemas import AiGeneratedRecommendation, AiStructuredRecommendation

VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_RISK = {"low", "medium", "high"}
VALID_ENTITY_TYPES = {"account", "campaign", "ad_group", "keyword", "search_query", "goal", "landing", "unknown"}
VALID_ACTION_TYPES = {
    "review_campaign",
    "review_search_queries",
    "review_goals",
    "review_landing",
    "prepare_negative_keywords",
    "prepare_budget_change",
    "prepare_bid_change",
    "request_more_data",
}
YANDEX_WRITE_LIKE_ACTIONS = {"prepare_negative_keywords", "prepare_budget_change", "prepare_bid_change"}


def _as_string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_string(item) for item in value if _as_string(item)]


def _risk(value: Any, warnings: list[str], field_name: str) -> str:
    risk = _as_string(value, "medium").lower()
    if risk not in VALID_RISK:
        warnings.append(f"{field_name} was normalized to medium.")
        return "medium"
    return risk


def _entity_type(value: Any, warnings: list[str]) -> str:
    entity_type = _as_string(value, "unknown").lower()
    if entity_type not in VALID_ENTITY_TYPES:
        warnings.append(f"Unknown entityType '{entity_type}' was normalized to unknown.")
        return "unknown"
    return entity_type


def _action_type(value: Any, warnings: list[str]) -> str:
    action_type = _as_string(value, "request_more_data").lower()
    if action_type not in VALID_ACTION_TYPES:
        warnings.append(f"Unknown action type '{action_type}' was normalized to request_more_data.")
        return "request_more_data"
    return action_type


def validate_structured_recommendation_payload(payload: dict[str, Any]) -> tuple[AiStructuredRecommendation, list[str]]:
    """Normalize model output into a safe DirectPilot recommendation contract."""

    warnings: list[str] = []
    if not isinstance(payload, dict):
        raise ValueError("Structured recommendation payload must be a JSON object.")

    confidence = _as_string(payload.get("confidence"), "medium").lower()
    if confidence not in VALID_CONFIDENCE:
        warnings.append("confidence was normalized to medium.")
        confidence = "medium"

    findings = []
    for index, item in enumerate(payload.get("findings") or []):
        if not isinstance(item, dict):
            warnings.append(f"finding #{index + 1} was skipped because it is not an object.")
            continue
        findings.append(
            {
                "type": _as_string(item.get("type"), "general"),
                "entityType": _entity_type(item.get("entityType"), warnings),
                "entityId": _as_string(item.get("entityId")) or None,
                "entityName": _as_string(item.get("entityName")) or None,
                "metric": _as_string(item.get("metric")) or None,
                "problem": _as_string(item.get("problem"), "Нужна ручная проверка."),
                "evidence": _as_string(item.get("evidence"), "Недостаточно структурированных данных."),
                "recommendation": _as_string(item.get("recommendation"), "Проверить вручную перед любыми действиями."),
                "risk": _risk(item.get("risk"), warnings, "finding.risk"),
            }
        )

    actions = []
    for index, item in enumerate(payload.get("actions") or []):
        if not isinstance(item, dict):
            warnings.append(f"action #{index + 1} was skipped because it is not an object.")
            continue
        action_type = _action_type(item.get("type"), warnings)
        if action_type in YANDEX_WRITE_LIKE_ACTIONS and item.get("requiresHumanApproval") is not True:
            warnings.append(f"{action_type} requires human approval and was forced to true.")
        actions.append(
            {
                "type": action_type,
                "entityType": _entity_type(item.get("entityType"), warnings),
                "entityId": _as_string(item.get("entityId")) or None,
                "description": _as_string(item.get("description"), "Запросить дополнительные данные и проверить вручную."),
                "requiresHumanApproval": True,
            }
        )
    if not findings and not actions:
        warnings.append("No usable findings or actions were returned; request_more_data action was added.")
        actions.append(
            {
                "type": "request_more_data",
                "entityType": "unknown",
                "entityId": None,
                "description": "Проверить входные данные и повторить анализ по структурированному контракту.",
                "requiresHumanApproval": True,
            }
        )

    missing_data = _as_string_list(payload.get("missingData"))
    safety_notes = _as_string_list(payload.get("safetyNotes"))
    if not safety_notes:
        safety_notes.append("Все рекомендации являются черновиками. Изменения в Яндекс.Директ не применялись.")

    structured = AiStructuredRecommendation(
        summary=_as_string(payload.get("summary"), "Модель вернула структурированный черновик рекомендаций."),
        confidence=confidence,
        riskLevel=_risk(payload.get("riskLevel"), warnings, "riskLevel"),
        missingData=missing_data,
        findings=findings,
        actions=actions,
        safetyNotes=safety_notes,
    )
    return structured, warnings


def structured_to_legacy_recommendations(structured: AiStructuredRecommendation) -> list[AiGeneratedRecommendation]:
    recommendations: list[AiGeneratedRecommendation] = []
    for finding in structured.findings[:5]:
        recommendations.append(
            AiGeneratedRecommendation(
                title=finding.problem,
                evidence=[finding.evidence],
                risk=finding.risk,
                expected_impact="Уточняется после ручной проверки и подтверждения данных.",
                next_step=finding.recommendation,
                requires_approval=True,
            )
        )
    if not recommendations and structured.actions:
        action = structured.actions[0]
        recommendations.append(
            AiGeneratedRecommendation(
                title="Нужна ручная проверка",
                evidence=structured.missingData or ["Модель не вернула отдельных findings."],
                risk=structured.riskLevel,
                expected_impact="Повысить качество анализа после уточнения данных.",
                next_step=action.description,
                requires_approval=True,
            )
        )
    return recommendations
