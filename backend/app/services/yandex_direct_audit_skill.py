from __future__ import annotations

from collections import Counter
from typing import Any

# Adapted methodology inspired by Silverov/yandex-direct-skill, MIT license.
# Only audit methodology, scoring, benchmarks, and checklist concepts are used.
# No shell scripts, API mutation logic, or Yandex Direct write actions are included.

CATEGORIES = [
    {"id": "conversions_metrika", "title": "Conversions & Metrika", "weight": 25},
    {"id": "wasted_spend_negatives", "title": "Wasted Spend / Negatives", "weight": 20},
    {"id": "account_structure", "title": "Account Structure", "weight": 15},
    {"id": "keywords_quality", "title": "Keywords & Quality", "weight": 15},
    {"id": "ads_extensions", "title": "Ads & Extensions", "weight": 15},
    {"id": "settings_targeting", "title": "Settings & Targeting", "weight": 10},
]

SEVERITY_MULTIPLIERS = {
    "critical": 5.0,
    "high": 3.0,
    "medium": 1.5,
    "low": 0.5,
}

STATUS_SCORES = {
    "pass": 1.0,
    "warning": 0.5,
    "fail": 0.0,
}


def grade_for_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _as_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _campaigns(summary: dict) -> list[dict]:
    return [item for item in summary.get("campaigns", []) if isinstance(item, dict)]


def _goal_ids(summary: dict) -> list[str]:
    goal_ids = summary.get("selectedGoalIds") or []
    if isinstance(goal_ids, list):
        return [str(item).strip() for item in goal_ids if str(item).strip()]
    return [item.strip() for item in str(goal_ids).split(",") if item.strip()]


def _campaign_name_quality(campaigns: list[dict]) -> tuple[str, str]:
    if not campaigns:
        return "na", "No campaign data is available."
    named = [item for item in campaigns if str(item.get("campaign_name") or "").strip()]
    if len(named) < len(campaigns):
        return "warning", "Some campaigns have empty names."
    names = [str(item.get("campaign_name") or "").lower() for item in campaigns]
    has_search_or_network = any(("search" in name or "поиск" in name or "rsya" in name or "рся" in name) for name in names)
    if has_search_or_network:
        return "pass", "Campaign names contain basic search/network markers."
    return "warning", "Campaign names exist, but channel/product structure is not clear from available data."


def _check(
    *,
    category: str,
    check_id: str,
    title: str,
    status: str,
    severity: str,
    evidence: str,
    recommendation: str,
    source: str = "directpilot",
) -> dict:
    return {
        "id": check_id,
        "category": category,
        "title": title,
        "status": status,
        "severity": severity,
        "evidence": evidence,
        "recommendation": recommendation,
        "source": source,
    }


def _build_checks(summary: dict) -> list[dict]:
    campaigns = _campaigns(summary)
    totals = summary.get("totals") or {}
    diagnostics = summary.get("syncDiagnostics") or {}
    search_insights = summary.get("searchQueryInsights") or {}
    goal_ids = _goal_ids(summary)
    has_goal_data = bool(summary.get("hasGoalData"))
    warnings = list(summary.get("goalDataWarnings") or []) + list(diagnostics.get("warnings") or [])
    target_cpa = _as_number((summary.get("client") or {}).get("target_cpa") or summary.get("targetCpa"), 0)
    if not target_cpa:
        target_cpa = _as_number(summary.get("target_cpa"), 0)

    total_cost = _as_number(totals.get("cost"))
    total_clicks = _as_number(totals.get("clicks"))
    total_impressions = _as_number(totals.get("impressions"))
    total_conversions = _as_number(totals.get("conversions"))
    account_ctr = (total_clicks / total_impressions * 100) if total_impressions else 0

    spend_without_conversions = [
        item for item in campaigns if "spend_without_conversions" in (item.get("issue_flags") or [])
    ]
    high_cpa = [item for item in campaigns if "high_cpa" in (item.get("issue_flags") or [])]
    low_ctr = [item for item in campaigns if "low_ctr" in (item.get("issue_flags") or [])]
    low_data = [item for item in campaigns if "low_data" in (item.get("issue_flags") or [])]
    search_candidates = int(search_insights.get("candidateNegativeKeywords") or 0)
    waste_cost = _as_number(search_insights.get("totalWasteCost"))
    source_counts = diagnostics.get("conversionSourceCounts") or {}
    fallback_used = bool(goal_ids and not has_goal_data) or bool(source_counts.get("fallback_total_when_goal_unavailable"))

    name_status, name_evidence = _campaign_name_quality(campaigns)

    checks = [
        _check(
            category="conversions_metrika",
            check_id="YD01",
            title="Metrika counter configured",
            status="pass" if (summary.get("client") or {}).get("metrica_counter") else "warning",
            severity="critical",
            evidence="Client settings include a Metrika counter." if (summary.get("client") or {}).get("metrica_counter") else "Metrika counter is missing or not available in summary.",
            recommendation="Add the Metrika counter in client settings.",
        ),
        _check(
            category="conversions_metrika",
            check_id="YD02",
            title="Conversion goal IDs configured",
            status="pass" if goal_ids else "fail",
            severity="critical",
            evidence=f"Selected goal IDs: {', '.join(goal_ids)}." if goal_ids else "No selected goal IDs are configured.",
            recommendation="Add one or more Yandex Direct/Metrika goal IDs for CPA-based analysis.",
        ),
        _check(
            category="conversions_metrika",
            check_id="YD03",
            title="Selected Direct goal conversions available",
            status="pass" if has_goal_data else ("fail" if goal_ids else "na"),
            severity="critical",
            evidence=summary.get("conversionsSourceMessage") or "No conversion source message is available.",
            recommendation="Run sync and verify that Yandex Direct returns conversions for the selected goals.",
            source="directpilot" if goal_ids else "needs_more_data",
        ),
        _check(
            category="conversions_metrika",
            check_id="YD04",
            title="Fallback to total conversions is not used",
            status="fail" if fallback_used else ("pass" if has_goal_data else "na"),
            severity="high",
            evidence="Total Direct conversions are used as fallback." if fallback_used else "Selected-goal conversions are the active source." if has_goal_data else "No synced conversion data.",
            recommendation="Check selected goal IDs and report availability before trusting CPA by goal.",
            source="directpilot" if goal_ids else "needs_more_data",
        ),
        _check(
            category="wasted_spend_negatives",
            check_id="YD10",
            title="Search query negative candidates",
            status="fail" if search_candidates >= 5 else "warning" if search_candidates else "pass",
            severity="critical",
            evidence=f"{search_candidates} negative keyword candidates; waste cost {waste_cost:.2f}.",
            recommendation="Review candidates and save safe negative keyword drafts. Do not apply automatically.",
        ),
        _check(
            category="wasted_spend_negatives",
            check_id="YD12",
            title="Search query report freshness",
            status="pass" if search_insights.get("totalQueries") else "na",
            severity="critical",
            evidence=f"Analyzed queries: {search_insights.get('totalQueries') or 0}.",
            recommendation="Run sync to load search query statistics if unavailable.",
            source="directpilot" if search_insights.get("totalQueries") else "needs_more_data",
        ),
        _check(
            category="wasted_spend_negatives",
            check_id="YD17",
            title="Spend without selected-goal conversions",
            status="fail" if spend_without_conversions else "pass" if campaigns else "na",
            severity="high",
            evidence=f"{len(spend_without_conversions)} campaigns spend without selected-goal conversions.",
            recommendation="Review search queries, landing pages, goals, and budget allocation.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="account_structure",
            check_id="YD19",
            title="Search/RSYA or channel structure is visible",
            status=name_status,
            severity="medium",
            evidence=name_evidence,
            recommendation="Use campaign naming that exposes channel, geo, product, and intent.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="account_structure",
            check_id="YD20",
            title="Account structure depth",
            status="warning" if len(campaigns) == 1 else "pass" if len(campaigns) > 1 else "na",
            severity="medium",
            evidence=f"Campaigns in summary: {len(campaigns)}.",
            recommendation="Split campaigns by product, geo, and intent where useful.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="keywords_quality",
            check_id="YD34",
            title="Low CTR campaign signals",
            status="fail" if len(low_ctr) >= 3 else "warning" if low_ctr else "pass" if campaigns else "na",
            severity="high",
            evidence=f"{len(low_ctr)} low CTR campaigns. Account CTR: {account_ctr:.2f}%.",
            recommendation="Review ad relevance, query intent, and extensions for low CTR segments.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="keywords_quality",
            check_id="YD30",
            title="Enough data for keyword-quality decisions",
            status="warning" if low_data else "pass" if campaigns else "na",
            severity="medium",
            evidence=f"{len(low_data)} campaigns have low data volume.",
            recommendation="Accumulate more clicks/impressions before making aggressive optimization decisions.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="ads_extensions",
            check_id="YD39",
            title="Sitelinks and extensions",
            status="na",
            severity="high",
            evidence="DirectPilot has not loaded ad extension data yet.",
            recommendation="Check sitelinks, callouts, images, and vCard manually in Yandex Direct.",
            source="needs_more_data",
        ),
        _check(
            category="ads_extensions",
            check_id="YD43",
            title="UTM tracking quality",
            status="na",
            severity="high",
            evidence="DirectPilot has not loaded landing URL/UTM data yet.",
            recommendation="Verify UTM tags manually or add read-only URL diagnostics later.",
            source="needs_more_data",
        ),
        _check(
            category="settings_targeting",
            check_id="YD49",
            title="Target CPA benchmark",
            status="fail" if high_cpa else "pass" if target_cpa and campaigns else "na",
            severity="high",
            evidence=f"{len(high_cpa)} campaigns are above target CPA." if target_cpa else "Target CPA is not configured.",
            recommendation="Set target CPA in client settings and review high-CPA campaigns.",
            source="directpilot" if target_cpa and campaigns else "needs_more_data",
        ),
        _check(
            category="settings_targeting",
            check_id="YD51",
            title="Strategy constraints and bid modifiers",
            status="na",
            severity="medium",
            evidence="DirectPilot has not loaded bidding strategy, geo, schedule, or bid modifier settings yet.",
            recommendation="Review strategy limits and targeting settings manually.",
            source="needs_more_data",
        ),
    ]
    if warnings:
        checks.append(
            _check(
                category="conversions_metrika",
                check_id="YD06",
                title="Sync warnings reviewed",
                status="warning",
                severity="medium",
                evidence="; ".join(str(item) for item in warnings[:3]),
                recommendation="Resolve sync warnings before making final CPA decisions.",
            )
        )
    return checks


def _score_checks(checks: list[dict], category_weight: float) -> tuple[float, float, float]:
    earned = 0.0
    possible = 0.0
    for check in checks:
        status = check.get("status")
        if status == "na":
            continue
        severity = check.get("severity") or "medium"
        multiplier = SEVERITY_MULTIPLIERS.get(severity, 1.5)
        possible += multiplier
        earned += STATUS_SCORES.get(status, 0.0) * multiplier
    if not possible:
        return 0.0, earned, possible
    return round((earned / possible) * 100, 1), earned, possible


def build_yandex_direct_audit(summary: dict) -> dict:
    checks = _build_checks(summary)
    categories = []
    weighted_score = 0.0
    total_weight = 0.0
    for category in CATEGORIES:
        category_checks = [item for item in checks if item.get("category") == category["id"]]
        score, earned, possible = _score_checks(category_checks, category["weight"])
        if possible:
            weighted_score += score * category["weight"]
            total_weight += category["weight"]
        categories.append(
            {
                "id": category["id"],
                "title": category["title"],
                "weight": category["weight"],
                "score": score,
                "grade": grade_for_score(score) if possible else "N/A",
                "checks": category_checks,
            }
        )

    score = round(weighted_score / total_weight, 1) if total_weight else 0.0
    grade = grade_for_score(score)
    failed_or_warning = [item for item in checks if item.get("status") in {"fail", "warning"}]
    critical_issues = [
        item for item in failed_or_warning if item.get("severity") in {"critical", "high"}
    ][:8]
    quick_wins = [
        item
        for item in failed_or_warning
        if item.get("severity") in {"critical", "high"}
        and item.get("id") in {"YD02", "YD03", "YD04", "YD10", "YD17", "YD34", "YD49"}
    ][:6]
    recommendations = [
        {
            "title": item["title"],
            "severity": item["severity"],
            "evidence": item["evidence"],
            "recommendation": item["recommendation"],
            "safetyNote": "Draft-only recommendation. No Yandex Direct changes were applied.",
        }
        for item in failed_or_warning[:10]
    ]
    limitations = [
        {
            "id": item["id"],
            "title": item["title"],
            "evidence": item["evidence"],
            "recommendation": item["recommendation"],
        }
        for item in checks
        if item.get("status") == "na" or item.get("source") == "needs_more_data"
    ][:10]
    status_counts = Counter(item.get("status") for item in checks)
    summary_text = (
        f"Yandex Direct audit score {score}/100, grade {grade}. "
        f"Checks: pass {status_counts.get('pass', 0)}, warning {status_counts.get('warning', 0)}, "
        f"fail {status_counts.get('fail', 0)}, N/A {status_counts.get('na', 0)}."
    )
    return {
        "methodology": "55-check Yandex Direct audit framework adapted for DirectPilot read-only MVP data.",
        "frameworkChecksTotal": 55,
        "implementedChecks": len(checks),
        "score": score,
        "grade": grade,
        "summary": summary_text,
        "categories": categories,
        "criticalIssues": critical_issues,
        "quickWins": quick_wins,
        "recommendations": recommendations,
        "limitations": limitations,
    }
