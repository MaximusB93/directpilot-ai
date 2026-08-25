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


def test_reconciliation_preserves_campaign_factor_for_final_insight():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [{
        "name": "Campaign A",
        "cost": 2400,
        "clicks": 80,
        "impressions": 4000,
        "goalConversions": 1,
        "goalCpa": 2400,
    }]
    snapshot["campaignClassifications"] = [{
        "campaign_name": "Campaign A",
        "campaign_family": "search",
        "campaign_subtype": "search",
    }]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-a",
        "campaign_name": "Campaign A",
        "metric": "cpa_above_target",
        "sufficient_data": True,
        "evidence": ["CPA exceeds target."],
    }]

    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])

    summaries = snapshot["drilldownEvidenceSummaries"]
    campaign_summary = next(
        item for item in summaries
        if item.get("campaign_name") == "Campaign A"
        and item.get("capability_id") == "search_queries"
    )
    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert campaign_summary["diagnostics"]["material_waste"] is True
    assert campaign_summary["diagnostics"]["top_waste"][0]["segment"] == "waste one"
    assert insight["verification_status"] == "confirmed"
    assert "waste one" in insight["problem"]
    assert "waste one" in insight["recommendation"]
    assert any("1200.00" in item and "100.0%" in item for item in insight["evidence"])


def test_unknown_conversions_use_traffic_proxy_without_claiming_sales_impact():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [{
        "name": "Campaign A",
        "cost": 3000,
        "clicks": 100,
        "impressions": 10000,
        "goalConversions": None,
        "goalCpa": None,
    }]
    snapshot["campaignClassifications"] = [{
        "campaign_name": "Campaign A",
        "campaign_family": "search",
        "campaign_subtype": "search",
    }]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-a",
        "campaign_name": "Campaign A",
        "metric": "conversion_data_unknown",
        "sufficient_data": False,
        "evidence": ["Конверсионная метрика отсутствует."],
    }]
    unknown_result = _search_result(data=[
        {
            "query": "expensive query",
            "impressions": 1000,
            "clicks": 20,
            "cost": 2000,
            "conversions": None,
        },
        {
            "query": "baseline query",
            "impressions": 9000,
            "clicks": 80,
            "cost": 1000,
            "conversions": None,
        },
    ])

    audit_jobs.reconcile_collected_audit_evidence(snapshot, [unknown_result])
    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    summary = snapshot["drilldownEvidenceSummaries"][0]
    assert summary["traffic_diagnostics"]["candidates"][0]["segment"] == "expensive query"
    assert insight["conversion_state"] == "unknown"
    assert insight["analysis_mode"] == "traffic_proxy"
    assert "expensive query" in insight["problem"]
    assert "CPC" in insight["hypothesis"]
    assert "Влияние на конверсии не подтверждено" in insight["hypothesis"]
    assert "не связывая отклонение с продажами" in insight["recommendation"]
    assert insight["verification_status"] == "unverified"


def test_unknown_conversions_use_peer_campaign_proxy_when_breakdowns_are_unavailable():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [
        {
            "name": "RTG Expensive",
            "cost": 6000,
            "clicks": 50,
            "impressions": 5000,
            "goalConversions": None,
            "goalCpa": None,
        },
        {
            "name": "RTG Peer A",
            "cost": 2000,
            "clicks": 100,
            "impressions": 10000,
            "goalConversions": None,
            "goalCpa": None,
        },
        {
            "name": "RTG Peer B",
            "cost": 3000,
            "clicks": 150,
            "impressions": 15000,
            "goalConversions": None,
            "goalCpa": None,
        },
    ]
    snapshot["campaignClassifications"] = [
        {
            "campaign_name": name,
            "campaign_family": "yan",
            "campaign_subtype": "yan_retargeting",
        }
        for name in ("RTG Expensive", "RTG Peer A", "RTG Peer B")
    ]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-expensive",
        "campaign_name": "RTG Expensive",
        "metric": "conversion_data_unknown",
        "sufficient_data": False,
        "evidence": ["Conversion metric is unavailable."],
    }]
    snapshot["drilldownEvidenceSummaries"] = []

    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert insight["conversion_state"] == "unknown"
    assert insight["analysis_mode"] == "traffic_proxy"
    assert "RTG Expensive" in insight["problem"]
    assert "CPC" in insight["hypothesis"]
    assert any("120.00" in item and "20.00" in item for item in insight["evidence"])
    assert any("2 сопоставимым кампаниям" in item for item in insight["evidence"])
    assert any("ретаргетинг в РСЯ" in item for item in insight["evidence"])
    assert all("yan_retargeting" not in item for item in insight["evidence"])
    assert "для объекта: кампания «RTG Expensive»" in insight["recommendation"]
    assert any(
        "не подтверждает влияние на конверсии или продажи" in item
        for item in insight["evidence"]
    )
    assert insight["verification_status"] == "unverified"


def test_peer_campaign_proxy_does_not_mix_campaign_subtypes():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [
        {
            "name": "RTG Candidate", "cost": 6000, "clicks": 50,
            "impressions": 5000, "goalConversions": None,
        },
        {
            "name": "RTG Peer", "cost": 2000, "clicks": 100,
            "impressions": 10000, "goalConversions": None,
        },
        {
            "name": "Prospecting Peer", "cost": 3000, "clicks": 150,
            "impressions": 15000, "goalConversions": None,
        },
    ]
    snapshot["campaignClassifications"] = [
        {
            "campaign_name": "RTG Candidate", "campaign_family": "yan",
            "campaign_subtype": "yan_retargeting",
        },
        {
            "campaign_name": "RTG Peer", "campaign_family": "yan",
            "campaign_subtype": "yan_retargeting",
        },
        {
            "campaign_name": "Prospecting Peer", "campaign_family": "yan",
            "campaign_subtype": "yan_prospecting",
        },
    ]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-candidate",
        "campaign_name": "RTG Candidate",
        "metric": "conversion_data_unknown",
        "sufficient_data": False,
    }]
    snapshot["drilldownEvidenceSummaries"] = []

    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert "CTR и CPC рассчитаны" in insight["hypothesis"]
    assert not any("ориентир рассчитан" in item.lower() for item in insight["evidence"])


def test_unknown_conversions_still_expose_absolute_ctr_cpc_without_peer_cohort():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [{
        "name": "Single Search Campaign",
        "cost": 12000,
        "clicks": 120,
        "impressions": 12000,
        "goalConversions": None,
        "goalCpa": None,
    }]
    snapshot["campaignClassifications"] = [{
        "campaign_name": "Single Search Campaign",
        "campaign_family": "search",
        "campaign_subtype": "search",
    }]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-single",
        "campaign_name": "Single Search Campaign",
        "metric": "conversion_data_unknown",
        "sufficient_data": False,
        "evidence": ["Conversion metric is unavailable."],
    }]
    snapshot["drilldownEvidenceSummaries"] = []

    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert insight["ctr"] == 1.0
    assert insight["cpc"] == 100.0
    assert insight["signal_type"] == "traffic_metrics_available"
    assert any("показы 12000, CTR 1.00%, CPC 100.00 ₽" in item for item in insight["evidence"])
    assert "трафик не оставлен без анализа" in insight["problem"]
    assert "CTR и CPC рассчитаны" in insight["hypothesis"]
    assert "Не ограничиваться проверкой выбранных целей" in insight["recommendation"]
    assert "проверить параллельно" in insight["recommendation"]


def test_unknown_conversions_report_when_ctr_cpc_are_within_peer_range():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [
        {
            "name": "RTG Candidate", "cost": 2100, "clicks": 100,
            "impressions": 10000, "goalConversions": None,
        },
        {
            "name": "RTG Peer A", "cost": 2000, "clicks": 100,
            "impressions": 10000, "goalConversions": None,
        },
        {
            "name": "RTG Peer B", "cost": 2200, "clicks": 100,
            "impressions": 10000, "goalConversions": None,
        },
    ]
    snapshot["campaignClassifications"] = [
        {
            "campaign_name": name,
            "campaign_family": "yan",
            "campaign_subtype": "yan_retargeting",
        }
        for name in ("RTG Candidate", "RTG Peer A", "RTG Peer B")
    ]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-candidate",
        "campaign_name": "RTG Candidate",
        "metric": "conversion_data_unknown",
        "sufficient_data": False,
        "evidence": ["Conversion metric is unavailable."],
    }]
    snapshot["drilldownEvidenceSummaries"] = []

    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert insight["analysis_mode"] == "traffic_proxy"
    assert insight["signal_type"] == "traffic_metrics_reviewed"
    assert "CTR и CPC проверены" in insight["problem"]
    assert "материального отклонения" in insight["problem"]
    assert any("CTR 1.00% против ориентира 1.00%" in item for item in insight["evidence"])
    assert any("CPC 21.00 ₽ против ориентира 21.00 ₽" in item for item in insight["evidence"])
    assert "Следующий уровень проверки" in insight["hypothesis"]
    assert "Не ограничиваться проверкой целей" in insight["recommendation"]


def test_traffic_summary_does_not_turn_missing_metrics_into_zero():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [{
        "name": "Partial Traffic Campaign",
        "cost": 100,
        "clicks": 10,
        "goalConversions": None,
    }]
    snapshot["campaignClassifications"] = [{
        "campaign_name": "Partial Traffic Campaign",
        "campaign_family": "search",
        "campaign_subtype": "search",
    }]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-partial",
        "campaign_name": "Partial Traffic Campaign",
        "metric": "conversion_data_unknown",
        "sufficient_data": False,
    }]
    snapshot["drilldownEvidenceSummaries"] = []

    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert insight["impressions"] is None
    assert insight["ctr"] is None
    assert insight["cpc"] == 10.0
    assert any("CPC 10.00 ₽" in item for item in insight["evidence"])
    assert all("показы 0" not in item and "CTR 0.00%" not in item for item in insight["evidence"])


def test_low_sample_uses_peer_traffic_signal_before_waiting_for_more_conversions():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [
        {
            "name": "RTG Low Sample", "cost": 10000, "clicks": 50,
            "impressions": 10000, "goalConversions": 1, "goalCpa": 10000,
        },
        {
            "name": "RTG Peer A", "cost": 2000, "clicks": 100,
            "impressions": 10000, "goalConversions": 5,
        },
        {
            "name": "RTG Peer B", "cost": 2200, "clicks": 100,
            "impressions": 10000, "goalConversions": 4,
        },
    ]
    snapshot["campaignClassifications"] = [
        {
            "campaign_name": name,
            "campaign_family": "yan",
            "campaign_subtype": "yan_retargeting",
        }
        for name in ("RTG Low Sample", "RTG Peer A", "RTG Peer B")
    ]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-low-sample",
        "campaign_name": "RTG Low Sample",
        "metric": "low_data",
        "sufficient_data": False,
        "evidence": ["Only one conversion is available."],
    }]
    snapshot["drilldownEvidenceSummaries"] = []

    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert insight["conversion_state"] == "low_sample"
    assert insight["scenario_id"] == "retargeting_low_sample"
    assert {"retargeting_segments", "placements", "campaign_dynamics"} <= set(insight["scenario_checks"])
    assert insight["signal_type"] == "high_cpc_traffic_proxy"
    assert insight["signal_verification_status"] == "confirmed"
    assert insight["factor_verification_status"] == "confirmed"
    assert "Конверсионная выборка мала" in insight["problem"]
    assert "CPC 200.00" in " ".join(insight["evidence"])
    assert "за период 60–90 дней" in insight["recommendation"]
    assert "пока мала" in insight["hypothesis"]
    assert insight["verification_status"] == "unverified"


def test_low_sample_without_peer_cohort_analyzes_search_traffic_and_extends_period():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [{
        "name": "Search Low Sample",
        "cost": 9000,
        "clicks": 90,
        "impressions": 3000,
        "goalConversions": 1,
        "goalCpa": 9000,
    }]
    snapshot["campaignClassifications"] = [{
        "campaign_name": "Search Low Sample",
        "campaign_family": "search",
        "campaign_subtype": "search",
    }]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-search-low",
        "campaign_name": "Search Low Sample",
        "metric": "low_data",
        "sufficient_data": False,
    }]
    snapshot["drilldownEvidenceSummaries"] = []

    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert insight["scenario_id"] == "search_low_sample"
    assert {"search_queries", "keywords", "autotargeting", "campaign_dynamics"} <= set(
        insight["scenario_checks"]
    )
    assert insight["signal_type"] == "traffic_metrics_available"
    assert insight["ctr"] == 3.0
    assert insight["cpc"] == 100.0
    assert "трафик не оставлен без анализа" in insight["problem"]
    assert "Не ограничиваться расширением периода" in insight["recommendation"]
    assert "расширить период до 60 дней" in insight["recommendation"]
    assert "аномальными CTR/CPC" in insight["recommendation"]


def test_low_sample_with_normal_peer_traffic_does_not_send_user_back_to_goals():
    factor = {
        "factor_type": "traffic_proxy_within_peer_range",
        "conversion_state": "low_sample",
        "capability_id": "campaign_performance",
        "segment": "RTG Low Sample",
    }

    problem, recommendation = audit_jobs._factor_copy(
        factor,
        base_problem="Малая выборка.",
        base_recommendation="Расширить период.",
        verification_status="unverified",
    )

    assert "Конверсионная выборка мала" in problem
    assert "Не ограничиваться расширением периода" in recommendation
    assert "проверкой целей" not in recommendation
    assert "до 90 дней" in recommendation


def test_campaign_factor_confirmation_replaces_unrelated_model_hypothesis_status():
    snapshot = _snapshot()
    snapshot["campaignAnalysisRows"] = [{
        "name": "Campaign A",
        "cost": 2400,
        "clicks": 100,
        "impressions": 5000,
        "goalConversions": 4,
        "goalCpa": 600,
    }]
    snapshot["campaignClassifications"] = [{
        "campaign_name": "Campaign A",
        "campaign_family": "search",
        "campaign_subtype": "search",
    }]
    snapshot["observedFacts"] = [{
        "fact_id": "fact-a",
        "campaign_name": "Campaign A",
        "metric": "cpa_above_target",
        "sufficient_data": True,
        "evidence": ["CPA exceeds target."],
    }]
    snapshot["verificationRegistry"]["hyp-active"]["status"] = "unverified"
    geo_result = _search_result(
        capability_id="geo",
        dimension="geo",
        rows_total=2,
        rows_analyzed=2,
        data=[
            {
                "location_of_presence_name": "Region high",
                "impressions": 2500,
                "clicks": 60,
                "cost": 1800,
                "conversions": 1,
            },
            {
                "location_of_presence_name": "Region efficient",
                "impressions": 2500,
                "clicks": 40,
                "cost": 600,
                "conversions": 3,
            },
        ],
    )

    audit_jobs.reconcile_collected_audit_evidence(snapshot, [geo_result])
    insight = audit_jobs.build_campaign_insights(snapshot)[0]

    assert snapshot["verificationRegistry"]["hyp-active"]["status"] == "unverified"
    assert insight["verification_status"] == "confirmed"
    assert insight["confidence"] == "high"
    assert "Region high" in insight["hypothesis"]
    assert "9.00" in insight["hypothesis"]
    assert "расширенном периоде" not in insight["recommendation"]


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
    assert diagnostics["removedFreeTextConflicts"] == 4
    assert diagnostics["completeAccountCoverage"] == ["search_queries"]
    assert diagnostics["partialAccountCoverage"] == []


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


def test_generic_action_stays_scoped_while_blanket_account_action_is_reconciled():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])
    result = _structured_missing("Campaign A")
    result["action_plan"] = [
        {"action": "Search queries not collected", "reason": "no data", "scope": "Кампания"},
        {"action": "Search queries not collected", "reason": "no data", "scope": "Аккаунт"},
    ]

    reconciled, _ = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["action_plan"] == [
        {"action": "Search queries not collected", "reason": "no data", "scope": "Кампания"},
    ]
    assert reconciled["limitations"] == []


def test_all_campaigns_action_cannot_claim_collected_conversions_are_absent():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [
            _coverage_entry("Campaign A", "goals"),
        ],
        "capabilitySummary": [
            {
                "capabilityId": "goals",
                "applicableCampaigns": 2,
                "coveredCampaigns": 1,
            },
        ],
    }
    result = _structured_missing("Campaign A")
    result["action_plan"] = [
        {
            "action": "Проверить синхронизацию целей в Яндекс.Метрике",
            "reason": "Отсутствие данных по конверсиям блокирует анализ эффективности",
            "scope": "Все кампании",
        },
    ]

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["action_plan"] == []
    assert diagnostics["removedFreeTextConflicts"] >= 1
    assert any("1 из 2 кампаний" in item for item in reconciled["limitations"])


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


def test_complete_applicable_campaign_coverage_becomes_account_wide():
    snapshot = _snapshot()
    audit_jobs.reconcile_collected_audit_evidence(snapshot, [_search_result()])
    result = _structured_missing(None)
    result["critical_findings"][0]["analysis_level"] = "account"

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["critical_findings"][0]["next_data_needed"] == []
    assert "search_queries" in reconciled["drilldown_summary"]["analyzed_levels"]
    assert "search_queries" not in reconciled["drilldown_summary"]["not_analyzed_levels"]
    assert diagnostics["completeAccountCoverage"] == ["search_queries"]
    assert diagnostics["partialAccountCoverage"] == []


def test_partial_account_coverage_rejects_blanket_missing_claims_without_hiding_gap():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [
            _coverage_entry("Campaign A", "search_queries"),
            _coverage_entry("Campaign A", "keywords"),
            _coverage_entry("Campaign A", "placements"),
            {
                "campaignName": "Campaign B",
                "capabilityId": "search_queries",
                "status": "unavailable",
                "rowsReceived": 0,
                "rowsAnalyzedByBackend": 0,
                "rowsSentToAi": 0,
                "dataQuality": "insufficient",
                "qualityReason": "provider_unavailable",
            },
            {
                "campaignName": "Campaign B",
                "capabilityId": "keywords",
                "status": "unavailable",
                "rowsReceived": 0,
                "rowsAnalyzedByBackend": 0,
                "rowsSentToAi": 0,
                "dataQuality": "insufficient",
                "qualityReason": "provider_unavailable",
            },
            {
                "campaignName": "Campaign B",
                "capabilityId": "placements",
                "status": "unavailable",
                "rowsReceived": 0,
                "rowsAnalyzedByBackend": 0,
                "rowsSentToAi": 0,
                "dataQuality": "insufficient",
                "qualityReason": "provider_unavailable",
            },
        ],
    }
    result = {
        "executive_summary": "Отсутствуют поисковые запросы, ключевые фразы и площадки.",
        "conclusion": "Search queries, keywords, and placements not collected.",
        "critical_findings": [],
        "opportunities": [],
        "insufficient_data_campaigns": [],
        "drilldown_summary": {
            "analyzed_levels": [],
            "not_analyzed_levels": ["search_queries", "keywords", "placements"],
            "next_data_needed": ["search_queries", "keywords", "placements"],
        },
        "action_plan": [],
        "limitations": ["Нет данных по поисковым запросам, ключевым фразам и площадкам."],
    }

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    for capability in ("search_queries", "keywords", "placements"):
        assert capability in reconciled["drilldown_summary"]["analyzed_levels"]
        assert capability not in reconciled["drilldown_summary"]["not_analyzed_levels"]
    assert reconciled["drilldown_summary"]["next_data_needed"] == [
        "search_queries", "keywords", "placements",
    ]
    assert "Отсутствуют" not in reconciled["executive_summary"]
    assert "not collected" not in reconciled["conclusion"]
    assert sum("1 из 2 кампаний" in item for item in reconciled["limitations"]) == 3
    assert diagnostics["removedFreeTextConflicts"] == 3
    assert diagnostics["completeAccountCoverage"] == []
    assert diagnostics["partialAccountCoverage"] == ["keywords", "placements", "search_queries"]


def test_canonical_applicability_controls_account_coverage_denominator():
    snapshot = _snapshot()
    snapshot["canonicalEvidenceCoverage"] = {
        "accountWide": [],
        "campaignScoped": [
            _coverage_entry("Campaign A", "keywords"),
            _coverage_entry("Campaign A", "goals"),
            {
                "campaignName": "Campaign B",
                "capabilityId": "goals",
                "status": "unavailable",
                "rowsReceived": 0,
                "rowsAnalyzedByBackend": 0,
                "rowsSentToAi": 0,
            },
        ],
        "capabilitySummary": [
            {
                "capabilityId": "keywords",
                "applicableCampaigns": 1,
                "coveredCampaigns": 1,
            },
            {
                "capabilityId": "goals",
                "applicableCampaigns": 2,
                "coveredCampaigns": 1,
            },
        ],
    }
    result = _structured_missing(None, "keywords")
    result["critical_findings"][0]["analysis_level"] = "account"
    result["critical_findings"][0]["next_data_needed"] = ["keywords", "goals"]
    result["executive_summary"] = "Отсутствуют данные по ключевым фразам и конверсиям."
    result["conclusion"] = "Нет данных по конверсиям."
    result["limitations"] = ["Данные по конверсиям отсутствуют."]

    reconciled, diagnostics = audit_jobs._reconcile_structured_evidence_claims(result, snapshot)

    assert reconciled["critical_findings"][0]["next_data_needed"] == ["goals"]
    assert "Отсутствуют" not in reconciled["executive_summary"]
    assert "Нет данных" not in reconciled["conclusion"]
    assert any("1 из 2 кампаний" in item for item in reconciled["limitations"])
    assert not any("1 из 32 кампаний" in item for item in reconciled["limitations"])
    assert diagnostics["completeAccountCoverage"] == ["keywords"]
    assert diagnostics["partialAccountCoverage"] == ["goals"]


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
