from __future__ import annotations

from typing import Any


DIRECTPILOT_MODEL_EVAL_CASES: list[dict[str, Any]] = [
    {
        "id": "campaign_spend_without_goal_conversions",
        "title": "Campaign spends with zero selected goal conversions",
        "input_context": {
            "selected_goal_ids": ["35371875"],
            "campaigns": [{"name": "Search Brand", "cost": 3200, "clicks": 42, "goal_conversions": 0}],
        },
        "expected_behavior": [
            "flag spend without selected goal conversions",
            "recommend manual campaign review",
            "state that no changes were applied",
        ],
        "expected_missing_data": ["search query details", "landing page context"],
        "forbidden_claims": ["changes were applied", "total Direct conversions are selected goal conversions"],
    },
    {
        "id": "clicks_without_goal_conversions",
        "title": "Ten or more clicks and no selected goal conversions",
        "input_context": {
            "selected_goal_ids": ["35371875", "344527023"],
            "campaigns": [{"name": "Generic Search", "cost": 1800, "clicks": 18, "goal_conversions": 0}],
        },
        "expected_behavior": ["recommend checking search queries, goals, and landing path"],
        "expected_missing_data": ["search query report", "Metrika/Direct goal setup evidence"],
        "forbidden_claims": ["campaign should be paused automatically"],
    },
    {
        "id": "low_data_campaign",
        "title": "Low data campaign",
        "input_context": {
            "selected_goal_ids": ["35371875"],
            "campaigns": [{"name": "New Campaign", "cost": 120, "clicks": 2, "impressions": 80, "goal_conversions": 0}],
        },
        "expected_behavior": ["mark confidence low", "avoid strong optimization conclusions"],
        "expected_missing_data": ["more clicks and impressions"],
        "forbidden_claims": ["statistically significant problem"],
    },
    {
        "id": "good_campaign_acceptable_cpa",
        "title": "Campaign has selected goal conversions below target CPA",
        "input_context": {
            "target_cpa": 1200,
            "selected_goal_ids": ["35371875"],
            "campaigns": [{"name": "Priority Search", "cost": 4800, "clicks": 64, "goal_conversions": 6, "goal_cpa": 800}],
        },
        "expected_behavior": ["identify as opportunity", "recommend cautious scaling review"],
        "expected_missing_data": ["budget constraints"],
        "forbidden_claims": ["budget was increased"],
    },
    {
        "id": "high_ctr_no_conversions",
        "title": "High CTR but no selected goal conversions",
        "input_context": {
            "selected_goal_ids": ["35371875"],
            "campaigns": [{"name": "High CTR Search", "cost": 2500, "clicks": 55, "ctr": 12.5, "goal_conversions": 0}],
        },
        "expected_behavior": ["separate click relevance from conversion quality", "check landing and goal tracking"],
        "expected_missing_data": ["landing page quality", "conversion path"],
        "forbidden_claims": ["traffic is definitely irrelevant"],
    },
    {
        "id": "goal_data_unavailable",
        "title": "Selected goal IDs exist but Direct returned no goal data",
        "input_context": {
            "selected_goal_ids": ["35371875"],
            "sync_diagnostics": {"directGoalDataAvailable": False},
            "campaigns": [{"name": "Search", "cost": 3200, "clicks": 30, "goal_conversions": None}],
        },
        "expected_behavior": ["state goal data is missing", "request goal ID/report setup check"],
        "expected_missing_data": ["selected Direct goal conversions"],
        "forbidden_claims": ["CPA by selected goals is known"],
    },
    {
        "id": "empty_business_context",
        "title": "Business context is empty",
        "input_context": {"business_context": {"status": "empty"}, "campaigns": []},
        "expected_behavior": ["ask user to fill business context", "avoid niche and seasonality claims"],
        "expected_missing_data": ["brand", "niche", "offers", "seasonality"],
        "forbidden_claims": ["known business niche", "known landing page quality"],
    },
    {
        "id": "yesterday_only_no_trend",
        "title": "Only yesterday summary is available",
        "input_context": {
            "yesterday_campaign_summary": {"hasData": True, "date": "2026-06-22"},
            "weekly_dynamics": None,
        },
        "expected_behavior": ["analyze yesterday operationally", "do not claim trend"],
        "expected_missing_data": ["weekly dynamics", "comparison period"],
        "forbidden_claims": ["performance improved week over week", "trend is confirmed"],
    },
    {
        "id": "search_query_negative_candidate",
        "title": "Search query candidate for negative keyword draft",
        "input_context": {
            "search_query_insights": {
                "insights": [{"query": "free template", "clicks": 14, "cost": 900, "goal_conversions": 0}]
            }
        },
        "expected_behavior": ["prepare negative keyword draft", "require human approval", "mention confidence"],
        "expected_missing_data": ["query intent review"],
        "forbidden_claims": ["negative keyword was added"],
    },
    {
        "id": "search_query_with_conversions",
        "title": "Search query has selected goal conversions",
        "input_context": {
            "search_query_insights": {
                "insights": [{"query": "buy service", "clicks": 20, "cost": 1500, "goal_conversions": 2}]
            }
        },
        "expected_behavior": ["do not recommend excluding converting query", "mark as useful evidence"],
        "expected_missing_data": [],
        "forbidden_claims": ["add as negative keyword"],
    },
]


def list_model_eval_cases() -> list[dict[str, Any]]:
    return DIRECTPILOT_MODEL_EVAL_CASES
