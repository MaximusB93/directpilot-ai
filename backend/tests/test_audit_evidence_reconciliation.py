from app.services import ai_audit_jobs as audit_jobs
from app.services.audit_evidence_reconciliation import (
    build_canonical_evidence_index,
    campaign_scope_key,
    canonical_coverage_projection,
    evidence_for_hypothesis,
)


def _snapshot() -> dict:
    scope_a = campaign_scope_key("direct-id-a")
    scope_b = campaign_scope_key("direct-id-b")
    return {
        "_trustedCampaignScopes": {"Campaign A": scope_a, "Campaign B": scope_b},
        "analysisPeriod": {
            "dateFrom": "2026-06-01", "dateTo": "2026-06-30", "days": 30,
            "requestedMatchesAvailableData": False,
        },
        "targetKpis": {"targetCpa": 500},
        "observedFacts": [{"fact_id": "fact-a", "sufficient_data": True}],
        "hypothesisRegistry": {
            "hyp-active": {
                "hypothesis_id": "hyp-active",
                "hypothesis_type": "search_query_waste",
                "campaign_name": "Campaign A",
                "campaign_family": "search",
                "campaign_subtype": "search",
                "fact_ids": ["fact-a"],
                "required_capabilities": ["search_queries"],
                "confirmation_rule_codes": ["search_queries_waste_without_goals"],
                "rejection_rule_codes": ["search_queries_no_material_waste"],
                "current_status": "unverified",
            },
        },
        "activeHypothesisIds": ["hyp-active"],
        "verificationRegistry": {
            "hyp-active": {
                "hypothesis_id": "hyp-active",
                "status": "confirmed",
                "verification_summary": "provider proposal",
                "supporting_evidence": [],
                "contradicting_evidence": [],
                "limitations": [],
                "remaining_data_needed": ["search_queries"],
                "evidence_summaries": [],
                "confirmation_rules": [],
                "rejection_rules": [],
            },
        },
        "validatedDataRequests": [{
            "request_id": "policy-search-a",
            "hypothesis_id": "policy_synthetic_001",
            "campaign_name": "Campaign A",
            "campaign_family": "search",
            "campaign_subtype": "search",
            "dimension": "search_queries",
            "capability_id": "search_queries",
            "required_for_conclusion": True,
            "period": {"date_from": "2026-06-01", "date_to": "2026-06-30"},
        }],
        "aiDrilldownSamples": [{"request_id": "policy-search-a", "data": [{"query": "sample"}]}],
    }


def _search_result(**updates) -> dict:
    result = {
        "request_id": "policy-search-a",
        "hypothesis_id": "policy_synthetic_001",
        "campaign_name": "Campaign A",
        "capability_id": "search_queries",
        "dimension": "search_queries",
        "status": "collected",
        "source": "yandex_direct_live_report",
        "live": True,
        "rows_total": 2,
        "rows_analyzed": 2,
        "period": {"date_from": "2026-06-01", "date_to": "2026-06-30"},
        "data": [
            {"query": "waste one", "impressions": 1000, "clicks": 20, "cost": 600, "conversions": 0},
            {"query": "waste two", "impressions": 1000, "clicks": 20, "cost": 600, "conversions": 0},
        ],
    }
    result.update(updates)
    return result


def test_policy_evidence_links_to_active_hypothesis_and_clears_false_missing():
    snapshot = _snapshot()

    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])

    verification = snapshot["verificationRegistry"]["hyp-active"]
    assert verification["status"] == "confirmed"
    assert verification["remaining_data_needed"] == []
    assert verification["evidence_summaries"][0]["capability_id"] == "search_queries"
    assert snapshot["analysisPeriod"]["requestedMatchesAvailableData"] is True


def test_evidence_never_crosses_campaign_scope_or_inapplicable_subtype():
    snapshot = _snapshot()
    index = build_canonical_evidence_index(
        snapshot,
        [_search_result(campaign_name="Campaign B")],
    )
    requests, results = evidence_for_hypothesis(
        snapshot, snapshot["hypothesisRegistry"]["hyp-active"], index,
    )
    assert requests == []
    assert results == []

    snapshot["validatedDataRequests"][0]["campaign_subtype"] = "yan_prospecting"
    index = build_canonical_evidence_index(snapshot, [_search_result()])
    requests, results = evidence_for_hypothesis(
        snapshot, snapshot["hypothesisRegistry"]["hyp-active"], index,
    )
    assert requests == []
    assert results == []


def test_canonical_coverage_separates_backend_analysis_and_ai_sample():
    snapshot = _snapshot()
    snapshot["baselineEvidenceSummary"] = [{
        "requestId": "baseline_campaigns", "rowsSentToAi": 3,
    }]
    account_result = {
        "request_id": "baseline_campaigns",
        "hypothesis_id": "baseline",
        "campaign_name": "__all_campaigns__",
        "capability_id": "campaigns",
        "dimension": "campaigns",
        "status": "collected",
        "source": "yandex_direct_live",
        "rows_total": 12,
        "rows_analyzed": 12,
        "data": [{}] * 12,
    }
    index = build_canonical_evidence_index(snapshot, [account_result, _search_result()])
    coverage = canonical_coverage_projection(index)

    assert len(coverage["accountWide"]) == 1
    assert len(coverage["campaignScoped"]) == 1
    assert coverage["accountWide"][0]["rowsAnalyzedByBackend"] == 12
    assert coverage["accountWide"][0]["rowsSentToAi"] == 3
    assert coverage["campaignScoped"][0]["rowsAnalyzedByBackend"] == 2
    assert coverage["campaignScoped"][0]["rowsSentToAi"] == 1


def test_structured_result_removes_collected_capability_from_missing_claims():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])
    result = {
        "critical_findings": [{
            "campaign_name": "Campaign A",
            "next_data_needed": ["search_queries", "devices"],
            "recommendation": "collect data",
        }],
        "opportunities": [],
        "insufficient_data_campaigns": [{
            "campaign_name": "Campaign A",
            "reason": "missing",
            "recommendation": "collect",
            "next_data_needed": ["search_queries"],
        }],
        "drilldown_summary": {
            "analyzed_levels": [],
            "not_analyzed_levels": ["search_queries", "devices"],
            "next_data_needed": ["search_queries", "devices"],
        },
        "limitations": [],
    }

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["critical_findings"][0]["next_data_needed"] == ["devices"]
    assert reconciled["insufficient_data_campaigns"][0]["next_data_needed"] == []
    assert "search_queries" in reconciled["drilldown_summary"]["analyzed_levels"]
    assert "search_queries" not in reconciled["drilldown_summary"]["not_analyzed_levels"]
    assert diagnostics["status"] == "final_output_evidence_reconciled"


def test_rows_with_unknown_conversions_are_quality_limited_not_missing():
    snapshot = _snapshot()
    unknown = _search_result(data=[
        {"query": "unknown", "impressions": 1000, "clicks": 40, "cost": 1200, "conversions": None},
    ], rows_total=1, rows_analyzed=1)

    audit_jobs.reconcile_collected_audit_evidence(snapshot, [unknown])

    verification = snapshot["verificationRegistry"]["hyp-active"]
    assert verification["status"] == "unverified"
    assert verification["remaining_data_needed"] == []
    assert any("unknown_conversion_metric" in item for item in verification["limitations"])


def test_free_text_and_action_plan_cannot_claim_collected_evidence_is_missing():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])
    result = {
        "executive_summary": "Нет данных по поисковым запросам.",
        "conclusion": "Search queries not collected.",
        "critical_findings": [],
        "opportunities": [],
        "insufficient_data_campaigns": [],
        "drilldown_summary": {
            "analyzed_levels": [], "not_analyzed_levels": [], "next_data_needed": [],
        },
        "action_plan": [{
            "action": "Собрать отсутствующие данные поисковых запросов",
            "reason": "Нет данных по запросам",
            "scope": "Campaign A",
        }],
        "limitations": ["Данные по поисковым запросам отсутствуют."],
    }

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["action_plan"] == []
    assert reconciled["limitations"] == []
    assert "Нет данных" not in reconciled["executive_summary"]
    assert "not collected" not in reconciled["conclusion"]
    assert diagnostics["removedFreeTextConflicts"] >= 4
