from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, get_args

from app.schemas import AuditDataRequest, AuditInvestigationHypothesis
from app.services.yandex_direct_read_capabilities import (
    ALL_SUBTYPES,
    YANDEX_DIRECT_READ_CAPABILITIES,
)
from app.services.audit_evidence_identity import ensure_trusted_campaign_scopes


AUDIT_EVIDENCE_POLICY_VERSION = "audit-evidence-v1"

CANONICAL_AUDIT_SIGNALS = frozenset({
    "high_cpa",
    "spend_without_conversions",
    "low_data_volume",
    "good_campaign_do_not_touch",
    "tracking_issue_suspected",
    "brand_campaign_cannibalization",
    "yan_low_quality_placements",
    "search_query_waste",
    "budget_spike",
    "learning_strategy_do_not_touch",
})

SIGNAL_PRIORITY_TIERS: dict[str, int] = {
    "tracking_issue_suspected": 0,
    "spend_without_conversions": 0,
    "high_cpa": 1,
    "search_query_waste": 1,
    "yan_low_quality_placements": 1,
    "budget_spike": 1,
    "brand_campaign_cannibalization": 1,
    "learning_strategy_do_not_touch": 2,
    "low_data_volume": 2,
    "good_campaign_do_not_touch": 3,
}

SIGNAL_PRIORITY_ORDER = {
    signal: rank
    for rank, signal in enumerate((
        "tracking_issue_suspected",
        "spend_without_conversions",
        "high_cpa",
        "search_query_waste",
        "yan_low_quality_placements",
        "budget_spike",
        "brand_campaign_cannibalization",
        "learning_strategy_do_not_touch",
        "low_data_volume",
        "good_campaign_do_not_touch",
    ))
}

# These are the metrics that the current deterministic build_observed_facts()
# implementation can actually emit. Keep this allowlist synchronized in tests;
# a policy string alone is not a runtime activation path.
RUNTIME_OBSERVED_FACT_METRICS = frozenset({
    "campaign_health",
    "conversion_data_unknown",
    "spend_without_goal_conversions",
    "cpa_above_target",
    "low_ctr",
    "low_data",
    "good_campaign",
    "goal_conversions_drop",
    "budget_spike",
    "stable_efficiency",
    "tracking_inconsistency",
})

NOT_AUTO_DETECTABLE_SIGNALS: dict[str, dict[str, str]] = {
    "learning_strategy_do_not_touch": {
        "status": "not_auto_detectable",
        "reasonCode": "trusted_strategy_learning_status_unavailable",
        "description": "DirectPilot не получает надёжный статус обучения стратегии из текущего baseline.",
    },
    "brand_campaign_cannibalization": {
        "status": "not_auto_detectable",
        "reasonCode": "trusted_brand_share_or_incrementality_unavailable",
        "description": "DirectPilot не рассчитывает brand share/incrementality и не подтверждает каннибализацию по названию.",
    },
}

_FACT_SIGNAL_MAP = {
    "cpa_above_target": "high_cpa",
    "spend_without_goal_conversions": "spend_without_conversions",
    "low_data": "low_data_volume",
    "good_campaign": "good_campaign_do_not_touch",
    "stable_efficiency": "good_campaign_do_not_touch",
    "tracking_inconsistency": "tracking_issue_suspected",
    "conversion_data_unknown": "tracking_issue_suspected",
    "budget_spike": "budget_spike",
}

_HYPOTHESIS_SIGNAL_MAP = {
    "search_query_waste": "search_query_waste",
    "placement_waste": "yan_low_quality_placements",
    "tracking_issue": "tracking_issue_suspected",
}

# Semantic dimensions resolve only to capability IDs already present in the
# read-only registry. The first live and applicable candidate wins.
DIMENSION_CAPABILITY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "campaign_performance": ("campaign_performance",),
    "conversions_by_goal": ("conversions_by_goal",),
    "goals": ("goals",),
    "ad_groups": ("ad_groups",),
    "ad_group_performance": ("ad_group_performance",),
    "keywords": ("keywords",),
    "keyword_performance": ("keyword_performance",),
    "search_queries": ("search_queries",),
    "devices": ("devices",),
    "geo": ("geo", "location_of_presence"),
    "campaign_daily_dynamics": ("campaign_daily_dynamics",),
    "autotargeting": ("autotargeting", "criteria_performance"),
    "bid_modifiers": ("bid_modifiers", "campaign_bid_modifiers"),
    "landing_pages": ("landing_pages",),
    "placements": ("placements", "placement_or_network_breakdown"),
    "audiences": ("audience_targets", "targeting_conditions"),
    "ads_creatives": ("ads", "creatives", "ad_creative_metadata"),
    "retargeting_segments": ("retargeting_segments", "retargeting_lists"),
    "frequency": ("frequency", "frequency_and_reach"),
    "demographics": ("demographics",),
    "conversion_sources": ("conversion_sources",),
    "campaign_strategy": ("campaign_strategy", "campaign_settings"),
    "campaign_status": ("campaign_status", "campaigns"),
    "campaign_settings": ("campaign_settings", "campaigns"),
    "pageviews": ("pageviews",),
    "lead_quality": ("lead_quality",),
}


@dataclass(frozen=True)
class EvidenceRule:
    required: tuple[str, ...]
    conditional: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()


_BASE_PERFORMANCE = ("campaign_performance", "conversions_by_goal")
_SEARCH_DETAIL = (
    "ad_groups", "ad_group_performance", "keywords", "keyword_performance", "search_queries",
)
_SEARCH_SEGMENTS = ("devices", "geo")
_YAN_PROSPECTING_DETAIL = ("placements", "audiences", "ads_creatives", "devices", "geo")
_YAN_RETARGETING_DETAIL = (
    "retargeting_segments", "audiences", "frequency", "ads_creatives", "devices",
)


AUDIT_EVIDENCE_POLICY: dict[str, dict[str, EvidenceRule]] = {
    "high_cpa": {
        "search": EvidenceRule(
            ("conversions_by_goal", "campaign_performance") + _SEARCH_DETAIL + _SEARCH_SEGMENTS + ("campaign_daily_dynamics",),
            ("autotargeting", "bid_modifiers", "landing_pages"),
            ("placements", "retargeting_segments", "frequency"),
        ),
        "brand_search": EvidenceRule(
            ("conversions_by_goal", "campaign_performance") + _SEARCH_DETAIL + _SEARCH_SEGMENTS + ("campaign_daily_dynamics",),
            ("autotargeting", "bid_modifiers", "landing_pages"),
            ("placements", "retargeting_segments", "frequency"),
        ),
        "yan_prospecting": EvidenceRule(
            _BASE_PERFORMANCE + _YAN_PROSPECTING_DETAIL + ("campaign_daily_dynamics",),
            ("frequency", "bid_modifiers", "demographics"),
            ("search_queries", "keywords", "keyword_performance"),
        ),
        "yan_retargeting": EvidenceRule(
            _BASE_PERFORMANCE + _YAN_RETARGETING_DETAIL + ("campaign_daily_dynamics",),
            ("bid_modifiers", "demographics"),
            ("search_queries", "keywords", "keyword_performance"),
        ),
        "unknown": EvidenceRule(
            _BASE_PERFORMANCE + ("campaign_daily_dynamics",),
            ("campaign_settings", "campaign_status"),
        ),
    },
    "spend_without_conversions": {
        "search": EvidenceRule(
            ("goals", "conversions_by_goal", "campaign_performance") + _SEARCH_DETAIL + _SEARCH_SEGMENTS,
            ("conversion_sources", "landing_pages", "campaign_strategy", "autotargeting"),
            ("placements", "retargeting_segments", "frequency"),
        ),
        "brand_search": EvidenceRule(
            ("goals", "conversions_by_goal", "campaign_performance") + _SEARCH_DETAIL + _SEARCH_SEGMENTS,
            ("conversion_sources", "landing_pages", "campaign_strategy", "autotargeting"),
            ("placements", "retargeting_segments", "frequency"),
        ),
        "yan_prospecting": EvidenceRule(
            ("goals", "conversions_by_goal", "campaign_performance") + _YAN_PROSPECTING_DETAIL,
            ("conversion_sources", "landing_pages", "campaign_strategy"),
            ("search_queries", "keywords", "keyword_performance"),
        ),
        "yan_retargeting": EvidenceRule(
            ("goals", "conversions_by_goal", "campaign_performance") + _YAN_RETARGETING_DETAIL,
            ("conversion_sources", "landing_pages", "campaign_strategy"),
            ("search_queries", "keywords", "keyword_performance"),
        ),
        "unknown": EvidenceRule(
            ("goals", "conversions_by_goal", "campaign_performance", "campaign_status"),
            ("conversion_sources", "landing_pages", "campaign_strategy"),
        ),
    },
    "search_query_waste": {
        "search": EvidenceRule(
            ("search_queries", "keywords", "keyword_performance", "autotargeting", "ad_groups", "ad_group_performance", "conversions_by_goal"),
            ("devices", "geo", "ads_creatives"),
            ("placements", "retargeting_segments", "frequency"),
        ),
        "brand_search": EvidenceRule(
            ("search_queries", "keywords", "keyword_performance", "autotargeting", "ad_groups", "ad_group_performance", "conversions_by_goal"),
            ("devices", "geo", "ads_creatives"),
            ("placements", "retargeting_segments", "frequency"),
        ),
    },
    "yan_low_quality_placements": {
        "yan_prospecting": EvidenceRule(
            ("placements", "campaign_performance", "conversions_by_goal", "devices"),
            ("demographics", "audiences", "ads_creatives", "frequency"),
            ("keywords", "search_queries", "keyword_performance"),
        ),
        "yan_retargeting": EvidenceRule(
            ("placements", "campaign_performance", "conversions_by_goal", "devices"),
            ("demographics", "audiences", "ads_creatives", "frequency"),
            ("keywords", "search_queries", "keyword_performance"),
        ),
    },
    "tracking_issue_suspected": {
        subtype: EvidenceRule(
            ("goals", "conversions_by_goal", "campaign_performance"),
            ("conversion_sources", "landing_pages", "pageviews", "lead_quality"),
        ) for subtype in ALL_SUBTYPES
    },
    "brand_campaign_cannibalization": {
        "search": EvidenceRule(
            _BASE_PERFORMANCE + ("search_queries", "keywords", "keyword_performance", "campaign_settings", "campaign_daily_dynamics"),
            ("autotargeting", "geo", "devices"),
            ("placements", "retargeting_segments", "frequency"),
        ),
        "brand_search": EvidenceRule(
            _BASE_PERFORMANCE + ("search_queries", "keywords", "keyword_performance", "campaign_settings", "campaign_daily_dynamics"),
            ("autotargeting", "geo", "devices"),
            ("placements", "retargeting_segments", "frequency"),
        ),
    },
    "budget_spike": {
        subtype: EvidenceRule(
            _BASE_PERFORMANCE + ("campaign_daily_dynamics", "campaign_settings", "campaign_strategy", "campaign_status"),
            (
                ("devices", "geo", "placements", "bid_modifiers")
                if subtype.startswith("yan_")
                else ("devices", "geo", "search_queries", "keywords", "bid_modifiers")
            ),
            ("search_queries", "keywords", "keyword_performance") if subtype.startswith("yan_") else ("placements", "retargeting_segments"),
        ) for subtype in ("search", "brand_search", "yan_prospecting", "yan_retargeting")
    },
    "low_data_volume": {
        subtype: EvidenceRule(
            _BASE_PERFORMANCE + ("goals", "campaign_daily_dynamics", "campaign_status", "campaign_strategy"),
        ) for subtype in ALL_SUBTYPES
    },
    "learning_strategy_do_not_touch": {
        subtype: EvidenceRule(
            ("campaign_strategy", "campaign_status", "campaign_daily_dynamics", "campaign_performance", "conversions_by_goal"),
        ) for subtype in ALL_SUBTYPES
    },
    "good_campaign_do_not_touch": {
        subtype: EvidenceRule(
            _BASE_PERFORMANCE + ("campaign_daily_dynamics", "campaign_strategy", "campaign_status"),
            ("campaign_settings", "devices", "geo"),
        ) for subtype in ALL_SUBTYPES
    },
}


# Versioned mapping derived from the reviewed dev split and Code Dictionary.
# Empty tuples mean a safety/workflow instruction, not a data request.
RECOMMENDATION_EVIDENCE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "compare_paid_brand_vs_organic": ("campaign_performance",),
    "compare_previous_period": ("campaign_daily_dynamics",),
    "compare_search_vs_yan": ("campaign_performance",),
    "consider_audience_resegmentation": ("audiences",),
    "consider_bid_rollback": ("bid_modifiers", "campaign_strategy"),
    "consider_budget_cap_rollback": ("campaign_settings", "campaign_daily_dynamics"),
    "consider_controlled_scaling": ("campaign_performance", "conversions_by_goal"),
    "consider_creative_replacement": ("ads_creatives",),
    "consider_strategy_rollback": ("campaign_strategy", "campaign_daily_dynamics"),
    "consider_targeted_negative_keywords": ("search_queries", "keywords"),
    "consider_targeted_placement_exclusions": ("placements",),
    "estimate_incrementality": ("campaign_performance", "campaign_daily_dynamics"),
    "extend_analysis_period": ("campaign_daily_dynamics",),
    "inspect_ad_groups": ("ad_groups", "ad_group_performance"),
    "inspect_audiences": ("audiences",),
    "inspect_creatives": ("ads_creatives",),
    "inspect_devices": ("devices",),
    "inspect_frequency": ("frequency",),
    "inspect_funnel_steps": ("landing_pages", "conversion_sources"),
    "inspect_keywords": ("keywords", "keyword_performance"),
    "inspect_landing_page": ("landing_pages",),
    "inspect_placements": ("placements",),
    "inspect_product_categories": ("campaign_performance",),
    "inspect_search_queries": ("search_queries",),
    "monitor_without_changes": ("campaign_daily_dynamics",),
    "prepare_dry_run": (),
    "replace_expired_offer": ("ads_creatives",),
    "review_bid_strategy": ("campaign_strategy", "bid_modifiers"),
    "review_budget_limits": ("campaign_settings",),
    "review_lead_quality": ("lead_quality",),
    "review_strategy_change_log": ("campaign_strategy", "campaign_daily_dynamics"),
    "review_target_kpi": ("conversions_by_goal",),
    "segment_campaign_performance": ("campaign_performance",),
    "validate_crm_conversions": ("lead_quality",),
    "validate_metrica_goals": ("goals", "conversions_by_goal"),
    "validate_redirects": ("landing_pages",),
    "validate_utm_tracking": ("landing_pages", "conversion_sources"),
    "wait_for_more_data": ("campaign_daily_dynamics",),
    "wait_for_strategy_learning": ("campaign_strategy", "campaign_status", "campaign_daily_dynamics"),
}


def canonical_signal_activation_status() -> dict[str, dict[str, Any]]:
    hypothesis_types = set(get_args(
        AuditInvestigationHypothesis.model_fields["hypothesis_type"].annotation
    ))
    result: dict[str, dict[str, Any]] = {}
    for signal in sorted(CANONICAL_AUDIT_SIGNALS):
        fact_metrics = sorted(
            metric
            for metric, mapped_signal in _FACT_SIGNAL_MAP.items()
            if mapped_signal == signal and metric in RUNTIME_OBSERVED_FACT_METRICS
        )
        hypothesis_types_for_signal = sorted(
            hypothesis_type
            for hypothesis_type, mapped_signal in _HYPOTHESIS_SIGNAL_MAP.items()
            if mapped_signal == signal and hypothesis_type in hypothesis_types
        )
        if fact_metrics or hypothesis_types_for_signal:
            result[signal] = {
                "status": "auto_detectable",
                "factMetrics": fact_metrics,
                "hypothesisTypes": hypothesis_types_for_signal,
            }
        else:
            result[signal] = dict(NOT_AUTO_DETECTABLE_SIGNALS.get(signal) or {
                "status": "unsupported",
                "reasonCode": "runtime_activation_path_missing",
                "description": "Для canonical signal не определён trusted runtime activation path.",
            })
    return result


def resolve_capability(dimension: str, campaign_subtype: str) -> str | None:
    candidates = DIMENSION_CAPABILITY_CANDIDATES.get(dimension, ())
    applicable = [
        YANDEX_DIRECT_READ_CAPABILITIES[item]
        for item in candidates
        if item in YANDEX_DIRECT_READ_CAPABILITIES
        and campaign_subtype in YANDEX_DIRECT_READ_CAPABILITIES[item].supported_subtypes
    ]
    if not applicable:
        return None
    applicable.sort(key=lambda item: (not item.live_supported, candidates.index(item.id)))
    return applicable[0].id


def _classification_by_campaign(snapshot: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        str(item.get("campaign_name") or item.get("campaignName")): {
            "campaign_name": str(item.get("campaign_name") or item.get("campaignName")),
            "campaign_family": str(item.get("campaign_family") or item.get("campaignFamily") or "unknown"),
            "campaign_subtype": str(item.get("campaign_subtype") or item.get("campaignSubtype") or "unknown"),
        }
        for item in (snapshot.get("campaignClassifications") or [])
        if isinstance(item, dict) and (item.get("campaign_name") or item.get("campaignName"))
    }


def detect_canonical_audit_signals(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    classifications = _classification_by_campaign(snapshot)
    facts = {
        str(item.get("fact_id") or item.get("factId")): item
        for item in (snapshot.get("observedFacts") or [])
        if isinstance(item, dict)
    }
    detected: dict[tuple[str, str], dict[str, Any]] = {}

    def add(signal: str, campaign_name: str, classification: dict[str, str], fact_ids: Iterable[str], hypothesis_id: str | None = None) -> None:
        if signal not in CANONICAL_AUDIT_SIGNALS:
            return
        subtype = classification["campaign_subtype"]
        if signal in {"search_query_waste", "brand_campaign_cannibalization"} and subtype not in {"search", "brand_search"}:
            return
        if signal == "yan_low_quality_placements" and subtype not in {"yan_prospecting", "yan_retargeting"}:
            return
        key = (campaign_name, signal)
        current = detected.setdefault(key, {
            "signal": signal,
            "campaignName": campaign_name,
            "campaignFamily": classification["campaign_family"],
            "campaignSubtype": subtype,
            "factIds": [],
            "hypothesisId": hypothesis_id,
            "trustedDeviation": 0.0,
        })
        trusted_fact_ids = [str(item) for item in fact_ids if item]
        current["factIds"] = list(dict.fromkeys(current["factIds"] + trusted_fact_ids))[:5]
        current["hypothesisId"] = current.get("hypothesisId") or hypothesis_id
        deviations = []
        for fact_id in trusted_fact_ids:
            try:
                deviations.append(abs(float(facts.get(fact_id, {}).get("deviation"))))
            except (TypeError, ValueError):
                continue
        if deviations:
            current["trustedDeviation"] = max(float(current.get("trustedDeviation") or 0), *deviations)

    for fact_id, fact in facts.items():
        signal = _FACT_SIGNAL_MAP.get(str(fact.get("metric") or ""))
        if not signal:
            continue
        campaign_name = str(fact.get("campaign_name") or fact.get("campaignName") or "")
        if campaign_name in classifications:
            add(signal, campaign_name, classifications[campaign_name], [fact_id])
        elif signal == "tracking_issue_suspected":
            for name, classification in classifications.items():
                add(signal, name, classification, [fact_id])

    registry = snapshot.get("hypothesisRegistry") or {}
    if not isinstance(registry, dict):
        registry = {}
    for hypothesis_id, hypothesis in registry.items():
        if not isinstance(hypothesis, dict):
            continue
        signal = _HYPOTHESIS_SIGNAL_MAP.get(str(hypothesis.get("hypothesis_type") or ""))
        campaign_name = str(hypothesis.get("campaign_name") or "")
        classification = classifications.get(campaign_name)
        linked = [str(item) for item in (hypothesis.get("fact_ids") or []) if str(item) in facts]
        trusted = any(bool(facts[item].get("sufficient_data")) for item in linked)
        if signal and classification and (trusted or signal == "tracking_issue_suspected"):
            add(signal, campaign_name, classification, linked, str(hypothesis_id))
    return sorted(detected.values(), key=lambda item: (
        SIGNAL_PRIORITY_TIERS[item["signal"]],
        SIGNAL_PRIORITY_ORDER[item["signal"]],
        -float(item.get("trustedDeviation") or 0),
        item["campaignName"].casefold(),
    ))


def _requirement_id(signal: str, subtype: str, campaign_name: str, dimension: str) -> str:
    safe_campaign = "".join(char.lower() if char.isalnum() else "_" for char in campaign_name).strip("_")[:40]
    return f"{signal}.{subtype}.{safe_campaign or 'campaign'}.{dimension}"


def _baseline_status(snapshot: dict[str, Any], campaign_name: str, dimension: str) -> tuple[str, str | None, int]:
    baseline = snapshot.get("freshBaseline") or {}
    metadata = (snapshot.get("campaignApiMetadata") or {}).get(campaign_name) or {}
    selected_goals = snapshot.get("selectedGoals") or {}
    dynamics = snapshot.get("periodComparison") or {}
    if dimension == "campaign_performance" and baseline.get("performanceAvailable"):
        return "satisfied", str(baseline.get("source") or "yandex_direct_live"), 1
    if dimension in {"conversions_by_goal", "goals"} and baseline.get("performanceAvailable"):
        if selected_goals.get("hasGoalData"):
            return "satisfied", str(baseline.get("source") or "yandex_direct_live"), 1
        return "partial", "goal_data_unavailable", 0
    if dimension in {"campaign_status", "campaign_settings"} and baseline.get("campaignsAvailable"):
        return "satisfied", str(baseline.get("source") or "yandex_direct_live"), 1
    if dimension == "campaign_strategy" and metadata and any(
        isinstance(value, dict) and value.get("BiddingStrategy") for value in metadata.values()
    ):
        return "satisfied", "yandex_direct_live", 1
    if dimension == "campaign_daily_dynamics" and (
        dynamics.get("campaignDynamics") or dynamics.get("worstCampaigns") or dynamics.get("bestCampaigns")
    ):
        return "satisfied", "directpilot_campaign_dynamics", 1
    return "missing", None, 0


def ensure_evidence_coverage_registry(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    existing = {
        str(item.get("requirementId")): dict(item)
        for item in (snapshot.get("evidenceCoverageRegistry") or [])
        if isinstance(item, dict) and item.get("requirementId")
    }
    signals = detect_canonical_audit_signals(snapshot)
    registry: list[dict[str, Any]] = []
    forbidden: list[dict[str, Any]] = []
    for signal_item in signals:
        signal = signal_item["signal"]
        subtype = signal_item["campaignSubtype"]
        rule = AUDIT_EVIDENCE_POLICY.get(signal, {}).get(subtype)
        if rule is None:
            continue
        priority_tier = SIGNAL_PRIORITY_TIERS[signal]
        priority_label = "high" if priority_tier <= 1 else "medium" if priority_tier == 2 else "low"
        for dimension_rank, dimension in enumerate(rule.required):
            requirement_id = _requirement_id(signal, subtype, signal_item["campaignName"], dimension)
            prior = existing.get(requirement_id, {})
            status, source, rows = _baseline_status(snapshot, signal_item["campaignName"], dimension)
            if prior.get("status") not in {None, "missing", "planned", "processing"}:
                status = str(prior["status"])
                source = prior.get("source")
                rows = int(prior.get("rowsAnalyzed") or 0)
            capability = resolve_capability(dimension, subtype)
            registry.append({
                "requirementId": requirement_id,
                "signal": signal,
                "hypothesisId": signal_item.get("hypothesisId") or f"policy_{signal}_{len(registry) + 1:03d}",
                "campaignName": signal_item["campaignName"],
                "campaignScopeKey": ensure_trusted_campaign_scopes(snapshot).get(signal_item["campaignName"]),
                "campaignFamily": signal_item["campaignFamily"],
                "campaignSubtype": subtype,
                "dimension": dimension,
                "capabilityCandidates": list(DIMENSION_CAPABILITY_CANDIDATES[dimension]),
                "resolvedCapability": capability,
                "priority": priority_label,
                "priorityTier": priority_tier,
                "priorityRank": (
                    priority_tier * 10_000
                    + SIGNAL_PRIORITY_ORDER[signal] * 100
                    + dimension_rank
                ),
                "dimensionPriority": dimension_rank,
                "trustedDeviation": float(signal_item.get("trustedDeviation") or 0),
                "required": True,
                "status": status,
                "requestIds": list(prior.get("requestIds") or []),
                "rowsReceived": int(prior.get("rowsReceived") or rows),
                "rowsAnalyzed": rows,
                "source": source,
                "reasonCode": prior.get("reasonCode") or f"required_for_{signal}_{subtype}",
                "limitations": list(prior.get("limitations") or []),
                "minimumEvidence": {"rowsAnalyzed": 1},
                "allowedTerminalStatuses": [
                    "collected", "cached", "partial", "not_applicable",
                    "unavailable", "unsupported", "insufficient_data",
                ],
            })
        forbidden.append({
            "signal": signal,
            "campaignName": signal_item["campaignName"],
            "campaignSubtype": subtype,
            "dimensions": list(rule.forbidden),
        })
    registry.sort(key=lambda item: (
        int(item["priorityTier"]),
        SIGNAL_PRIORITY_ORDER[item["signal"]],
        int(item["dimensionPriority"]),
        -float(item.get("trustedDeviation") or 0),
        str(item["campaignName"]).casefold(),
        str(item["requirementId"]),
    ))
    snapshot["policyVersion"] = AUDIT_EVIDENCE_POLICY_VERSION
    snapshot["signalsDetected"] = signals
    snapshot["evidenceCoverageRegistry"] = registry
    snapshot["forbiddenEvidenceDimensions"] = forbidden
    return registry


def _request_matches(
    snapshot: dict[str, Any], requirement: dict[str, Any], request: dict[str, Any],
) -> bool:
    capability = str(request.get("capability_id") or request.get("dimension") or "")
    campaign_name = str(request.get("campaign_name") or "")
    requirement_scope = requirement.get("campaignScopeKey")
    request_scope = ensure_trusted_campaign_scopes(snapshot).get(campaign_name)
    same_campaign = bool(requirement_scope and request_scope and requirement_scope == request_scope)
    if not requirement_scope and not request_scope:
        # Compatibility for snapshots created before trusted scope keys existed.
        # Exact-name matching is allowed only when the snapshot has no identity map.
        same_campaign = not ensure_trusted_campaign_scopes(snapshot) and campaign_name == requirement["campaignName"]
    return (
        same_campaign
        and capability in set(requirement.get("capabilityCandidates") or [])
    )


def refresh_evidence_coverage_registry(snapshot: dict[str, Any], results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    registry = ensure_evidence_coverage_registry(snapshot)
    requests = [
        item for key in ("validatedDataRequests", "pendingDataRequests", "processingDataRequests")
        for item in (snapshot.get(key) or []) if isinstance(item, dict)
    ]
    result_items = [item for item in (results if results is not None else snapshot.get("drilldownResults") or []) if isinstance(item, dict)]
    status_rank = {
        "satisfied": 6, "not_applicable": 5, "partial": 4, "blocked": 3,
        "processing": 2, "planned": 1, "missing": 0,
    }
    for requirement in registry:
        matches = [item for item in result_items if _request_matches(snapshot, requirement, item)]
        planned = [item for item in requests if _request_matches(snapshot, requirement, item)]
        best = requirement["status"]
        best_payload: dict[str, Any] | None = None
        for item in matches:
            result_status = str(item.get("status") or "")
            rows = int(item.get("rows_analyzed") or item.get("rows_total") or 0)
            if result_status in {"collected", "cached"} and rows >= 1:
                coverage_status = "satisfied"
            elif result_status == "not_applicable":
                coverage_status = "not_applicable"
            elif result_status in {"partial", "unavailable", "unsupported", "insufficient_data"} or (
                result_status in {"collected", "cached"} and rows < 1
            ):
                coverage_status = "partial"
            elif result_status == "processing":
                coverage_status = "processing"
            elif (
                result_status == "skipped_budget_limit"
                and str(item.get("error_code") or "") == "audit_collection_deadline_reached"
            ):
                coverage_status = "partial"
            elif result_status in {"failed", "skipped_budget_limit"}:
                coverage_status = "blocked"
            else:
                coverage_status = "missing"
            if status_rank[coverage_status] >= status_rank.get(best, 0):
                best, best_payload = coverage_status, item
        if best_payload is None and planned and status_rank.get(best, 0) < status_rank["planned"]:
            best = "processing" if any(
                item in (snapshot.get("processingDataRequests") or []) for item in planned
            ) else "planned"
        requirement["status"] = best
        if planned:
            requirement["requestIds"] = list(dict.fromkeys(
                requirement["requestIds"] + [str(item.get("request_id")) for item in planned if item.get("request_id")]
            ))
        if best_payload is not None:
            requirement["rowsReceived"] = int(best_payload.get("rows_total") or best_payload.get("rows_analyzed") or 0)
            requirement["rowsAnalyzed"] = int(best_payload.get("rows_analyzed") or 0)
            requirement["source"] = str(best_payload.get("source") or best_payload.get("source_type") or "unavailable")
            requirement["reasonCode"] = best_payload.get("error_code") or requirement["reasonCode"]
            requirement["limitations"] = [str(item)[:300] for item in (best_payload.get("limitations") or [])[:5]]
    snapshot["evidenceCoverageRegistry"] = registry
    return evaluate_audit_evidence_coverage(snapshot)


def evaluate_audit_evidence_coverage(snapshot: dict[str, Any]) -> dict[str, Any]:
    registry = snapshot.get("evidenceCoverageRegistry") or []
    if not registry:
        state = "legacy_unknown" if snapshot.get("legacyCompletedAudit") else "complete"
        result = {
            "completionState": state, "requiredTotal": 0, "satisfied": 0, "partial": 0,
            "unavailable": 0, "notApplicable": 0, "blocked": 0, "missing": 0, "processing": 0,
            "requirements": [],
        }
        snapshot["auditCompletionState"] = state
        snapshot["evidenceCoverageSummary"] = result
        return result
    counts = {key: 0 for key in ("satisfied", "partial", "not_applicable", "blocked", "missing", "processing", "planned")}
    unavailable = 0
    for item in registry:
        status = str(item.get("status") or "missing")
        counts[status if status in counts else "missing"] += 1
        if status == "partial" and str(item.get("source") or "") == "unavailable":
            unavailable += 1
    blocking = counts["blocked"] + counts["missing"] + counts["processing"] + counts["planned"]
    state = "blocked_missing_evidence" if blocking else "partial_coverage" if counts["partial"] else "complete"
    result = {
        "completionState": state,
        "requiredTotal": len(registry),
        "satisfied": counts["satisfied"],
        "partial": counts["partial"],
        "unavailable": unavailable,
        "notApplicable": counts["not_applicable"],
        "blocked": counts["blocked"],
        "missing": counts["missing"],
        "processing": counts["processing"] + counts["planned"],
        "requirements": registry,
    }
    snapshot["auditCompletionState"] = state
    snapshot["evidenceCoverageSummary"] = {key: value for key, value in result.items() if key != "requirements"}
    return result


def _forbidden_for(snapshot: dict[str, Any], campaign_name: str) -> set[str]:
    dimensions = {
        str(dimension)
        for item in (snapshot.get("forbiddenEvidenceDimensions") or [])
        if item.get("campaignName") == campaign_name
        for dimension in (item.get("dimensions") or [])
    }
    return dimensions | {
        capability
        for dimension in dimensions
        for capability in DIMENSION_CAPABILITY_CANDIDATES.get(dimension, ())
    }


def evidence_dimension_forbidden(
    snapshot: dict[str, Any],
    campaign_name: str,
    dimension_or_capability: str,
) -> bool:
    return dimension_or_capability in _forbidden_for(snapshot, campaign_name)


def merge_mandatory_and_ai_requests(
    snapshot: dict[str, Any],
    ai_requests: list[AuditDataRequest],
    *,
    request_budget: int,
) -> tuple[list[AuditDataRequest], list[dict[str, Any]], dict[str, int]]:
    registry = ensure_evidence_coverage_registry(snapshot)
    existing: dict[tuple[str, str], AuditDataRequest] = {}
    effective: list[AuditDataRequest] = []
    rejected: list[dict[str, Any]] = []
    stats = {"policyRequestsAdded": 0, "aiRequestsAdded": 0, "duplicateRequestsRemoved": 0, "forbiddenRequestsRejected": 0}
    ai_by_key: dict[tuple[str, str], AuditDataRequest] = {}
    for request in ai_requests:
        capability = request.capability_id or request.dimension
        key = (request.campaign_name, capability)
        if key in ai_by_key:
            stats["duplicateRequestsRemoved"] += 1
            continue
        ai_by_key[key] = request

    # Mandatory policy requests reserve the audit budget first. An equivalent
    # AI request may supply the request shape, but it cannot remove the
    # required_for_conclusion contract.
    period = snapshot.get("analysisPeriod") or {}
    for requirement in registry:
        if requirement.get("status") not in {"missing", "planned", "processing"}:
            continue
        capability = requirement.get("resolvedCapability")
        if not capability:
            requirement["status"] = "blocked"
            requirement["reasonCode"] = "capability_resolution_failed"
            continue
        key = (requirement["campaignName"], capability)
        if key in existing:
            requirement["requestIds"] = list(dict.fromkeys(
                requirement["requestIds"] + [existing[key].request_id]
            ))
            continue
        if len(effective) >= request_budget:
            requirement["status"] = "blocked"
            requirement["reasonCode"] = "mandatory_request_budget_exhausted"
            continue
        request_suffix = requirement["requirementId"].replace(".", "_")[:120]
        request = ai_by_key.pop(key, None)
        if request is None:
            capability_definition = YANDEX_DIRECT_READ_CAPABILITIES[capability]
            request = AuditDataRequest(
                request_id=f"policy_{request_suffix}",
                hypothesis_id=str(requirement["hypothesisId"]),
                campaign_name=requirement["campaignName"],
                campaign_family=requirement["campaignFamily"],
                campaign_subtype=requirement["campaignSubtype"],
                dimension=capability,
                capability_id=capability,
                reason=f"Обязательный срез policy: {requirement['reasonCode']}.",
                period={
                    "date_from": period.get("dateFrom"), "date_to": period.get("dateTo"), "days": period.get("days"),
                    "comparison_date_from": period.get("comparisonDateFrom"),
                    "comparison_date_to": period.get("comparisonDateTo"),
                },
                filters={"campaign_name": requirement["campaignName"]},
                metrics=list(capability_definition.allowed_metrics)[:12],
                priority=str(requirement["priority"]),
                required_for_conclusion=True,
                data_preference="live_preferred",
            )
            stats["policyRequestsAdded"] += 1
        else:
            request.request_id = f"policy_{request_suffix}"
            request.hypothesis_id = str(requirement["hypothesisId"])
            request.reason = f"Обязательный срез policy: {requirement['reasonCode']}."
            request.required_for_conclusion = True
            request.priority = str(requirement["priority"])
            stats["aiRequestsAdded"] += 1
        requirement["status"] = "planned"
        requirement["requestIds"] = list(dict.fromkeys(requirement["requestIds"] + [request.request_id]))
        existing[key] = request
        effective.append(request)

    # Non-mandatory AI requests are accepted only after mandatory coverage is
    # reserved and only when the campaign subtype permits that dimension.
    for key, request in ai_by_key.items():
        capability = request.capability_id or request.dimension
        forbidden = _forbidden_for(snapshot, request.campaign_name)
        if request.dimension in forbidden or capability in forbidden:
            rejected.append({
                "campaignName": request.campaign_name,
                "dimension": request.dimension,
                "status": "rejected_by_policy",
                "reasonCode": "forbidden_dimension_for_campaign_subtype",
            })
            stats["forbiddenRequestsRejected"] += 1
            continue
        if key in existing:
            stats["duplicateRequestsRemoved"] += 1
            continue
        if len(effective) >= request_budget:
            rejected.append({
                "campaignName": request.campaign_name,
                "dimension": request.dimension,
                "status": "rejected_by_policy",
                "reasonCode": "optional_request_budget_exhausted",
            })
            continue
        existing[key] = request
        effective.append(request)
        stats["aiRequestsAdded"] += 1
    snapshot["evidenceCoverageRegistry"] = registry
    diagnostics = snapshot.setdefault("evidencePolicyDiagnostics", {})
    for key, value in stats.items():
        diagnostics[key] = int(diagnostics.get(key) or 0) + value
    diagnostics["policyVersion"] = AUDIT_EVIDENCE_POLICY_VERSION
    diagnostics["signalsDetected"] = len(snapshot.get("signalsDetected") or [])
    diagnostics["mandatoryRequirementsCount"] = len(registry)
    return effective, rejected, stats


def public_evidence_coverage(snapshot: dict[str, Any], *, legacy_completed: bool = False) -> dict[str, Any]:
    if not snapshot.get("evidenceCoverageRegistry") and legacy_completed:
        return {
            "policyVersion": None,
            "completionState": "legacy_unknown",
            "summary": {"requiredTotal": 0, "satisfied": 0, "partial": 0, "unavailable": 0, "notApplicable": 0, "blocked": 0, "missing": 0, "processing": 0},
            "requirements": [],
        }
    coverage = evaluate_audit_evidence_coverage(snapshot)
    stop_reason = str((snapshot.get("auditRuntime") or {}).get("stopReason") or "")
    if stop_reason in {"collection_deadline_reached", "hard_deadline_reached"}:
        coverage = {**coverage, "completionState": "partial_coverage"}
    sensitive_markers = (
        "authorization", "oauth", "access_token", "refresh_token", "client-login",
        "campaignid", "adgroupid", "request_hash", "raw provider", "raw request",
        "provider response", "direct payload", "organization_id", "client_id", "audit_job_id",
    )

    def safe_text(value: Any, *, max_chars: int) -> str | None:
        text = str(value or "").strip()[:max_chars]
        if not text:
            return None
        if any(marker in text.lower() for marker in sensitive_markers):
            return "Технические детали скрыты."
        return text

    requirements = [{
        "campaignName": safe_text(item.get("campaignName") or "Кампания", max_chars=300),
        "signal": str(item.get("signal") or "unknown")[:100],
        "dimension": str(item.get("dimension") or "unknown")[:100],
        "status": str(item.get("status") or "missing")[:50],
        "source": safe_text(item.get("source"), max_chars=100),
        "reasonCode": safe_text(item.get("reasonCode"), max_chars=150),
        "rowsAnalyzed": int(item.get("rowsAnalyzed") or 0),
        "limitations": [
            safe
            for value in (item.get("limitations") or [])[:3]
            if (safe := safe_text(value, max_chars=300))
        ],
    } for item in coverage["requirements"]]
    return {
        "policyVersion": AUDIT_EVIDENCE_POLICY_VERSION,
        "completionState": coverage["completionState"],
        "summary": {key: value for key, value in coverage.items() if key not in {"requirements", "completionState"}},
        "requirements": requirements,
    }


def validate_audit_evidence_policy() -> list[str]:
    errors: list[str] = []
    requirement_ids: set[str] = set()
    for signal, rules in AUDIT_EVIDENCE_POLICY.items():
        if signal not in CANONICAL_AUDIT_SIGNALS:
            errors.append(f"unknown signal: {signal}")
        for subtype, rule in rules.items():
            if subtype not in ALL_SUBTYPES:
                errors.append(f"unknown subtype: {subtype}")
            overlap = set(rule.required) & set(rule.forbidden)
            if overlap:
                errors.append(f"required/forbidden overlap: {signal}.{subtype}: {sorted(overlap)}")
            for dimension in rule.required + rule.conditional + rule.forbidden:
                if dimension not in DIMENSION_CAPABILITY_CANDIDATES:
                    errors.append(f"unknown dimension: {dimension}")
            for dimension in rule.required:
                requirement_id = f"{signal}.{subtype}.{dimension}"
                if requirement_id in requirement_ids:
                    errors.append(f"duplicate requirement: {requirement_id}")
                requirement_ids.add(requirement_id)
                for capability in DIMENSION_CAPABILITY_CANDIDATES.get(dimension, ()):
                    if capability not in YANDEX_DIRECT_READ_CAPABILITIES:
                        errors.append(f"unknown capability: {capability}")
    missing_rules = CANONICAL_AUDIT_SIGNALS - set(AUDIT_EVIDENCE_POLICY)
    for signal in sorted(missing_rules):
        errors.append(f"canonical signal has no policy rule: {signal}")
    for metric, signal in sorted(_FACT_SIGNAL_MAP.items()):
        if metric not in RUNTIME_OBSERVED_FACT_METRICS:
            errors.append(f"fact activation metric is not emitted at runtime: {signal}.{metric}")
    schema_hypothesis_types = set(get_args(
        AuditInvestigationHypothesis.model_fields["hypothesis_type"].annotation
    ))
    for hypothesis_type, signal in sorted(_HYPOTHESIS_SIGNAL_MAP.items()):
        if hypothesis_type not in schema_hypothesis_types:
            errors.append(
                f"hypothesis activation type is absent from schema: {signal}.{hypothesis_type}"
            )
    activation = canonical_signal_activation_status()
    for signal in sorted(CANONICAL_AUDIT_SIGNALS):
        status = str((activation.get(signal) or {}).get("status") or "unsupported")
        if status not in {"auto_detectable", "not_auto_detectable"}:
            errors.append(f"canonical signal has no runtime activation contract: {signal}")
        if status == "not_auto_detectable" and not (
            (activation[signal].get("reasonCode") or "").strip()
            and (activation[signal].get("description") or "").strip()
        ):
            errors.append(f"not_auto_detectable signal is undocumented: {signal}")
    for code, dimensions in RECOMMENDATION_EVIDENCE_DIMENSIONS.items():
        if not code:
            errors.append("empty recommendation code")
        for dimension in dimensions:
            if dimension not in DIMENSION_CAPABILITY_CANDIDATES:
                errors.append(f"unknown recommendation dimension: {code}.{dimension}")
    if not AUDIT_EVIDENCE_POLICY_VERSION:
        errors.append("missing policy version")
    return errors
