from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.evals.loader import load_cascade_eval_cases
from app.schemas import (
    AiAuditCreateRequest,
    AuditDataRequest,
    AuditHypothesisVerification,
    AuditInvestigationHypothesis,
    AuditInvestigationPlan,
)
from app.services.audit_data_tools import select_live_request_batch, validate_audit_data_requests
from app.services.cascade_investigation import (
    MAX_INVESTIGATION_ROUNDS,
    build_cascade_hypotheses,
    build_observed_facts,
    enforce_hypothesis_verification,
    next_cascade_capabilities,
    round_stop_reason,
)
from app.services.yandex_direct_api_knowledge import search_direct_api_docs
from app.services.yandex_direct_read_capabilities import (
    YANDEX_DIRECT_READ_CAPABILITIES,
    public_direct_read_manifest,
)


def _request(index: int, capability: str = "devices") -> AuditDataRequest:
    return AuditDataRequest(
        request_id=f"request-{index}",
        hypothesis_id=f"hypothesis-{index}",
        campaign_name="Поиск",
        campaign_family="search",
        campaign_subtype="search",
        dimension=capability,
        capability_id=capability,
        reason="Проверить причину; результат способен изменить вывод.",
        period={"days": 30},
        metrics=["clicks", "cost", "conversions"],
        required_for_conclusion=True,
    )


def test_manual_audit_defaults_to_fresh_cache_policy():
    payload = AiAuditCreateRequest(client_id="client-a")

    assert payload.cache_policy == "fresh"


def test_semantic_request_rejects_raw_api_controls():
    payload = _request(1).model_dump(mode="json")
    payload["ReportType"] = "SEARCH_QUERY_PERFORMANCE_REPORT"
    with pytest.raises(ValidationError):
        AuditDataRequest.model_validate(payload)

    payload = _request(1).model_dump(mode="json")
    payload["filters"] = {"CampaignId": "123"}
    with pytest.raises(ValidationError):
        AuditDataRequest.model_validate(payload)


def test_docs_candidate_without_adapter_is_never_executable():
    result = search_direct_api_docs("landing page content")
    candidate = next(item for item in result["matches"] if item["capability_id"] == "landing_pages")

    assert result["executable"] is False
    assert candidate["supported_now"] is False
    assert candidate["requires_backend_implementation"] is True


def test_all_executable_capabilities_are_read_only():
    assert YANDEX_DIRECT_READ_CAPABILITIES
    assert all(item.read_only for item in YANDEX_DIRECT_READ_CAPABILITIES.values())
    assert not any(item.service in {"add", "update", "delete", "suspend", "resume", "setBids"}
                   for item in YANDEX_DIRECT_READ_CAPABILITIES.values())


def test_public_manifest_does_not_expose_raw_api_controls():
    manifest = public_direct_read_manifest()
    serialized = str(manifest)

    assert all("report_type" not in item for item in manifest)
    assert all("api_fields" not in item for item in manifest)
    assert all("service" not in item for item in manifest)
    assert all("official_reference" not in item for item in manifest)
    assert "Client-Login" not in serialized


def test_thirteen_requests_are_preserved_in_batches_five_five_three():
    pending = [_request(index) for index in range(13)]
    batch_sizes = []
    while pending:
        selected, pending = select_live_request_batch(pending)
        batch_sizes.append(len(selected))

    assert batch_sizes == [5, 5, 3]


def test_request_limit_is_per_hypothesis_not_per_campaign():
    requests = [
        AuditDataRequest(
            **{
                **_request(index).model_dump(mode="json"),
                "hypothesis_id": "hypothesis-a" if index < 4 else "hypothesis-b",
                "dimension": capability,
                "capability_id": capability,
            }
        )
        for index, capability in enumerate(
            ["ad_groups", "keywords", "search_queries", "ads", "devices", "geo", "demographics", "goals"]
        )
    ]
    accepted, rejected = validate_audit_data_requests(requests)

    assert len(accepted) == 8
    assert rejected == []


def test_retargeting_rejects_search_queries_and_uses_retargeting_cascade():
    request = AuditDataRequest(
        **{
            **_request(1, "search_queries").model_dump(mode="json"),
            "campaign_family": "yan",
            "campaign_subtype": "yan_retargeting",
        }
    )
    accepted, rejected = validate_audit_data_requests([request])

    assert accepted == []
    assert rejected[0].status == "not_applicable"
    assert next_cascade_capabilities(
        subtype="yan_retargeting", already_requested=set(), remaining_budget=4,
    )[0] == "retargeting_lists"
    assert "search_queries" not in next_cascade_capabilities(
        subtype="yan_retargeting", already_requested=set(), remaining_budget=20,
    )


def test_rule_engine_keeps_fact_separate_from_cause_and_builds_hypothesis():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-01", "dateTo": "2026-06-30", "days": 30},
        "targetKpis": {"targetCpa": 500},
        "campaignClassifications": [{
            "campaign_name": "Поиск", "campaign_family": "search", "campaign_subtype": "search",
        }],
        "campaignGroups": {"critical": [{
            "name": "Поиск", "cost": 10000, "clicks": 100, "impressions": 5000,
            "goalConversions": 10, "goalCpa": 1000, "flags": ["high_cpa"],
        }]},
    }
    facts = build_observed_facts(snapshot)
    plan = AuditInvestigationPlan(hypotheses=[AuditInvestigationHypothesis(
        hypothesis_id="hyp-1",
        campaign_name="Поиск",
        campaign_family="search",
        campaign_subtype="search",
        observed_fact="CPA выше цели",
        hypothesis="Причина может быть в качестве поискового спроса.",
        data_requests=[_request(1, "ad_groups")],
    )])
    hypotheses = build_cascade_hypotheses(plan, facts)

    assert facts[0].metric == "cpa_above_target"
    assert facts[0].deviation == 100
    assert "причин" not in facts[0].evidence[0].lower()
    assert hypotheses[0].fact_ids == [facts[0].fact_id]
    assert hypotheses[0].status == "collecting_data"


def test_rule_engine_uses_period_comparison_and_marks_missing_goal_data_as_fact():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-01", "dateTo": "2026-06-30", "days": 30},
        "selectedGoals": {"ids": ["123"], "hasGoalData": False, "message": "Goal data unavailable"},
        "campaignClassifications": [{
            "campaign_name": "Search", "campaign_family": "search", "campaign_subtype": "search",
        }],
        "campaignGroups": {"critical": [{
            "name": "Search", "cost": 5000, "clicks": 50, "impressions": 1000,
            "goalConversions": 0, "flags": ["spend_without_conversions"],
        }]},
        "periodComparison": {"worstCampaigns": [{
            "name": "Search",
            "severity": "critical",
            "flags": ["conversion_drop"],
            "last7": {"cost": 5000, "clicks": 50, "goalConversions": 2},
            "previous7": {"cost": 4500, "clicks": 55, "goalConversions": 5},
            "changes": {"goalConversionsDeltaPct": -60, "costDeltaPct": 11.11},
        }]},
    }

    facts = build_observed_facts(snapshot)

    assert any(item.metric == "goal_conversions_drop" and item.deviation == -60 for item in facts)
    tracking = next(item for item in facts if item.metric == "tracking_inconsistency")
    assert tracking.sufficient_data is False
    assert tracking.analysis_level == "tracking"


def test_confirmed_requires_trusted_collected_evidence():
    proposed = AuditHypothesisVerification(
        hypothesis_id="hyp-1",
        status="confirmed",
        verification_summary="Гипотеза подтверждена.",
        supporting_evidence=["Сигнал модели"],
    )
    request = _request(1).model_dump(mode="json")
    unavailable = {
        "request_id": "request-1", "hypothesis_id": "hyp-1", "dimension": "devices",
        "status": "unavailable", "summary": "Источник недоступен.", "rows_analyzed": 0,
    }
    enforced = enforce_hypothesis_verification(
        proposed,
        hypothesis={"fact_sufficient_data": True},
        requests=[request],
        results=[unavailable],
    )

    assert enforced.status == "unverified"
    assert enforced.supporting_evidence == []

    collected = {**unavailable, "status": "collected", "rows_analyzed": 20, "summary": "Mobile CPA выше."}
    enforced = enforce_hypothesis_verification(
        proposed,
        hypothesis={"fact_sufficient_data": True},
        requests=[request],
        results=[collected],
    )
    assert enforced.status == "confirmed"
    assert enforced.supporting_evidence[0].startswith("devices: 20 строк")


def test_round_limits_and_stop_conditions_are_bounded():
    assert MAX_INVESTIGATION_ROUNDS == 3
    assert round_stop_reason(
        round_number=3, pending=0, processing=0,
        verifications=[{"status": "unverified"}], request_count=10,
    ) == "max_rounds_reached"
    assert round_stop_reason(
        round_number=1, pending=1, processing=0,
        verifications=[], request_count=1,
    ) is None


def test_cascade_eval_dataset_is_separate_and_complete():
    cases = load_cascade_eval_cases()

    assert len(cases) >= 8
    assert {"cascade-search-irrelevant-queries", "cascade-yan-retargeting-no-search-queries",
            "cascade-tracking-issue", "cascade-good-campaign-do-not-touch"}.issubset(
        {case.id for case in cases}
    )
