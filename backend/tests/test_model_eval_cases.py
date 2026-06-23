from app.services.model_eval_cases import list_model_eval_cases


def test_model_eval_cases_cover_core_directpilot_scenarios():
    cases = list_model_eval_cases()

    assert len(cases) >= 10
    case_ids = {case["id"] for case in cases}
    assert "campaign_spend_without_goal_conversions" in case_ids
    assert "goal_data_unavailable" in case_ids
    assert "search_query_negative_candidate" in case_ids
    assert "search_query_with_conversions" in case_ids
    assert "yesterday_only_no_trend" in case_ids


def test_model_eval_cases_forbid_apply_and_fake_goal_claims():
    cases = list_model_eval_cases()
    forbidden_text = " ".join(
        " ".join(case.get("forbidden_claims", []))
        for case in cases
    ).lower()

    assert "changes were applied" in forbidden_text
    assert "negative keyword was added" in forbidden_text
    assert "cpa by selected goals is known" in forbidden_text
    assert "total direct conversions are selected goal conversions" in forbidden_text


def test_yesterday_eval_case_prevents_trend_claims_without_dynamics():
    case = next(item for item in list_model_eval_cases() if item["id"] == "yesterday_only_no_trend")

    assert "do not claim trend" in case["expected_behavior"]
    assert "weekly dynamics" in case["expected_missing_data"]
    assert any("trend" in claim.lower() for claim in case["forbidden_claims"])
