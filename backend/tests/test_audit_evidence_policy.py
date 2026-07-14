from app.schemas import AuditDataRequest
from app.services.audit_evidence_policy import (
    AUDIT_EVIDENCE_POLICY,
    AUDIT_EVIDENCE_POLICY_VERSION,
    RECOMMENDATION_EVIDENCE_DIMENSIONS,
    ensure_evidence_coverage_registry,
    evaluate_audit_evidence_coverage,
    merge_mandatory_and_ai_requests,
    public_evidence_coverage,
    refresh_evidence_coverage_registry,
    validate_audit_evidence_policy,
)


def _snapshot(metric: str = "cpa_above_target", subtype: str = "search") -> dict:
    family = "yan" if subtype.startswith("yan_") else "search"
    return {
        "analysisPeriod": {"dateFrom": "2026-06-15", "dateTo": "2026-07-14", "days": 30},
        "freshBaseline": {"performanceAvailable": True, "campaignsAvailable": True, "source": "yandex_direct_live"},
        "selectedGoals": {"ids": ["123"], "hasGoalData": True},
        "campaignClassifications": [{
            "campaign_name": "Campaign A",
            "campaign_family": family,
            "campaign_subtype": subtype,
        }],
        "observedFacts": [{
            "fact_id": "fact-1",
            "campaign_name": "Campaign A",
            "metric": metric,
            "sufficient_data": metric != "low_data",
        }],
        "hypothesisRegistry": {},
    }


def _ai_request(dimension: str, subtype: str = "search") -> AuditDataRequest:
    return AuditDataRequest(
        request_id=f"ai-{dimension}",
        hypothesis_id="hypothesis-1",
        campaign_name="Campaign A",
        campaign_family="yan" if subtype.startswith("yan_") else "search",
        campaign_subtype=subtype,
        dimension=dimension,
        capability_id=dimension,
        reason="AI request",
    )


def test_policy_self_validation_and_version_are_stable():
    assert AUDIT_EVIDENCE_POLICY_VERSION == "audit-evidence-v1"
    assert validate_audit_evidence_policy() == []
    assert "inspect_search_queries" in RECOMMENDATION_EVIDENCE_DIMENSIONS
    assert "prepare_dry_run" in RECOMMENDATION_EVIDENCE_DIMENSIONS


def test_search_high_cpa_requires_search_evidence_and_forbids_yan_dimensions():
    rule = AUDIT_EVIDENCE_POLICY["high_cpa"]["search"]
    assert {"campaign_performance", "conversions_by_goal", "ad_groups", "keywords", "search_queries"} <= set(rule.required)
    assert {"placements", "retargeting_segments", "frequency"} <= set(rule.forbidden)

    snapshot = _snapshot()
    requests, rejected, _ = merge_mandatory_and_ai_requests(
        snapshot,
        [_ai_request("placements"), _ai_request("search_queries")],
        request_budget=20,
    )
    capabilities = {item.capability_id for item in requests}
    assert "search_queries" in capabilities
    assert "placements" not in capabilities
    assert rejected[0]["reasonCode"] == "forbidden_dimension_for_campaign_subtype"


def test_yan_rules_are_subtype_specific_and_do_not_request_search_queries():
    prospecting = AUDIT_EVIDENCE_POLICY["high_cpa"]["yan_prospecting"]
    retargeting = AUDIT_EVIDENCE_POLICY["high_cpa"]["yan_retargeting"]
    assert {"placements", "audiences", "ads_creatives"} <= set(prospecting.required)
    assert {"retargeting_segments", "frequency"} <= set(retargeting.required)
    assert "search_queries" in prospecting.forbidden
    assert "search_queries" in retargeting.forbidden


def test_mandatory_requests_reserve_budget_before_optional_ai_requests():
    snapshot = _snapshot(metric="spend_without_goal_conversions")
    optional = [_ai_request("ads"), _ai_request("ad_performance")]
    requests, _, stats = merge_mandatory_and_ai_requests(snapshot, optional, request_budget=5)
    required = [item for item in requests if item.required_for_conclusion]
    assert len(requests) == 5
    assert len(required) == 5
    assert stats["policyRequestsAdded"] == 5


def test_equivalent_ai_request_is_normalized_to_mandatory_policy_identity():
    snapshot = _snapshot()
    requests, _, stats = merge_mandatory_and_ai_requests(
        snapshot,
        [_ai_request("search_queries")],
        request_budget=20,
    )
    request = next(item for item in requests if item.capability_id == "search_queries")
    assert request.request_id.startswith("policy_")
    assert request.hypothesis_id.startswith("policy_")
    assert request.required_for_conclusion is True
    assert stats["aiRequestsAdded"] == 1


def test_coverage_tracks_satisfied_partial_and_blocked_without_raw_payloads():
    snapshot = _snapshot()
    registry = ensure_evidence_coverage_registry(snapshot)
    search_requirement = next(item for item in registry if item["dimension"] == "search_queries")
    results = [{
        "request_id": "result-1",
        "campaign_name": "Campaign A",
        "capability_id": "search_queries",
        "dimension": "search_queries",
        "status": "collected",
        "source": "yandex_direct_live",
        "rows_analyzed": 15,
        "data": [{"private": "must-not-leak"}],
    }]
    coverage = refresh_evidence_coverage_registry(snapshot, results)
    assert search_requirement["requirementId"]
    assert coverage["satisfied"] >= 3
    assert coverage["completionState"] == "blocked_missing_evidence"
    public = public_evidence_coverage(snapshot)
    assert "requestIds" not in str(public)
    assert "must-not-leak" not in str(public)


def test_unavailable_required_evidence_is_partial_not_success_or_zero():
    snapshot = _snapshot(metric="tracking_inconsistency", subtype="unknown")
    registry = ensure_evidence_coverage_registry(snapshot)
    for item in registry:
        item["status"] = "partial"
        item["source"] = "unavailable"
        item["rowsAnalyzed"] = 0
    coverage = evaluate_audit_evidence_coverage(snapshot)
    assert coverage["completionState"] == "partial_coverage"
    assert coverage["partial"] == coverage["requiredTotal"]


def test_low_data_and_learning_rules_avoid_deep_speculative_requests():
    low_data = AUDIT_EVIDENCE_POLICY["low_data_volume"]["search"]
    learning = AUDIT_EVIDENCE_POLICY["learning_strategy_do_not_touch"]["search"]
    assert "search_queries" not in low_data.required
    assert "placements" not in low_data.required
    assert {"campaign_strategy", "campaign_status", "campaign_daily_dynamics"} <= set(learning.required)


def test_legacy_completed_audit_does_not_reopen_without_registry():
    public = public_evidence_coverage({}, legacy_completed=True)
    assert public["completionState"] == "legacy_unknown"
    assert public["requirements"] == []


def test_public_policy_checklist_redacts_sensitive_technical_details():
    snapshot = _snapshot()
    registry = ensure_evidence_coverage_registry(snapshot)
    registry[0]["campaignName"] = "CampaignId=123 must-not-leak"
    registry[0]["source"] = "Authorization Bearer must-not-leak"
    registry[0]["limitations"] = ["access_token=must-not-leak CampaignId=123 request_hash=private"]
    public_dump = str(public_evidence_coverage(snapshot)).lower()
    for marker in ("bearer", "access_token", "campaignid", "request_hash", "must-not-leak"):
        assert marker not in public_dump
