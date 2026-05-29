from app.services.yandex_direct_audit_skill import build_yandex_direct_audit, grade_for_score


def test_grade_mapping() -> None:
    assert grade_for_score(95) == "A"
    assert grade_for_score(80) == "B"
    assert grade_for_score(65) == "C"
    assert grade_for_score(50) == "D"
    assert grade_for_score(10) == "F"


def test_audit_excludes_na_checks_from_scoring() -> None:
    summary = {
        "client": {"id": "client-1", "name": "Client", "metrica_counter": "123", "target_cpa": 500},
        "totals": {"cost": 1000, "impressions": 10000, "clicks": 500, "conversions": 10},
        "campaigns": [
            {
                "campaign_name": "Search Brand",
                "cost": 1000,
                "clicks": 500,
                "impressions": 10000,
                "conversions_used": 10,
                "goal_conversions": 10,
                "cpa_used": 100,
                "issue_flags": [],
            }
        ],
        "selectedGoalIds": ["35371875"],
        "hasGoalData": True,
        "conversionsSourceMessage": "Selected Direct goal conversions are used.",
        "syncDiagnostics": {
            "conversionSourceCounts": {"yandex_direct_goals": 1},
            "warnings": [],
        },
        "searchQueryInsights": {"totalQueries": 0, "candidateNegativeKeywords": 0, "totalWasteCost": 0, "insights": []},
    }

    audit = build_yandex_direct_audit(summary)

    assert audit["score"] > 70
    assert audit["categories"][0]["title"] == "Аналитика и цели"
    assert "Оценка аудита Яндекс.Директа" in audit["summary"]
    assert any(item["source"] == "needs_more_data" for item in audit["limitations"])
    assert any(item.get("statusLabel") == "Нужны дополнительные данные" for item in audit["limitations"])
    assert any(
        check.get("statusLabel") in {"Ок", "Требует внимания", "Проблема", "Нужны дополнительные данные"}
        for category in audit["categories"]
        for check in category["checks"]
    )
    assert all("applied" not in item["recommendation"].lower() for item in audit["recommendations"])


def test_critical_fail_lowers_score_and_creates_quick_win() -> None:
    summary = {
        "client": {"id": "client-1", "name": "Client"},
        "totals": {"cost": 5000, "impressions": 10000, "clicks": 100, "conversions": 0},
        "campaigns": [
            {
                "campaign_name": "Search Generic",
                "cost": 5000,
                "clicks": 100,
                "impressions": 10000,
                "conversions_used": 0,
                "goal_conversions": 0,
                "cpa_used": None,
                "issue_flags": ["spend_without_conversions", "low_ctr"],
            }
        ],
        "selectedGoalIds": [],
        "hasGoalData": False,
        "conversionsSourceMessage": "No goal IDs are configured.",
        "syncDiagnostics": {"conversionSourceCounts": {"yandex_direct_total": 1}, "warnings": []},
        "searchQueryInsights": {
            "totalQueries": 10,
            "candidateNegativeKeywords": 6,
            "totalWasteCost": 2500,
            "insights": [],
        },
    }

    audit = build_yandex_direct_audit(summary)

    assert audit["score"] < 70
    assert audit["grade"] in {"C", "D", "F"}
    assert any(item["id"] == "YD02" for item in audit["criticalIssues"])
    assert audit["quickWins"]
