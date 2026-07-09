from __future__ import annotations

from app.ai.evals.loader import load_eval_cases


def test_all_ai_eval_cases_load_and_validate() -> None:
    cases = load_eval_cases()

    assert len(cases) >= 5
    assert len({case.id for case in cases}) == len(cases)
    for case in cases:
        assert case.title.strip()
        assert case.input_data
        assert case.expected.should_find or case.expected.should_not_do


def test_ai_eval_dataset_contains_initial_safety_scenarios() -> None:
    cases = {case.id: case for case in load_eval_cases()}

    assert {
        "001_high_cpa",
        "002_spend_without_conversions",
        "003_low_data_volume",
        "004_good_campaign_do_not_touch",
        "005_tracking_issue_suspected",
    }.issubset(cases)
    assert all(case.expected.should_not_do for case in cases.values())
    assert cases["003_low_data_volume"].expected.risk_level == "low"
    assert cases["004_good_campaign_do_not_touch"].expected.risk_level == "low"
