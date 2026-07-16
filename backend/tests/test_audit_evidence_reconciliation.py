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
        "_trustedCampaignScopeNames": {scope_a: "Campaign A", scope_b: "Campaign B"},
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
    assert "search_queries" in reconciled["drilldown_summary"]["not_analyzed_levels"]
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
    assert reconciled["limitations"] != []
    assert "Нет данных" in reconciled["executive_summary"]
    assert "not collected" in reconciled["conclusion"]
    assert diagnostics["removedFreeTextConflicts"] == 1


def _structured_missing(campaign_name, capability="search_queries") -> dict:
    return {
        "executive_summary": "summary",
        "conclusion": "conclusion",
        "critical_findings": [{
            "campaign_name": campaign_name,
            "analysis_level": "campaign",
            "next_data_needed": [capability],
            "recommendation": "collect",
            "problem": "problem",
            "fact": "fact",
        }],
        "opportunities": [],
        "insufficient_data_campaigns": [],
        "drilldown_summary": {
            "analyzed_levels": [], "not_analyzed_levels": [capability],
            "next_data_needed": [capability],
        },
        "action_plan": [],
        "limitations": [],
    }


def test_campaign_a_evidence_cannot_close_campaign_b_or_unknown_campaign_claims():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])

    for campaign_name in ("Campaign B", "Unknown Campaign", None):
        reconciled, _ = audit_jobs._reconcile_structured_evidence_claims(
            _structured_missing(campaign_name), snapshot,
        )
        assert reconciled["critical_findings"][0]["next_data_needed"] == ["search_queries"]


def test_generic_and_account_actions_do_not_inherit_partial_campaign_evidence():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])
    result = _structured_missing("Campaign A")
    result["action_plan"] = [
        {"action": "Search queries not collected", "reason": "no data", "scope": "Кампания"},
        {"action": "Search queries not collected", "reason": "no data", "scope": "Аккаунт"},
    ]

    reconciled, _ = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert len(reconciled["action_plan"]) == 2


def _account_result(capability: str, rows: list[dict]) -> dict:
    return {
        "request_id": f"baseline_{capability}",
        "campaign_name": "__all_campaigns__",
        "capability_id": capability,
        "dimension": capability,
        "status": "collected",
        "source": "yandex_direct_live_report",
        "live": True,
        "rows_total": len(rows),
        "rows_analyzed": len(rows),
        "period": {"date_from": "2026-06-01", "date_to": "2026-06-30"},
        "data": rows,
    }


def test_account_campaign_and_performance_rows_are_derived_by_trusted_identity():
    snapshot = _snapshot()
    results = [
        _account_result("campaigns", [
            {"campaign_id": "direct-id-a", "name": "Campaign A"},
            {"campaign_id": "direct-id-b", "name": "Campaign B"},
        ]),
        _account_result("campaign_performance", [
            {"campaign_id": "direct-id-a", "campaign_name": "Campaign A", "cost": 10},
            {"campaign_id": "direct-id-b", "campaign_name": "Campaign B", "cost": 20},
        ]),
    ]

    coverage = canonical_coverage_projection(build_canonical_evidence_index(snapshot, results))

    assert len(coverage["accountWide"]) == 2
    assert {(item["campaignName"], item["capabilityId"]) for item in coverage["campaignScoped"]} == {
        ("Campaign A", "campaigns"), ("Campaign B", "campaigns"),
        ("Campaign A", "campaign_performance"), ("Campaign B", "campaign_performance"),
    }


def test_duplicate_campaign_names_remain_ambiguous_without_public_ids():
    snapshot = _snapshot()
    snapshot["_trustedCampaignScopes"] = {}
    snapshot["_trustedCampaignScopeNames"] = {
        campaign_scope_key("duplicate-a"): "Duplicate",
        campaign_scope_key("duplicate-b"): "Duplicate",
    }
    snapshot["_ambiguousCampaignNames"] = ["Duplicate"]
    result = _account_result("campaigns", [
        {"campaign_id": "duplicate-a", "name": "Duplicate"},
        {"campaign_id": "duplicate-b", "name": "Duplicate"},
    ])

    coverage = canonical_coverage_projection(build_canonical_evidence_index(snapshot, [result]))
    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(
        _structured_missing("Duplicate", "campaigns"),
        {**snapshot, "canonicalEvidenceCoverage": coverage},
    )

    assert reconciled["critical_findings"][0]["next_data_needed"] == ["campaigns"]
    assert diagnostics["requiresBackendFallback"] is False
    assert "scopeKey" not in str(coverage)
    assert "duplicate-a" not in str(coverage)


def test_ambiguous_free_text_conflict_requires_safe_backend_fallback():
    snapshot = _snapshot()
    snapshot["_trustedCampaignScopes"] = {}
    snapshot["_trustedCampaignScopeNames"] = {
        campaign_scope_key("duplicate-a"): "Duplicate",
        campaign_scope_key("duplicate-b"): "Duplicate",
    }
    snapshot["_ambiguousCampaignNames"] = ["Duplicate"]
    coverage = canonical_coverage_projection(build_canonical_evidence_index(snapshot, [
        _account_result("campaigns", [
            {"campaign_id": "duplicate-a", "name": "Duplicate"},
            {"campaign_id": "duplicate-b", "name": "Duplicate"},
        ]),
    ]))
    result = _structured_missing("Duplicate", "campaigns")
    result["critical_findings"][0]["problem"] = "Campaigns not collected"

    _, diagnostics = audit_jobs._reconcile_structured_evidence_claims(
        result, {**snapshot, "canonicalEvidenceCoverage": coverage},
    )

    assert diagnostics["requiresBackendFallback"] is True
    assert diagnostics["ambiguousFreeTextConflicts"] == 1


def test_live_baseline_does_not_restore_ambiguous_name_mapping():
    snapshot = _snapshot()
    audit_jobs._apply_live_baseline(snapshot, [
        _account_result("campaigns", [
            {"campaign_id": "duplicate-a", "name": "Duplicate"},
            {"campaign_id": "duplicate-b", "name": "Duplicate"},
        ]),
        _account_result("campaign_performance", []),
    ], allow_saved_fallback=False)

    assert "Duplicate" not in snapshot["_trustedCampaignScopes"]
    assert "Duplicate" in snapshot["_ambiguousCampaignNames"]
    assert any(item["code"] == "ambiguous_campaign_identity" for item in snapshot["evidenceIdentityLimitations"])


def test_production_aliases_are_reconciled_with_canonical_capabilities():
    snapshot = _snapshot()
    aliases = {
        "device": "devices", "placement": "placements", "keyword": "keyword_performance",
        "ad_group": "ad_group_performance", "audience": "audience_targets", "ads_creatives": "ads",
    }
    for alias, capability in aliases.items():
        result = _search_result(capability_id=capability, dimension=capability)
        audit_jobs.reconcile_collected_audit_evidence(snapshot, [result])
        reconciled, _ = audit_jobs._reconcile_structured_evidence_claims(
            _structured_missing("Campaign A", alias), snapshot,
        )
        assert reconciled["critical_findings"][0]["next_data_needed"] == []


def test_retargeting_and_dynamics_capabilities_remain_campaign_scoped():
    snapshot = _snapshot()
    for capability in ("retargeting_segments", "campaign_daily_dynamics"):
        audit_jobs.reconcile_collected_audit_evidence(snapshot, [
            _search_result(capability_id=capability, dimension=capability),
        ])
        reconciled, _ = audit_jobs._reconcile_structured_evidence_claims(
            _structured_missing("Campaign A", capability), snapshot,
        )
        assert reconciled["critical_findings"][0]["next_data_needed"] == []

        other, _ = audit_jobs._reconcile_structured_evidence_claims(
            _structured_missing("Campaign B", capability), snapshot,
        )
        assert other["critical_findings"][0]["next_data_needed"] == [capability]


def test_partial_campaign_coverage_never_becomes_account_wide():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])
    result = _structured_missing(None)
    result["critical_findings"][0]["analysis_level"] = "account"

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["critical_findings"][0]["next_data_needed"] == ["search_queries"]
    assert "search_queries" in reconciled["drilldown_summary"]["analyzed_levels"]
    assert diagnostics["completeAccountCoverage"] == []


def test_complete_campaign_coverage_can_satisfy_account_summary():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [
        _search_result(), _search_result(request_id="search-b", campaign_name="Campaign B"),
    ])
    result = _structured_missing(None)
    result["critical_findings"][0]["analysis_level"] = "account"

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["critical_findings"][0]["next_data_needed"] == []
    assert "search_queries" in reconciled["drilldown_summary"]["analyzed_levels"]
    assert "search_queries" in diagnostics["completeAccountCoverage"]


def test_unknown_conversion_placement_rows_are_quality_limited_not_missing():
    snapshot = _snapshot()
    result = _search_result(
        capability_id="placements", dimension="placements", rows_total=1, rows_analyzed=1,
        data=[{"placement": "network", "cost": 500, "clicks": 20, "conversions": None}],
    )
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [result])

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(
        _structured_missing("Campaign A", "placement"), snapshot,
    )

    assert reconciled["critical_findings"][0]["next_data_needed"] == []
    assert diagnostics["qualityLimitationsAdded"] >= 1


def test_reconciliation_lifecycle_is_separate_from_provider_status():
    snapshot = _snapshot()
    snapshot["auditRuntime"] = {"finalGenerationStatus": "provider_completed"}
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])
    _, diagnostics = audit_jobs._reconcile_structured_evidence_claims(
        _structured_missing("Campaign A"), snapshot,
    )

    assert snapshot["auditRuntime"]["finalGenerationStatus"] == "provider_completed"
    assert diagnostics["status"] == "final_output_evidence_reconciled"


def test_empty_or_saved_period_evidence_never_reports_a_match():
    for results in ([], [_search_result(source="directpilot_saved_stats", live=False)]):
        snapshot = _snapshot()
        snapshot["analysisPeriod"]["requestedMatchesAvailableData"] = True
        audit_jobs.reconcile_collected_audit_evidence(snapshot, results)
        assert snapshot["analysisPeriod"]["requestedMatchesAvailableData"] is False
        assert snapshot["analysisPeriod"]["evidencePeriodsChecked"] == 0


def test_mismatched_live_period_adds_scoped_limitation():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(
        snapshot,
        [_search_result(period={"date_from": "2026-05-01", "date_to": "2026-05-31"})],
    )

    assert snapshot["analysisPeriod"]["requestedMatchesAvailableData"] is False
    assert snapshot["analysisPeriod"]["evidencePeriodsChecked"] == 1
    assert snapshot["periodEvidenceLimitations"][0]["campaignName"] == "Campaign A"


def test_reconciliation_is_pure_and_never_calls_direct(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(
        audit_jobs, "collect_audit_data_requests",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Direct must not be called")),
    )

    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])

    assert snapshot["canonicalEvidenceCoverage"]["campaignScoped"]


def _coverage_entry(
    campaign_name: str, capability: str, *, quality: str = "sufficient",
    quality_reason: str | None = None,
) -> dict:
    return {
        "campaignName": campaign_name,
        "capabilityId": capability,
        "status": "collected",
        "rowsReceived": 7,
        "rowsAnalyzedByBackend": 7,
        "rowsSentToAi": 7,
        "dataQuality": quality,
        "qualityReason": quality_reason,
        "source": "yandex_direct_live_report",
        "period": {"date_from": "2026-06-01", "date_to": "2026-06-30"},
    }


def _insufficient_result(
    campaign_name: str, needed: list[str], *, reason: str, recommendation: str,
) -> dict:
    return {
        "executive_summary": "summary",
        "conclusion": "conclusion",
        "critical_findings": [],
        "opportunities": [],
        "insufficient_data_campaigns": [{
            "campaign_name": campaign_name,
            "reason": reason,
            "recommendation": recommendation,
            "next_data_needed": needed,
        }],
        "drilldown_summary": {
            "analyzed_levels": [], "not_analyzed_levels": [], "next_data_needed": [],
        },
        "action_plan": [],
        "limitations": [],
    }


def test_partial_insufficient_data_rewrite_separates_missing_from_low_quality():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [_coverage_entry(
            "Campaign A", "retargeting_segments",
            quality="insufficient", quality_reason="low_data",
        )],
    }
    result = _insufficient_result(
        "Campaign A", ["retargeting_segments", "conversion_data"],
        reason="Отсутствуют данные по сегментам ретаргетинга и конверсиям.",
        recommendation="Повторно собрать сегменты ретаргетинга и конверсии.",
    )

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)
    item = reconciled["insufficient_data_campaigns"][0]

    assert item["next_data_needed"] == ["conversion_data"]
    assert "сегментам ретаргетинга собраны" in item["reason"]
    assert "выборка ограничена" in item["reason"]
    assert "конверсиям недоступны или недостаточны" in item["reason"]
    assert "Повторно запрашивать уже собранные данные" in item["recommendation"]
    assert diagnostics["removedFalseMissingClaims"] == 1
    assert diagnostics["removedFreeTextConflicts"] == 2
    assert diagnostics["requiresBackendFallback"] is False


def test_all_collected_insufficient_data_rewrite_does_not_request_same_slice():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [_coverage_entry(
            "Campaign A", "retargeting_segments",
            quality="insufficient", quality_reason="low_data",
        )],
    }
    result = _insufficient_result(
        "Campaign A", ["retargeting_segments"],
        reason="Нет данных по сегментам ретаргетинга.",
        recommendation="Собрать сегменты ретаргетинга повторно.",
    )

    reconciled, _ = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)
    item = reconciled["insufficient_data_campaigns"][0]

    assert item["next_data_needed"] == []
    assert "выборка ограничена" in item["reason"]
    assert "не требуется" in item["recommendation"]
    assert "отсутств" not in item["reason"].casefold()


def test_none_collected_preserves_insufficient_data_meaning():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {"accountWide": [], "campaignScoped": []}
    original_reason = "Отсутствуют данные по сегментам ретаргетинга и конверсиям."
    original_recommendation = "Собрать сегменты ретаргетинга и конверсии."
    result = _insufficient_result(
        "Campaign A", ["retargeting_segments", "conversion_data"],
        reason=original_reason, recommendation=original_recommendation,
    )

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)
    item = reconciled["insufficient_data_campaigns"][0]

    assert item["next_data_needed"] == ["retargeting_segments", "conversion_data"]
    assert item["reason"] == original_reason
    assert item["recommendation"] == original_recommendation
    assert diagnostics["removedFalseMissingClaims"] == 0
    assert diagnostics["removedFreeTextConflicts"] == 0


def test_insufficient_data_rewrite_never_uses_other_campaign_evidence():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [_coverage_entry("Campaign A", "retargeting_segments")],
    }
    result = _insufficient_result(
        "Campaign B", ["retargeting_segments"],
        reason="Нет данных по сегментам ретаргетинга.",
        recommendation="Собрать сегменты ретаргетинга.",
    )

    reconciled, _ = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)
    item = reconciled["insufficient_data_campaigns"][0]

    assert item["next_data_needed"] == ["retargeting_segments"]
    assert item["reason"] == "Нет данных по сегментам ретаргетинга."


def test_ambiguous_insufficient_data_scope_requires_safe_fallback():
    snapshot = _snapshot()
    snapshot["_trustedCampaignScopes"] = {}
    snapshot["_ambiguousCampaignNames"] = ["Duplicate"]
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [_coverage_entry("Duplicate", "retargeting_segments")],
    }
    result = _insufficient_result(
        "Duplicate", ["retargeting_segments"],
        reason="Сегменты ретаргетинга отсутствуют.",
        recommendation="Собрать отсутствующие сегменты ретаргетинга.",
    )

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["insufficient_data_campaigns"][0]["next_data_needed"] == ["retargeting_segments"]
    assert diagnostics["requiresBackendFallback"] is True
    assert diagnostics["ambiguousFreeTextConflicts"] == 2


def test_unknown_conversion_quality_is_never_rewritten_as_zero():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [_coverage_entry(
            "Campaign A", "conversions_by_goal",
            quality="insufficient", quality_reason="unknown_conversion_metric",
        )],
    }
    result = _insufficient_result(
        "Campaign A", ["conversions_by_goal"],
        reason="Нет данных по конверсиям.", recommendation="Проверить конверсии.",
    )

    reconciled, _ = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)
    item = reconciled["insufficient_data_campaigns"][0]

    assert "метрика конверсий недоступна или некорректна" in item["reason"]
    assert "конверсии: 0" not in str(reconciled).casefold()
    assert "zero conversions" not in str(reconciled).casefold()


def test_production_dimensions_are_removed_without_false_missing_text_or_opaque_ids():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [
            _coverage_entry("Campaign A", "search_queries"),
            _coverage_entry("Campaign A", "placements"),
            _coverage_entry("Campaign A", "devices"),
        ],
    }
    result = _insufficient_result(
        "Campaign A", ["search_queries", "placement", "device"],
        reason="Отсутствуют поисковые запросы, площадки и устройства.",
        recommendation="Повторно запросить поисковые запросы, площадки и устройства.",
    )

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)
    public_text = str({"result": reconciled, "diagnostics": diagnostics})

    assert reconciled["insufficient_data_campaigns"][0]["next_data_needed"] == []
    assert "отсутств" not in reconciled["insufficient_data_campaigns"][0]["reason"].casefold()
    assert "scopeKey" not in public_text
    assert "request_id" not in public_text
    assert "direct-id-a" not in public_text
