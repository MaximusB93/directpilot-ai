from app.services.ai_output_validation import (
    structured_to_legacy_recommendations,
    validate_structured_recommendation_payload,
)


def test_structured_recommendation_payload_validates_and_maps_to_legacy():
    structured, warnings = validate_structured_recommendation_payload(
        {
            "summary": "Нужно проверить кампанию с расходом без конверсий.",
            "confidence": "high",
            "riskLevel": "medium",
            "missingData": ["поисковые запросы"],
            "findings": [
                {
                    "type": "spend_without_conversions",
                    "entityType": "campaign",
                    "entityId": "123",
                    "entityName": "Search",
                    "metric": "goal_conversions",
                    "problem": "Расход есть, конверсий по целям нет.",
                    "evidence": "Расход 3200 ₽, конверсии по целям 0.",
                    "recommendation": "Проверить запросы и посадочную.",
                    "risk": "high",
                }
            ],
            "actions": [
                {
                    "type": "review_campaign",
                    "entityType": "campaign",
                    "entityId": "123",
                    "description": "Проверить кампанию вручную.",
                    "requiresHumanApproval": True,
                }
            ],
            "safetyNotes": ["Изменения в Директ не применялись."],
        }
    )

    assert warnings == []
    assert structured.confidence == "high"
    assert structured.findings[0].entityType == "campaign"
    assert structured.actions[0].requiresHumanApproval is True

    legacy = structured_to_legacy_recommendations(structured)
    assert legacy[0].requires_approval is True
    assert "Расход есть" in legacy[0].title


def test_structured_recommendation_normalizes_unknown_values_and_forces_approval():
    structured, warnings = validate_structured_recommendation_payload(
        {
            "summary": "Черновик.",
            "confidence": "certain",
            "riskLevel": "extreme",
            "findings": [
                {
                    "type": "unknown",
                    "entityType": "ad",
                    "problem": "Нужна проверка.",
                    "evidence": "Недостаточно данных.",
                    "recommendation": "Запросить данные.",
                    "risk": "critical",
                }
            ],
            "actions": [
                {
                    "type": "pause_campaign_now",
                    "entityType": "campaign",
                    "description": "Остановить кампанию.",
                    "requiresHumanApproval": False,
                },
                {
                    "type": "prepare_negative_keywords",
                    "entityType": "search_query",
                    "description": "Подготовить минус-слова.",
                    "requiresHumanApproval": False,
                },
            ],
        }
    )

    assert structured.confidence == "medium"
    assert structured.riskLevel == "medium"
    assert structured.findings[0].entityType == "unknown"
    assert structured.findings[0].risk == "medium"
    assert structured.actions[0].type == "request_more_data"
    assert structured.actions[0].requiresHumanApproval is True
    assert structured.actions[1].requiresHumanApproval is True
    assert any("Unknown action type" in item for item in warnings)
    assert any("requires human approval" in item for item in warnings)
