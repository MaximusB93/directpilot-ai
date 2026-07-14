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


@dataclass(frozen=True)
class SufficiencyDecision:
    sufficient: bool
    stop_reason: str | None
    parameters: dict[str, Any]


def _number(value: Any) -> float:
    try:
        return float(str(value or 0).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _row_number(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return _number(row[key])
    return 0.0


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


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    return {
        "rows": len(rows),
        "impressions": int(sum(_row_number(row, "impressions") for row in rows)),
        "clicks": int(sum(_row_number(row, "clicks") for row in rows)),
        "cost": round(sum(_row_number(row, "cost") for row in rows), 2),
        "conversions": round(sum(_row_number(row, "conversions", "goal_conversions") for row in rows), 4),
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


def evaluate_capability_evidence(
    result: dict[str, Any],
    *,
    target_cpa: float = 0,
    period_days: int = 30,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    capability_id = str(result.get("capability_id") or result.get("dimension") or "")
    rows = [row for row in (result.get("data") or []) if isinstance(row, dict)]
    totals = _aggregate_rows(rows)
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
        conversions=float(totals["conversions"]),
        target_cpa=target_cpa,
        period_days=period_days,
        segments=len(segment_names),
    )
    available = result.get("status") in AVAILABLE_STATUSES
    summary = {
        "capability_id": capability_id,
        "status": result.get("status"),
        "rows_analyzed": len(rows),
        "metrics": totals,
        "segments": len(segment_names),
        "sufficient_data": bool(available and sufficiency.sufficient),
        "stop_reason": None if available and sufficiency.sufficient else "low_data",
    }
    rules: list[dict[str, Any]] = []
    if capability_id in {"search_queries", "ad_group_performance", "keyword_performance", "placements"}:
        waste_rows = [
            row for row in rows
            if _row_number(row, "conversions", "goal_conversions") == 0
            and _row_number(row, "clicks") >= 20
            and _row_number(row, "cost") >= (target_cpa if target_cpa > 0 else 500)
        ]
        waste_cost = round(sum(_row_number(row, "cost") for row in waste_rows), 2)
        passed = bool(available and sufficiency.sufficient and waste_rows)
        rules.append({
            "rule_code": f"{capability_id}_waste_without_goals",
            "parameters": {**sufficiency.parameters, "minimum_clicks": 20},
            "result": {"matching_rows": len(waste_rows), "waste_cost": waste_cost},
            "passed": passed,
            "evidence": [f"rows={len(waste_rows)}", f"waste_cost={waste_cost:.2f}"],
        })
    elif capability_id in {"devices", "geo"}:
        comparable = [row for row in rows if _row_number(row, "clicks") >= 15]
        cpas = [
            _row_number(row, "cost") / _row_number(row, "conversions", "goal_conversions")
            for row in comparable if _row_number(row, "conversions", "goal_conversions") > 0
        ]
        ratio = max(cpas) / min(cpas) if len(cpas) >= 2 and min(cpas) > 0 else 0
        passed = bool(available and sufficiency.sufficient and ratio >= 1.5)
        rules.append({
            "rule_code": f"{capability_id}_cpa_segment_gap",
            "parameters": {**sufficiency.parameters, "minimum_ratio": 1.5},
            "result": {"comparable_segments": len(comparable), "cpa_ratio": round(ratio, 3)},
            "passed": passed,
            "evidence": [f"comparable_segments={len(comparable)}", f"cpa_ratio={ratio:.3f}"],
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
    elif capability_id == "goals":
        has_goal_values = any(
            "conversions" in row or "goal_conversions" in row for row in rows
        )
        passed = bool(available and rows and has_goal_values)
        rules.append({
            "rule_code": "selected_goal_data_available",
            "parameters": {"requires_goal_metric": True},
            "result": {"rows_with_goal_metric": sum(1 for row in rows if "conversions" in row or "goal_conversions" in row)},
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
    related = [item for item in results if item.get("hypothesis_id") == hypothesis_id]
    by_request = {item.get("request_id"): item for item in related}
    required = [item for item in requests if item.get("required_for_conclusion")]
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
    requested_capabilities = {
        str(item.get("capability_id") or item.get("dimension") or "") for item in requests
    }
    prerequisite_codes = set(hypothesis.get("prerequisite_rule_codes") or [])
    confirmation_codes = set(hypothesis.get("confirmation_rule_codes") or [])
    rejection_codes = set(hypothesis.get("rejection_rule_codes") or [])
    if not prerequisite_codes and "goals" in requested_capabilities:
        prerequisite_codes.add("selected_goal_data_available")
    if not confirmation_codes:
        confirmation_codes.update(
            rule_code
            for capability, rule_code in CONFIRMATION_RULE_BY_CAPABILITY.items()
            if capability in requested_capabilities
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
        "evidence_summaries": summaries,
        "confirmation_rules": rules,
        "matched_confirmation_rules": matching_confirmation_rules,
        "matched_rejection_rules": matching_rejection_rules,
        "has_passed_confirmation_rule": bool(matching_confirmation_rules),
        "has_sufficient_evidence": any(item.get("sufficient_data") for item in summaries),
    }
