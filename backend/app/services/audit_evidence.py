from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AVAILABLE_STATUSES = {"collected", "cached", "partial"}
PREREQUISITE_RULE_CODES = {"selected_goal_data_available"}
CONFIRMATION_RULE_BY_CAPABILITY = {
    "search_queries": "search_queries_waste_without_goals",
    "ad_group_performance": "ad_group_performance_waste_without_goals",
    "keyword_performance": "keyword_performance_waste_without_goals",
    "placements": "placements_waste_without_goals",
    "devices": "devices_cpa_segment_gap",
    "geo": "geo_cpa_segment_gap",
    "retargeting_lists": "retargeting_list_unavailable",
}
REJECTION_RULE_BY_CAPABILITY = {
    "search_queries": "search_queries_no_material_waste",
    "ad_group_performance": "ad_group_performance_no_material_waste",
    "keyword_performance": "keyword_performance_no_material_waste",
    "placements": "placements_no_material_waste",
    "devices": "devices_cpa_segments_comparable",
    "geo": "geo_cpa_segments_comparable",
    "retargeting_lists": "retargeting_lists_available",
}

HYPOTHESIS_EVIDENCE_POLICY = {
    "search_query_waste": {
        "allowed_capabilities": {"search_queries", "goals"},
        "confirmation_rule_codes": {"search_queries_waste_without_goals"},
        "rejection_rule_codes": {"search_queries_no_material_waste"},
        "required_fact_metrics": {"cost", "clicks", "goal_conversions"},
    },
    "ad_group_concentration": {
        "allowed_capabilities": {"ad_group_performance", "ad_groups", "goals"},
        "confirmation_rule_codes": {"ad_group_performance_waste_without_goals"},
        "rejection_rule_codes": {"ad_group_performance_no_material_waste"},
        "required_fact_metrics": {"cost", "clicks", "goal_conversions"},
    },
    "keyword_waste": {
        "allowed_capabilities": {"keyword_performance", "keywords", "goals"},
        "confirmation_rule_codes": {"keyword_performance_waste_without_goals"},
        "rejection_rule_codes": {"keyword_performance_no_material_waste"},
        "required_fact_metrics": {"cost", "clicks", "goal_conversions"},
    },
    "device_segment_gap": {
        "allowed_capabilities": {"devices", "goals"},
        "confirmation_rule_codes": {"devices_cpa_segment_gap"},
        "rejection_rule_codes": {"devices_cpa_segments_comparable"},
        "required_fact_metrics": {"cost", "clicks", "goal_conversions"},
    },
    "geo_segment_gap": {
        "allowed_capabilities": {"geo", "goals"},
        "confirmation_rule_codes": {"geo_cpa_segment_gap"},
        "rejection_rule_codes": {"geo_cpa_segments_comparable"},
        "required_fact_metrics": {"cost", "clicks", "goal_conversions"},
    },
    "placement_waste": {
        "allowed_capabilities": {"placements", "goals"},
        "confirmation_rule_codes": {"placements_waste_without_goals"},
        "rejection_rule_codes": {"placements_no_material_waste"},
        "required_fact_metrics": {"cost", "clicks", "goal_conversions"},
    },
    "retargeting_segment_issue": {
        "allowed_capabilities": {
            "retargeting_lists", "retargeting_segments", "audience_targets", "audiences", "goals",
        },
        "confirmation_rule_codes": {"retargeting_list_unavailable"},
        "rejection_rule_codes": {"retargeting_lists_available"},
        "required_fact_metrics": set(),
    },
    "tracking_issue": {
        "allowed_capabilities": {"goals"},
        "confirmation_rule_codes": set(),
        "rejection_rule_codes": set(),
        "required_fact_metrics": {"goal_conversions"},
    },
    "campaign_metadata_issue": {
        "allowed_capabilities": {
            "campaigns", "campaign_settings", "campaign_strategy", "campaign_status",
        },
        "confirmation_rule_codes": set(),
        "rejection_rule_codes": set(),
        "required_fact_metrics": set(),
    },
}


@dataclass(frozen=True)
class SufficiencyDecision:
    sufficient: bool
    stop_reason: str | None
    parameters: dict[str, Any]


@dataclass(frozen=True)
class NumericMetric:
    state: str
    value: float | None


def parse_numeric_metric(value: Any) -> NumericMetric:
    if value is None or str(value).strip() in {"", "--", "\u2014", "\ufffd"}:
        return NumericMetric("missing", None)
    try:
        parsed = float(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return NumericMetric("invalid", None)
    return NumericMetric("known", parsed)


def _number(value: Any) -> float:
    parsed = parse_numeric_metric(value)
    return float(parsed.value) if parsed.state == "known" else 0.0


def _row_number(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return _number(row[key])
    return 0.0


def _has_goal_metric(row: dict[str, Any]) -> bool:
    return any(
        (
            str(key).lower() in {"conversions", "goal_conversions"}
            or str(key).lower().startswith((
                "conversions_", "cost_per_conversion_", "conversion_rate_",
                "revenue_", "goals_roi_",
            ))
        )
        and parse_numeric_metric(value).state == "known"
        for key, value in row.items()
    )


def _row_conversion_metric(
    row: dict[str, Any], aggregation_policy: str | None = None,
) -> NumericMetric:
    if aggregation_policy == "per_goal_only_no_cross_goal_sum":
        return NumericMetric("missing", None)
    for key in ("goal_conversions", "conversions"):
        if key in row:
            return parse_numeric_metric(row[key])
    dynamic = [
        parse_numeric_metric(value)
        for key, value in row.items()
        if str(key).lower().startswith("conversions_")
    ]
    if len(dynamic) == 1:
        return dynamic[0]
    if dynamic and any(item.state == "invalid" for item in dynamic):
        return NumericMetric("invalid", None)
    return NumericMetric("missing", None)


def _row_conversion_value(
    row: dict[str, Any], aggregation_policy: str | None = None,
) -> float | None:
    return _row_conversion_metric(row, aggregation_policy).value


def evaluate_metric_sufficiency(
    metric: str,
    *,
    cost: float = 0,
    clicks: int = 0,
    impressions: int = 0,
    conversions: float = 0,
    target_cpa: float = 0,
    period_days: int = 0,
    segments: int = 0,
) -> SufficiencyDecision:
    """Apply metric-specific sample rules. Ten clicks are never a universal threshold."""

    metric = str(metric or "").lower()
    params = {
        "cost": round(float(cost or 0), 2),
        "clicks": int(clicks or 0),
        "impressions": int(impressions or 0),
        "conversions": float(conversions or 0),
        "target_cpa": round(float(target_cpa or 0), 2),
        "period_days": int(period_days or 0),
        "segments": int(segments or 0),
    }
    if metric in {"high_cpa", "cpa_above_target"}:
        sufficient = bool(target_cpa > 0 and period_days >= 7 and clicks >= 30 and conversions >= 3)
    elif metric in {"spend_without_conversions", "spend_without_goal_conversions"}:
        spend_floor = target_cpa if target_cpa > 0 else 500.0
        sufficient = bool(period_days >= 7 and clicks >= 20 and cost >= spend_floor and conversions == 0)
    elif metric in {"ctr", "low_ctr"}:
        sufficient = bool(period_days >= 7 and impressions >= 1000 and clicks >= 20)
    elif metric in {"device_comparison", "geo_comparison", "placements", "queries"}:
        sufficient = bool(period_days >= 7 and segments >= 2 and clicks >= 30)
    elif metric == "strategy_learning":
        sufficient = False  # Only explicit API state can establish this fact.
    elif metric in {"tracking", "tracking_inconsistency"}:
        sufficient = False  # Missing goal data is a limitation, not a causal diagnosis.
    else:
        sufficient = bool(period_days >= 7 and clicks >= 30 and impressions >= 500)
    return SufficiencyDecision(
        sufficient=sufficient,
        stop_reason=None if sufficient else "low_data",
        parameters=params,
    )


def _aggregate_rows(
    rows: list[dict[str, Any]], aggregation_policy: str | None = None,
) -> dict[str, float | int | None]:
    conversion_metrics = [_row_conversion_metric(row, aggregation_policy) for row in rows]
    conversion_values = [item.value for item in conversion_metrics if item.state == "known"]
    return {
        "rows": len(rows),
        "impressions": int(sum(_row_number(row, "impressions") for row in rows)),
        "clicks": int(sum(_row_number(row, "clicks") for row in rows)),
        "cost": round(sum(_row_number(row, "cost") for row in rows), 2),
        "conversions": round(sum(conversion_values), 4) if conversion_values else None,
        "rows_with_known_conversions": sum(1 for item in conversion_metrics if item.state == "known"),
        "rows_with_unknown_conversions": sum(1 for item in conversion_metrics if item.state != "known"),
    }


def _segment_key(capability_id: str, row: dict[str, Any]) -> str:
    keys = {
        "search_queries": ("query",),
        "ad_group_performance": ("ad_group_name",),
        "keyword_performance": ("criterion", "criteria", "keyword"),
        "devices": ("device",),
        "geo": ("location_of_presence_name", "location", "region"),
        "placements": ("placement", "external_network_name"),
        "retargeting_lists": ("name", "type"),
        "goals": ("goal_ids", "campaign_name"),
    }.get(capability_id, ())
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return f"row-{id(row)}"


def _segment_diagnostic(
    capability_id: str,
    row: dict[str, Any],
    *,
    total_cost: float,
    aggregation_policy: str | None,
) -> dict[str, Any]:
    conversions = _row_conversion_value(row, aggregation_policy)
    cost = _row_number(row, "cost")
    clicks = int(_row_number(row, "clicks"))
    impressions = int(_row_number(row, "impressions"))
    cpa = round(cost / conversions, 2) if conversions and conversions > 0 else None
    return {
        "capability_id": capability_id,
        "segment": _segment_key(capability_id, row)[:300],
        "cost": round(cost, 2),
        "cost_share_pct": round(cost / total_cost * 100, 2) if total_cost > 0 else 0.0,
        "clicks": clicks,
        "impressions": impressions,
        "conversions": round(conversions, 4) if conversions is not None else None,
        "cpa": cpa,
    }


def _performance_diagnostics(
    capability_id: str,
    rows: list[dict[str, Any]],
    *,
    target_cpa: float,
    aggregation_policy: str | None,
    total_cost: float,
) -> dict[str, Any]:
    diagnostics = [
        _segment_diagnostic(
            capability_id, row, total_cost=total_cost, aggregation_policy=aggregation_policy,
        )
        for row in rows
        if _row_conversion_metric(row, aggregation_policy).state == "known"
    ]
    zero_conversion = [
        item for item in diagnostics
        if item["conversions"] == 0 and item["clicks"] > 0 and item["cost"] > 0
    ]
    zero_conversion.sort(key=lambda item: (item["cost"], item["clicks"]), reverse=True)
    waste_cost = round(sum(float(item["cost"]) for item in zero_conversion), 2)
    waste_clicks = sum(int(item["clicks"]) for item in zero_conversion)
    waste_share = round(waste_cost / total_cost * 100, 2) if total_cost > 0 else 0.0
    spend_floor = target_cpa if target_cpa > 0 else 500.0
    material_waste = bool(
        waste_clicks >= 20
        and waste_cost >= spend_floor
        and waste_share >= 10
    )

    high_cpa = [
        item for item in diagnostics
        if item["conversions"] is not None
        and item["conversions"] > 0
        and item["clicks"] >= 15
        and item["cpa"] is not None
        and target_cpa > 0
        and item["cpa"] >= target_cpa * 1.3
    ]
    high_cpa.sort(
        key=lambda item: (
            float(item["cpa"]) / target_cpa if target_cpa > 0 else 0,
            item["cost"],
        ),
        reverse=True,
    )
    return {
        "kind": "performance_contributors",
        "material_waste": material_waste,
        "waste_rows_count": len(zero_conversion),
        "waste_cost": waste_cost,
        "waste_clicks": waste_clicks,
        "waste_share_pct": waste_share,
        "top_waste": zero_conversion[:5],
        "top_high_cpa": high_cpa[:5],
    }


def _comparison_diagnostics(
    capability_id: str,
    rows: list[dict[str, Any]],
    *,
    aggregation_policy: str | None,
    total_cost: float,
) -> dict[str, Any]:
    comparable = [
        _segment_diagnostic(
            capability_id, row, total_cost=total_cost, aggregation_policy=aggregation_policy,
        )
        for row in rows
        if _row_number(row, "clicks") >= 15
        and _row_conversion_metric(row, aggregation_policy).state == "known"
        and float(_row_conversion_value(row, aggregation_policy) or 0) > 0
    ]
    comparable.sort(key=lambda item: float(item["cpa"] or 0), reverse=True)
    positive_cpas = [float(item["cpa"]) for item in comparable if item["cpa"]]
    ratio = (
        max(positive_cpas) / min(positive_cpas)
        if len(positive_cpas) >= 2 and min(positive_cpas) > 0
        else 0.0
    )
    best = min(comparable, key=lambda item: float(item["cpa"] or 0), default=None)
    worst = max(comparable, key=lambda item: float(item["cpa"] or 0), default=None)
    return {
        "kind": "segment_comparison",
        "cpa_ratio": round(ratio, 3),
        "comparable_segments": len(comparable),
        "worst_segment": worst,
        "best_segment": best,
        "top_high_cpa": comparable[:5],
    }


def evaluate_capability_evidence(
    result: dict[str, Any],
    *,
    target_cpa: float = 0,
    period_days: int = 30,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    capability_id = str(result.get("capability_id") or result.get("dimension") or "")
    result_period = result.get("period") if isinstance(result.get("period"), dict) else {}
    fallback_period_days = int(period_days or 30)
    try:
        period_days = int(
            result_period.get("days")
            or result_period.get("period_days")
            or fallback_period_days
        )
    except (TypeError, ValueError):
        period_days = fallback_period_days
    rows = [row for row in (result.get("data") or []) if isinstance(row, dict)]
    aggregation_policy = str(result.get("aggregation_policy") or "") or None
    selected_goal_ids = [str(item) for item in (result.get("selected_goal_ids") or [])]
    totals = _aggregate_rows(rows, aggregation_policy)
    rows_total = int(result.get("rows_analyzed") or result.get("rows_total") or len(rows))
    known_conversions = int(totals["rows_with_known_conversions"])
    unknown_conversions = max(0, rows_total - known_conversions)
    conversion_coverage = known_conversions / rows_total if rows_total else 0.0
    conversion_required = capability_id in {
        "search_queries", "ad_group_performance", "keyword_performance", "placements",
        "devices", "geo", "goals",
    }
    conversion_evidence_complete = not conversion_required or (
        rows_total > 0 and known_conversions == rows_total
    )
    segment_names = {_segment_key(capability_id, row) for row in rows}
    metric = {
        "search_queries": "queries",
        "ad_group_performance": "high_cpa",
        "keyword_performance": "high_cpa",
        "devices": "device_comparison",
        "geo": "geo_comparison",
        "placements": "placements",
        "retargeting_lists": "device_comparison",
        "goals": "tracking",
    }.get(capability_id, "campaign_health")
    sufficiency = evaluate_metric_sufficiency(
        metric,
        cost=float(totals["cost"]),
        clicks=int(totals["clicks"]),
        impressions=int(totals["impressions"]),
        conversions=float(totals["conversions"] or 0),
        target_cpa=target_cpa,
        period_days=period_days,
        segments=len(segment_names),
    )
    available = result.get("status") in AVAILABLE_STATUSES
    summary = {
        "request_id": result.get("request_id"),
        "hypothesis_id": result.get("hypothesis_id"),
        "capability_id": capability_id,
        "status": result.get("status"),
        "rows_analyzed": len(rows),
        "rows_total": rows_total,
        "rows_with_known_conversions": known_conversions,
        "rows_with_unknown_conversions": unknown_conversions,
        "known_conversion_coverage": round(conversion_coverage, 4),
        "aggregation_policy": aggregation_policy,
        "selected_goal_ids": selected_goal_ids,
        "period": {
            "date_from": result_period.get("date_from") or result_period.get("dateFrom"),
            "date_to": result_period.get("date_to") or result_period.get("dateTo"),
            "days": period_days,
        },
        "data_quality_warnings": list(result.get("warnings") or []) + (
            ["Conversion coverage is incomplete; causal confirmation and rejection are blocked."]
            if conversion_required and not conversion_evidence_complete else []
        ),
        "metrics": totals,
        "segments": len(segment_names),
        "sufficient_data": bool(available and sufficiency.sufficient and conversion_evidence_complete),
        "stop_reason": (
            None if available and sufficiency.sufficient and conversion_evidence_complete
            else "unknown_conversion_metric" if available and not conversion_evidence_complete
            else "low_data"
        ),
    }
    rules: list[dict[str, Any]] = []
    if capability_id in {"search_queries", "ad_group_performance", "keyword_performance", "placements"}:
        diagnostics = _performance_diagnostics(
            capability_id,
            rows,
            target_cpa=target_cpa,
            aggregation_policy=aggregation_policy,
            total_cost=float(totals["cost"]),
        )
        summary["diagnostics"] = diagnostics
        waste_cost = float(diagnostics["waste_cost"])
        passed = bool(
            available
            and sufficiency.sufficient
            and conversion_evidence_complete
            and diagnostics["material_waste"]
        )
        rules.append({
            "rule_code": f"{capability_id}_waste_without_goals",
            "parameters": {
                **sufficiency.parameters,
                "minimum_combined_clicks": 20,
                "minimum_combined_cost": target_cpa if target_cpa > 0 else 500.0,
                "minimum_cost_share_pct": 10,
            },
            "result": {
                "matching_rows": diagnostics["waste_rows_count"],
                "waste_cost": waste_cost,
                "waste_clicks": diagnostics["waste_clicks"],
                "waste_share_pct": diagnostics["waste_share_pct"],
                "top_factors": diagnostics["top_waste"],
            },
            "passed": passed,
            "evidence": [
                f"rows={diagnostics['waste_rows_count']}",
                f"waste_cost={waste_cost:.2f}",
                f"waste_clicks={diagnostics['waste_clicks']}",
                f"waste_share_pct={diagnostics['waste_share_pct']:.2f}",
            ],
        })
        no_material_waste = bool(
            available
            and sufficiency.sufficient
            and conversion_evidence_complete
            and rows
            and not diagnostics["material_waste"]
        )
        rules.append({
            "rule_code": f"{capability_id}_no_material_waste",
            "parameters": {
                **sufficiency.parameters,
                "minimum_combined_clicks": 20,
                "minimum_cost_share_pct": 10,
            },
            "result": {
                "material_waste": False,
                "rows_checked": len(rows),
                "waste_cost": waste_cost,
                "waste_share_pct": diagnostics["waste_share_pct"],
            },
            "passed": no_material_waste,
            "evidence": [
                f"rows_checked={len(rows)}",
                f"waste_cost={waste_cost:.2f}",
                f"waste_share_pct={diagnostics['waste_share_pct']:.2f}",
            ],
        })
    elif capability_id in {"devices", "geo"}:
        diagnostics = _comparison_diagnostics(
            capability_id,
            rows,
            aggregation_policy=aggregation_policy,
            total_cost=float(totals["cost"]),
        )
        summary["diagnostics"] = diagnostics
        ratio = float(diagnostics["cpa_ratio"])
        passed = bool(
            available and sufficiency.sufficient and conversion_evidence_complete and ratio >= 1.5
        )
        rules.append({
            "rule_code": f"{capability_id}_cpa_segment_gap",
            "parameters": {**sufficiency.parameters, "minimum_ratio": 1.5},
            "result": {
                "comparable_segments": diagnostics["comparable_segments"],
                "cpa_ratio": round(ratio, 3),
                "worst_segment": diagnostics["worst_segment"],
                "best_segment": diagnostics["best_segment"],
            },
            "passed": passed,
            "evidence": [
                f"comparable_segments={diagnostics['comparable_segments']}",
                f"cpa_ratio={ratio:.3f}",
            ],
        })
        comparable_cpas = bool(
            available and sufficiency.sufficient and conversion_evidence_complete
            and diagnostics["comparable_segments"] >= 2 and 0 < ratio <= 1.2
        )
        rules.append({
            "rule_code": f"{capability_id}_cpa_segments_comparable",
            "parameters": {**sufficiency.parameters, "maximum_ratio": 1.2},
            "result": {
                "comparable_segments": diagnostics["comparable_segments"],
                "cpa_ratio": round(ratio, 3),
                "worst_segment": diagnostics["worst_segment"],
                "best_segment": diagnostics["best_segment"],
            },
            "passed": comparable_cpas,
            "evidence": [
                f"comparable_segments={diagnostics['comparable_segments']}",
                f"cpa_ratio={ratio:.3f}",
            ],
        })
    elif capability_id == "retargeting_lists":
        unavailable = [row for row in rows if row.get("is_available") is False or str(row.get("is_available")).lower() == "false"]
        passed = bool(available and rows and unavailable)
        rules.append({
            "rule_code": "retargeting_list_unavailable",
            "parameters": {"requires_explicit_api_flag": True},
            "result": {"unavailable_lists": len(unavailable), "lists": len(rows)},
            "passed": passed,
            "evidence": [f"unavailable_lists={len(unavailable)}"],
        })
        all_available = bool(available and rows and not unavailable)
        rules.append({
            "rule_code": "retargeting_lists_available",
            "parameters": {"requires_explicit_api_flag": True},
            "result": {"unavailable_lists": 0, "lists": len(rows)},
            "passed": all_available,
            "evidence": [f"available_lists={len(rows)}"],
        })
    elif capability_id == "goals":
        has_goal_values = any(_has_goal_metric(row) for row in rows)
        rows_with_goal_metric = sum(1 for row in rows if _has_goal_metric(row))
        passed = bool(available and rows and has_goal_values)
        rules.append({
            "rule_code": "selected_goal_data_available",
            "parameters": {"requires_goal_metric": True},
            "result": {"rows_with_goal_metric": rows_with_goal_metric},
            "passed": passed,
            "evidence": [f"goal_metric_available={str(has_goal_values).lower()}"],
        })
    return summary, rules


def evaluate_hypothesis_evidence(
    hypothesis: dict[str, Any],
    requests: list[dict[str, Any]],
    results: list[dict[str, Any]],
    *,
    target_cpa: float = 0,
    period_days: int = 30,
) -> dict[str, Any]:
    hypothesis_id = str(hypothesis.get("hypothesis_id") or "")
    hypothesis_type = str(hypothesis.get("hypothesis_type") or "campaign_metadata_issue")
    policy = HYPOTHESIS_EVIDENCE_POLICY.get(
        hypothesis_type, HYPOTHESIS_EVIDENCE_POLICY["campaign_metadata_issue"],
    )
    policy_capabilities = set(policy["allowed_capabilities"])
    requested_capabilities = {
        str(item.get("capability_id") or item.get("dimension") or "") for item in requests
    }
    trusted_requested_capabilities = requested_capabilities & policy_capabilities
    trusted_requests = [
        item for item in requests
        if str(item.get("capability_id") or item.get("dimension") or "") in policy_capabilities
    ]
    related = [
        item for item in results
        if item.get("hypothesis_id") == hypothesis_id
        and str(item.get("capability_id") or item.get("dimension") or "") in policy_capabilities
    ]
    by_request = {item.get("request_id"): item for item in related}
    required = [item for item in trusted_requests if item.get("required_for_conclusion")]
    required_available = all(
        (by_request.get(item.get("request_id")) or {}).get("status") in AVAILABLE_STATUSES
        for item in required
    )
    summaries: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    for result in related:
        summary, result_rules = evaluate_capability_evidence(
            result, target_cpa=target_cpa, period_days=period_days,
        )
        summaries.append(summary)
        rules.extend(result_rules)
    prerequisite_codes = set(hypothesis.get("prerequisite_rule_codes") or [])
    confirmation_codes = set(hypothesis.get("confirmation_rule_codes") or []) & set(
        policy["confirmation_rule_codes"]
    )
    rejection_codes = set(hypothesis.get("rejection_rule_codes") or []) & set(
        policy["rejection_rule_codes"]
    )
    if not prerequisite_codes and "goals" in requested_capabilities:
        prerequisite_codes.add("selected_goal_data_available")
    if "confirmation_rule_codes" not in hypothesis:
        confirmation_codes.update(
            rule_code
            for capability, rule_code in CONFIRMATION_RULE_BY_CAPABILITY.items()
            if capability in trusted_requested_capabilities
        )
    if "rejection_rule_codes" not in hypothesis:
        rejection_codes.update(
            rule_code
            for capability, rule_code in REJECTION_RULE_BY_CAPABILITY.items()
            if capability in trusted_requested_capabilities
        )
    rules_by_code = {str(item.get("rule_code") or ""): item for item in rules}
    prerequisite_results = [rules_by_code.get(code) for code in sorted(prerequisite_codes)]
    required_prerequisites_passed = all(
        item is not None and bool(item.get("passed")) for item in prerequisite_results
    )
    matching_confirmation_rules = [
        item for item in rules if item.get("rule_code") in confirmation_codes and item.get("passed")
    ]
    matching_rejection_rules = [
        item for item in rules if item.get("rule_code") in rejection_codes and item.get("passed")
    ]
    return {
        "required_data_available": required_available,
        "required_prerequisites_passed": required_prerequisites_passed,
        "prerequisite_rule_codes": sorted(prerequisite_codes),
        "confirmation_rule_codes": sorted(confirmation_codes),
        "rejection_rule_codes": sorted(rejection_codes),
        "hypothesis_type": hypothesis_type,
        "ignored_capabilities": sorted(requested_capabilities - trusted_requested_capabilities),
        "evidence_summaries": summaries,
        "confirmation_rules": rules,
        "matched_confirmation_rules": matching_confirmation_rules,
        "matched_rejection_rules": matching_rejection_rules,
        "has_passed_confirmation_rule": bool(matching_confirmation_rules),
        "has_sufficient_evidence": any(item.get("sufficient_data") for item in summaries),
    }
