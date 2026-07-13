from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.schemas import (
    AiAuditPeriod,
    AuditDataRequest,
    AuditDataRequestResult,
    AuditHypothesis,
    AuditHypothesisVerification,
    AuditInvestigationPlan,
    AuditInvestigationRound,
    AuditObservedFact,
)
from app.services.audit_evidence import evaluate_hypothesis_evidence, evaluate_metric_sufficiency

logger = logging.getLogger(__name__)

MAX_INVESTIGATION_ROUNDS = 3
MAX_HYPOTHESES_PER_AUDIT = 5
MAX_DATA_REQUESTS_PER_AUDIT = 20
MAX_REQUESTS_PER_HYPOTHESIS = 4
AVAILABLE_STATUSES = {"collected", "cached", "partial"}

CASCADE_BY_SUBTYPE: dict[str, tuple[str, ...]] = {
    "search": ("ad_groups", "keywords", "autotargeting", "search_queries", "ads", "devices", "geo", "demographics", "goals"),
    "brand_search": ("ad_groups", "search_queries", "goals", "devices", "geo"),
    "yan_prospecting": ("ad_groups", "audience_targets", "placements", "ads", "devices", "geo", "demographics", "frequency", "goals"),
    "yan_retargeting": ("retargeting_lists", "audience_targets", "placements", "ad_creative_metadata", "devices", "geo", "demographics", "frequency", "goals"),
    "unknown": ("campaigns",),
}

FORBIDDEN_BY_SUBTYPE: dict[str, tuple[str, ...]] = {
    "yan_retargeting": ("search_queries", "keywords", "autotargeting"),
}


def _period(snapshot: dict[str, Any]) -> AiAuditPeriod:
    value = snapshot.get("analysisPeriod") or {}
    return AiAuditPeriod(
        date_from=value.get("dateFrom"), date_to=value.get("dateTo"), days=value.get("days"),
        comparison_date_from=value.get("comparisonDateFrom"),
        comparison_date_to=value.get("comparisonDateTo"),
    )


def build_observed_facts(snapshot: dict[str, Any]) -> list[AuditObservedFact]:
    """Create deterministic observations. Causes remain hypotheses, never facts."""

    classifications = {
        item.get("campaign_name"): item for item in snapshot.get("campaignClassifications") or []
    }
    target_cpa = float((snapshot.get("targetKpis") or {}).get("targetCpa") or 0)
    facts: list[AuditObservedFact] = []
    period = _period(snapshot)
    comparison = snapshot.get("periodComparison") or {}
    dynamics_by_campaign = {
        item.get("name"): item
        for key in ("worstCampaigns", "bestCampaigns")
        for item in (comparison.get(key) or [])
        if item.get("name")
    }
    campaigns = [
        campaign
        for group in (snapshot.get("campaignGroups") or {}).values()
        for campaign in (group or [])
    ]
    seen: set[str] = set()
    for campaign in campaigns:
        name = str(campaign.get("name") or "Кампания без названия")
        if name in seen:
            continue
        seen.add(name)
        classification = classifications.get(name) or {
            "campaign_family": "unknown", "campaign_subtype": "unknown",
        }
        cost = float(campaign.get("cost") or 0)
        clicks = int(campaign.get("clicks") or 0)
        impressions = int(campaign.get("impressions") or 0)
        conversions = float(campaign.get("goalConversions") or 0)
        cpa = float(campaign.get("goalCpa") or 0) if conversions else None
        flags = set(campaign.get("flags") or [])
        metric = "campaign_health"
        evidence = [f"Расход {cost:.2f}; клики {clicks}; конверсии по целям {conversions:g}."]
        benchmark: float | None = None
        deviation: float | None = None
        if cost > 0 and conversions == 0:
            metric = "spend_without_goal_conversions"
        elif target_cpa and cpa is not None and cpa > target_cpa:
            metric = "cpa_above_target"
            benchmark = target_cpa
            deviation = round((cpa / target_cpa - 1) * 100, 2)
        elif "low_ctr" in flags:
            metric = "low_ctr"
        elif "low_data" in flags:
            metric = "low_data"
        elif conversions > 0 and (not target_cpa or (cpa or 0) <= target_cpa):
            metric = "good_campaign"
        sufficiency = evaluate_metric_sufficiency(
            metric,
            cost=cost,
            clicks=clicks,
            impressions=impressions,
            conversions=conversions,
            target_cpa=target_cpa,
            period_days=int(period.days or 0),
        )
        sufficient = sufficiency.sufficient
        if not sufficient and metric not in {"tracking_inconsistency", "strategy_learning"}:
            metric = "low_data"
        facts.append(AuditObservedFact(
            fact_id=f"fact_{len(facts) + 1:03d}",
            campaign_name=name,
            campaign_family=classification["campaign_family"],
            campaign_subtype=classification["campaign_subtype"],
            analysis_level="campaign",
            metric=metric,
            current_value=cpa if metric == "cpa_above_target" else cost,
            benchmark_value=benchmark,
            deviation=deviation,
            sample_size=clicks or impressions,
            sufficient_data=sufficient,
            evidence=evidence,
            source="directpilot_campaign_stats",
            period=period,
        ))
        dynamics = dynamics_by_campaign.get(name) or {}
        current = dynamics.get("last7") or {}
        previous = dynamics.get("previous7") or {}
        changes = dynamics.get("changes") or {}
        dynamics_flags = set(dynamics.get("flags") or [])
        dynamic_metric = None
        current_value = None
        benchmark_value = None
        dynamic_deviation = None
        if "conversion_drop" in dynamics_flags:
            dynamic_metric = "goal_conversions_drop"
            current_value = current.get("goalConversions")
            benchmark_value = previous.get("goalConversions")
            dynamic_deviation = changes.get("goalConversionsDeltaPct")
        elif (
            changes.get("costDeltaPct") is not None
            and float(changes["costDeltaPct"]) >= 50
            and float(current.get("cost") or 0) > 0
            and int(current.get("clicks") or 0) >= 10
        ):
            dynamic_metric = "budget_spike"
            current_value = current.get("cost")
            benchmark_value = previous.get("cost")
            dynamic_deviation = changes.get("costDeltaPct")
        elif dynamics.get("severity") in {"ok", "opportunity"} and float(current.get("goalConversions") or 0) > 0:
            dynamic_metric = "stable_efficiency"
            current_value = current.get("goalCpa")
            benchmark_value = previous.get("goalCpa")
            dynamic_deviation = changes.get("goalCpaDeltaPct")
        if dynamic_metric:
            facts.append(AuditObservedFact(
                fact_id=f"fact_{len(facts) + 1:03d}",
                campaign_name=name,
                campaign_family=classification["campaign_family"],
                campaign_subtype=classification["campaign_subtype"],
                analysis_level="campaign",
                metric=dynamic_metric,
                current_value=current_value,
                benchmark_value=benchmark_value,
                deviation=dynamic_deviation,
                sample_size=int(current.get("clicks") or current.get("impressions") or 0),
                sufficient_data=evaluate_metric_sufficiency(
                    "high_cpa" if dynamic_metric == "goal_conversions_drop" else "ctr",
                    cost=float(current.get("cost") or 0),
                    clicks=int(current.get("clicks") or 0),
                    impressions=int(current.get("impressions") or 0),
                    conversions=float(current.get("goalConversions") or 0),
                    target_cpa=target_cpa,
                    period_days=7,
                ).sufficient,
                evidence=[
                    f"Текущие 7 дней: {current_value}; предыдущие 7 дней: {benchmark_value}; изменение: {dynamic_deviation}%.",
                ],
                source="directpilot_campaign_dynamics",
                period=period,
            ))
    selected_goals = snapshot.get("selectedGoals") or {}
    if selected_goals.get("ids") and not selected_goals.get("hasGoalData"):
        facts.append(AuditObservedFact(
            fact_id=f"fact_{len(facts) + 1:03d}",
            campaign_name="Аккаунт",
            campaign_family="unknown",
            campaign_subtype="unknown",
            analysis_level="tracking",
            metric="tracking_inconsistency",
            current_value="goal_data_unavailable",
            sample_size=0,
            sufficient_data=False,
            evidence=[str(selected_goals.get("message") or "Данные по выбранным целям недоступны.")[:500]],
            source="directpilot_goal_diagnostics",
            period=period,
        ))
    return facts


def build_cascade_hypotheses(
    plan: AuditInvestigationPlan,
    facts: list[AuditObservedFact],
    *,
    round_number: int = 1,
) -> list[AuditHypothesis]:
    facts_by_campaign: dict[str, list[AuditObservedFact]] = {}
    for fact in facts:
        facts_by_campaign.setdefault(fact.campaign_name, []).append(fact)
    hypotheses = []
    for item in plan.hypotheses[:MAX_HYPOTHESES_PER_AUDIT]:
        campaign_facts = facts_by_campaign.get(item.campaign_name) or []
        fact = campaign_facts[0] if campaign_facts else None
        required = [request.capability_id or request.dimension for request in item.data_requests if request.required_for_conclusion]
        optional = [request.capability_id or request.dimension for request in item.data_requests if not request.required_for_conclusion]
        hypotheses.append(AuditHypothesis(
            hypothesis_id=item.hypothesis_id,
            fact_ids=[fact.fact_id for fact in campaign_facts[:5]],
            campaign_name=item.campaign_name,
            hypothesis=item.hypothesis,
            rationale=item.observed_fact,
            status="collecting_data" if item.data_requests else "unverified",
            priority="high" if fact and fact.metric in {"spend_without_goal_conversions", "cpa_above_target"} else "medium",
            confidence_before_verification="medium" if fact and fact.sufficient_data else "low",
            required_capabilities=required[:MAX_REQUESTS_PER_HYPOTHESIS],
            optional_capabilities=optional[:MAX_REQUESTS_PER_HYPOTHESIS],
            forbidden_capabilities=list(FORBIDDEN_BY_SUBTYPE.get(item.campaign_subtype, ())),
            confirmation_rules=["Обязательные данные получены и содержат подтверждающий измеримый сигнал."],
            rejection_rules=["Доверенные данные противоречат предполагаемой причине."],
            stop_conditions=["Доказательств достаточно", "Следующие данные недоступны", "Достигнут лимит расследования"],
            investigation_round=round_number,
            remaining_data_needed=required,
        ))
    return hypotheses


def create_investigation_round(
    *, round_number: int, facts: list[AuditObservedFact], hypotheses: list[AuditHypothesis],
    requests: list[AuditDataRequest],
) -> AuditInvestigationRound:
    return AuditInvestigationRound(
        round_number=round_number,
        observed_facts=facts,
        hypotheses=hypotheses,
        planned_requests=requests,
        pending_requests=requests,
        started_at=datetime.now(UTC).isoformat(),
    )


def trusted_evidence_for_results(results: list[dict[str, Any]]) -> list[str]:
    evidence = []
    for result in results:
        if result.get("status") not in AVAILABLE_STATUSES:
            continue
        rows = int(result.get("rows_analyzed") or 0)
        summary = str(result.get("summary") or "")[:300]
        evidence.append(
            f"{result.get('capability_id') or result.get('dimension')}: {rows} строк; {summary}"
        )
    return evidence[:8]


def enforce_hypothesis_verification(
    proposed: AuditHypothesisVerification,
    *, hypothesis: dict[str, Any], requests: list[dict[str, Any]], results: list[dict[str, Any]],
    target_cpa: float = 0,
    period_days: int = 30,
) -> AuditHypothesisVerification:
    related = [item for item in results if item.get("hypothesis_id") == proposed.hypothesis_id]
    by_request = {item.get("request_id"): item for item in related}
    required = [item for item in requests if item.get("required_for_conclusion")]
    missing_required = [
        item for item in required
        if (by_request.get(item.get("request_id")) or {}).get("status") not in AVAILABLE_STATUSES
    ]
    backend_evaluation = evaluate_hypothesis_evidence(
        {**hypothesis, "hypothesis_id": proposed.hypothesis_id},
        requests,
        results,
        target_cpa=target_cpa,
        period_days=period_days,
    )
    trusted = [
        evidence
        for rule in backend_evaluation["confirmation_rules"]
        if rule.get("passed")
        for evidence in rule.get("evidence") or []
    ][:8]
    statuses = {item.get("status") for item in related}
    fact_sufficient = bool(hypothesis.get("fact_sufficient_data", True))
    status = proposed.status
    limitations = list(proposed.limitations)
    if related and statuses == {"not_applicable"}:
        status = "not_applicable"
    elif proposed.contradicting_evidence and proposed.status == "rejected":
        status = "rejected"
    elif not backend_evaluation["has_passed_confirmation_rule"] or not fact_sufficient:
        status = "unverified"
        limitations.append("Backend не нашёл достаточного подтверждения в доверенных данных.")
    elif status == "confirmed" and (
        missing_required or not backend_evaluation["required_data_available"]
    ):
        status = "partially_confirmed" if trusted else "unverified"
        limitations.append("Не все обязательные данные или подтверждающие сигналы получены.")
    elif status == "partially_confirmed" and not proposed.supporting_evidence:
        status = "unverified"
    if any(item.get("status") in {"unavailable", "insufficient_data", "failed", "processing"} for item in related) and status == "confirmed":
        status = "partially_confirmed"
    return proposed.model_copy(update={
        "status": status,
        "supporting_evidence": trusted if status in {"confirmed", "partially_confirmed"} else [],
        "limitations": list(dict.fromkeys(limitations))[:8],
        "remaining_data_needed": [
            str(item.get("capability_id") or item.get("dimension")) for item in missing_required
        ][:8],
        "evidence_summaries": backend_evaluation["evidence_summaries"],
        "confirmation_rules": backend_evaluation["confirmation_rules"],
    })


def next_cascade_capabilities(
    *, subtype: str, already_requested: set[str], remaining_budget: int,
) -> list[str]:
    if remaining_budget <= 0:
        return []
    forbidden = set(FORBIDDEN_BY_SUBTYPE.get(subtype, ()))
    return [
        capability for capability in CASCADE_BY_SUBTYPE.get(subtype, CASCADE_BY_SUBTYPE["unknown"])
        if capability not in already_requested and capability not in forbidden
    ][: min(MAX_REQUESTS_PER_HYPOTHESIS, remaining_budget)]


def round_stop_reason(
    *, round_number: int, pending: int, processing: int, verifications: list[dict[str, Any]],
    request_count: int,
) -> str | None:
    if pending or processing:
        return None
    statuses = {item.get("status") for item in verifications}
    if statuses and statuses <= {"confirmed", "not_applicable"}:
        return "sufficient_evidence_or_rejected"
    if round_number >= MAX_INVESTIGATION_ROUNDS:
        return "max_rounds_reached"
    if request_count >= MAX_DATA_REQUESTS_PER_AUDIT:
        return "request_budget_reached"
    return None
