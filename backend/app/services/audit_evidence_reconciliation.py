from __future__ import annotations

from typing import Any

from app.services.audit_evidence import HYPOTHESIS_EVIDENCE_POLICY, evaluate_capability_evidence
from app.services.audit_evidence_identity import (
    campaign_scope_for_name,
    campaign_scope_key,
    ensure_trusted_campaign_scopes,
    trusted_scope_names,
)
from app.services.audit_evidence_policy import DIMENSION_CAPABILITY_CANDIDATES


AVAILABLE_EVIDENCE_STATUSES = {"collected", "cached", "partial"}
ACCOUNT_DERIVABLE_CAPABILITIES = {
    "campaigns", "campaign_performance", "goals", "conversions_by_goal",
}
PRODUCTION_CAPABILITY_ALIASES: dict[str, tuple[str, ...]] = {
    "campaign_settings": ("campaigns",),
    "device": ("devices",),
    "placement": ("placements",),
    "keyword": ("keyword_performance", "keywords"),
    "ad_group": ("ad_group_performance", "ad_groups"),
    "audience": ("audience_targets",),
    "ads_creatives": ("ads",),
    "retargeting_segments_data": ("retargeting_segments", "retargeting_lists"),
    "audience_targets_data": ("audience_targets",),
    "search_queries_data": ("search_queries",),
    "campaign_settings_data": ("campaign_settings", "campaigns"),
    "campaign_performance_data": ("campaign_performance",),
    "ad_group_performance_data": ("ad_group_performance", "ad_groups"),
    "keyword_performance_data": ("keyword_performance", "keywords"),
}
for _dimension, _candidates in DIMENSION_CAPABILITY_CANDIDATES.items():
    PRODUCTION_CAPABILITY_ALIASES.setdefault(_dimension, tuple(_candidates))


def capability_candidates(value: Any) -> tuple[str, ...]:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = PRODUCTION_CAPABILITY_ALIASES.get(normalized, ())
    return tuple(dict.fromkeys((normalized, *aliases))) if normalized else ()


def _row_value(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _row_campaign_scope(
    snapshot: dict[str, Any], row: dict[str, Any], *, capability: str,
) -> tuple[str | None, str | None]:
    names = ("CampaignId", "campaign_id", "id") if capability == "campaigns" else ("CampaignId", "campaign_id")
    raw_id = _row_value(row, *names)
    scope = campaign_scope_key(raw_id)
    trusted_names = trusted_scope_names(snapshot)
    if scope and scope in trusted_names:
        return scope, trusted_names[scope]
    return None, None


def _quality_reason(result: dict[str, Any], *, target_cpa: float, period_days: int) -> tuple[str, str | None]:
    status = str(result.get("status") or "unavailable")
    rows = int(result.get("rows_analyzed") or result.get("rows_total") or len(result.get("data") or []))
    if status == "not_applicable":
        return "not_applicable", "not_applicable"
    if status not in AVAILABLE_EVIDENCE_STATUSES:
        return "unavailable", str(result.get("error_code") or status or "unavailable")
    if rows <= 0:
        return "insufficient", str(result.get("error_code") or "no_rows")
    summary, _ = evaluate_capability_evidence(
        result, target_cpa=target_cpa, period_days=period_days,
    )
    if summary.get("sufficient_data"):
        return "sufficient", None
    return "insufficient", str(summary.get("stop_reason") or "low_data")


def build_canonical_evidence_index(
    snapshot: dict[str, Any], results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Index trusted evidence by scope and capability; raw IDs and rows never leave this layer."""

    requests = {
        str(item.get("request_id")): item
        for item in snapshot.get("validatedDataRequests") or []
        if isinstance(item, dict) and item.get("request_id")
    }
    samples = {
        str(item.get("request_id")): len(item.get("data") or [])
        for item in snapshot.get("aiDrilldownSamples") or []
        if isinstance(item, dict) and item.get("request_id")
    }
    samples.update({
        str(item.get("request_id") or item.get("requestId")): int(item.get("rowsSentToAi") or 0)
        for item in snapshot.get("baselineEvidenceSummary") or []
        if isinstance(item, dict) and (item.get("request_id") or item.get("requestId"))
    })
    target_cpa = float((snapshot.get("targetKpis") or {}).get("targetCpa") or 0)
    period_days = int((snapshot.get("analysisPeriod") or {}).get("days") or 30)
    entries: list[dict[str, Any]] = []

    def append_entry(
        result: dict[str, Any], request: dict[str, Any], *,
        campaign_name: str, scope_key: str, derived_from_account: bool = False,
    ) -> None:
        request_id = str(result.get("request_id") or "")
        capability = str(result.get("capability_id") or result.get("dimension") or "")
        quality, reason = _quality_reason(
            result, target_cpa=target_cpa, period_days=period_days,
        )
        rows_received = int(result.get("rows_total") or len(result.get("data") or []))
        rows_analyzed = int(result.get("rows_analyzed") or len(result.get("data") or []))
        entries.append({
            "requestId": request_id,
            "hypothesisId": str(result.get("hypothesis_id") or request.get("hypothesis_id") or ""),
            "campaignName": campaign_name,
            "scopeKey": scope_key,
            "scope": "account" if scope_key == "account" else "campaign",
            "campaignSubtype": str(request.get("campaign_subtype") or "unknown"),
            "capabilityId": capability,
            "status": str(result.get("status") or "unavailable"),
            "rowsReceived": rows_received,
            "rowsAnalyzedByBackend": rows_analyzed,
            "rowsSentToAi": 0 if derived_from_account else int(samples.get(request_id) or 0),
            "dataQuality": quality,
            "qualityReason": reason,
            "source": str(result.get("source") or result.get("source_type") or "unavailable"),
            "period": dict(result.get("period") or request.get("period") or {}),
            "freshness": result.get("freshness"),
            "fetchedAt": result.get("fetched_at"),
            "live": bool(result.get("live")) or str(result.get("source") or "").startswith("yandex_direct_live"),
            "cached": bool(result.get("cached")) or str(result.get("status") or "") == "cached",
            "savedFallback": bool(result.get("saved_fallback")) or str(result.get("source") or "") == "directpilot_saved_stats",
            "limitations": [str(item)[:300] for item in (result.get("limitations") or [])[:5]],
            "derivedFromAccountWide": derived_from_account,
            "result": result,
            "request": request,
        })

    for result in results:
        if not isinstance(result, dict):
            continue
        request_id = str(result.get("request_id") or "")
        request = requests.get(request_id) or {}
        campaign_name = str(result.get("campaign_name") or request.get("campaign_name") or "")
        scope_key = campaign_scope_for_name(snapshot, campaign_name)
        if not scope_key:
            continue
        capability = str(result.get("capability_id") or result.get("dimension") or "")
        if not capability:
            continue
        append_entry(result, request, campaign_name=campaign_name, scope_key=scope_key)
        if scope_key != "account" or capability not in ACCOUNT_DERIVABLE_CAPABILITIES:
            continue
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in result.get("data") or []:
            if not isinstance(row, dict):
                continue
            row_scope, row_name = _row_campaign_scope(snapshot, row, capability=capability)
            if row_scope and row_name:
                grouped.setdefault((row_scope, row_name), []).append(row)
        for (row_scope, row_name), rows in grouped.items():
            scoped_result = {
                **result,
                "campaign_name": row_name,
                "rows_total": len(rows),
                "rows_analyzed": len(rows),
                "data": rows,
            }
            append_entry(
                scoped_result, request,
                campaign_name=row_name,
                scope_key=row_scope,
                derived_from_account=True,
            )
    return {
        "entries": entries,
        "byScopeCapability": {
            (item["scopeKey"], item["capabilityId"]): item for item in entries
        },
    }


def apply_canonical_coverage_to_registry(
    snapshot: dict[str, Any], index: dict[str, Any],
) -> None:
    """Close policy requirements only with evidence from the exact trusted scope."""

    registry = snapshot.get("evidenceCoverageRegistry") or []
    for requirement in registry:
        if not isinstance(requirement, dict):
            continue
        scope = str(requirement.get("campaignScopeKey") or "")
        candidates = {
            candidate
            for value in (
                requirement.get("dimension"),
                requirement.get("resolvedCapability"),
                *(requirement.get("capabilityCandidates") or []),
            )
            for candidate in capability_candidates(value)
        }
        matches = [
            item for item in index.get("entries") or []
            if item.get("scopeKey") == scope
            and str(item.get("capabilityId") or "") in candidates
        ]
        available = [
            item for item in matches
            if item.get("status") in AVAILABLE_EVIDENCE_STATUSES
            and int(item.get("rowsReceived") or 0) > 0
        ]
        if not available:
            continue
        best = max(available, key=lambda item: int(item.get("rowsReceived") or 0))
        requirement.update({
            "status": "satisfied",
            "rowsReceived": int(best.get("rowsReceived") or 0),
            "rowsAnalyzed": int(best.get("rowsAnalyzedByBackend") or 0),
            "source": str(best.get("source") or "unavailable"),
            "limitations": list(best.get("limitations") or [])[:5],
        })
    snapshot["evidenceCoverageRegistry"] = registry


def evidence_for_hypothesis(
    snapshot: dict[str, Any], hypothesis: dict[str, Any], index: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypothesis_id = str(hypothesis.get("hypothesis_id") or "")
    campaign_name = str(hypothesis.get("campaign_name") or "")
    scope_key = campaign_scope_for_name(snapshot, campaign_name)
    subtype = str(hypothesis.get("campaign_subtype") or "unknown")
    hypothesis_type = str(hypothesis.get("hypothesis_type") or "campaign_metadata_issue")
    allowed = set(HYPOTHESIS_EVIDENCE_POLICY.get(
        hypothesis_type, HYPOTHESIS_EVIDENCE_POLICY["campaign_metadata_issue"],
    )["allowed_capabilities"])
    linked_results: list[dict[str, Any]] = []
    linked_requests: list[dict[str, Any]] = []
    for entry in index.get("entries") or []:
        if entry.get("scopeKey") != scope_key or entry.get("capabilityId") not in allowed:
            continue
        request = entry.get("request") or {}
        request_subtype = str(request.get("campaign_subtype") or entry.get("campaignSubtype") or "unknown")
        if request_subtype not in {subtype, "unknown"}:
            continue
        linked_results.append({**(entry.get("result") or {}), "hypothesis_id": hypothesis_id})
        linked_requests.append({
            **request,
            "hypothesis_id": hypothesis_id,
            "campaign_name": campaign_name,
            "required_for_conclusion": bool(request.get("required_for_conclusion")),
        })
    return linked_requests, linked_results


def canonical_coverage_projection(
    index: dict[str, Any], snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def public(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "campaignName", "capabilityId", "status", "rowsReceived",
                "rowsAnalyzedByBackend", "rowsSentToAi", "dataQuality", "qualityReason",
                "source", "period", "freshness", "fetchedAt", "limitations",
            )
        }

    account = [public(item) for item in index.get("entries") or [] if item.get("scope") == "account"]
    campaigns = [public(item) for item in index.get("entries") or [] if item.get("scope") == "campaign"]
    matrix: list[dict[str, Any]] = []
    if snapshot is not None:
        expected: dict[tuple[str, str], dict[str, Any]] = {}
        for item in snapshot.get("minimumCoveragePlan") or []:
            if not isinstance(item, dict):
                continue
            key = (str(item.get("campaignName") or ""), str(item.get("capabilityId") or ""))
            if all(key):
                expected[key] = dict(item)
        for request in snapshot.get("validatedDataRequests") or []:
            if not isinstance(request, dict):
                continue
            key = (
                str(request.get("campaign_name") or ""),
                str(request.get("capability_id") or request.get("dimension") or ""),
            )
            if all(key):
                expected.setdefault(key, {
                    "campaignName": key[0], "capabilityId": key[1], "applicable": True,
                })

        entries = [item for item in index.get("entries") or [] if item.get("scope") == "campaign"]
        for (campaign_name, capability_id), planned in expected.items():
            candidates = set(capability_candidates(capability_id))
            matched = next((
                item for item in entries
                if item.get("campaignName") == campaign_name
                and str(item.get("capabilityId") or "") in candidates
            ), None)
            if matched is None:
                matrix.append({
                    "campaignName": campaign_name,
                    "capabilityId": capability_id,
                    "status": "not_requested",
                    "rowsReceived": 0,
                    "rowsAnalyzedByBackend": 0,
                    "rowsSentToAi": 0,
                    "source": None,
                    "applicable": bool(planned.get("applicable", True)),
                    "absenceReason": "not_requested",
                    "limitations": [],
                })
                continue
            raw_status = str(matched.get("status") or "unavailable")
            rows = int(matched.get("rowsReceived") or 0)
            if raw_status == "not_applicable":
                public_status = "not_applicable"
            elif raw_status in {"collected", "cached"} and rows > 0:
                public_status = "collected"
            elif raw_status == "partial":
                public_status = "partial"
            elif raw_status in {"collected", "cached", "insufficient_data"} and rows <= 0:
                public_status = "insufficient_data"
            elif (
                raw_status == "skipped_budget_limit"
                and str((matched.get("result") or {}).get("error_code") or "")
                == "audit_collection_deadline_reached"
            ):
                public_status = "not_requested"
            elif raw_status in {"unavailable", "unsupported", "skipped_budget_limit"}:
                public_status = "unavailable"
            elif raw_status == "failed":
                public_status = "failed"
            else:
                public_status = "partial"
            matrix.append({
                **public(matched),
                "campaignName": campaign_name,
                "capabilityId": capability_id,
                "status": public_status,
                "applicable": public_status != "not_applicable",
                "absenceReason": None if public_status == "collected" else (
                    matched.get("qualityReason") or raw_status
                ),
            })

    applicable = [item for item in matrix if item.get("applicable")]
    campaign_names = sorted({str(item.get("campaignName")) for item in applicable})
    terminal_statuses = {"collected", "partial", "insufficient_data", "unavailable", "failed"}
    by_campaign: dict[str, list[dict[str, Any]]] = {}
    for item in applicable:
        by_campaign.setdefault(str(item.get("campaignName")), []).append(item)
    covered_campaigns = sorted(
        campaign_name
        for campaign_name, items in by_campaign.items()
        if items and all(item.get("status") in terminal_statuses for item in items)
    )
    campaigns_with_data = sorted({
        str(item.get("campaignName"))
        for item in applicable
        if item.get("status") in {"collected", "partial"}
    })
    capability_summary: list[dict[str, Any]] = []
    for capability_id in sorted({str(item.get("capabilityId")) for item in matrix}):
        items = [item for item in matrix if str(item.get("capabilityId")) == capability_id]
        applicable_items = [item for item in items if item.get("applicable")]
        collected_items = [
            item for item in applicable_items if item.get("status") in {"collected", "partial"}
        ]
        capability_summary.append({
            "capabilityId": capability_id,
            "applicableCampaigns": len({item.get("campaignName") for item in applicable_items}),
            "coveredCampaigns": len({item.get("campaignName") for item in collected_items}),
            "rowsReceived": sum(int(item.get("rowsReceived") or 0) for item in items),
            "rowsAnalyzedByBackend": sum(int(item.get("rowsAnalyzedByBackend") or 0) for item in items),
            "rowsSentToAi": sum(int(item.get("rowsSentToAi") or 0) for item in items),
            "sources": sorted({str(item.get("source")) for item in items if item.get("source")}),
        })
    return {
        "accountWide": account,
        "campaignScoped": campaigns,
        "campaignMatrix": matrix,
        "capabilitySummary": capability_summary,
        "summary": {
            "accountCapabilities": len(account),
            "campaignCapabilities": len(campaigns),
            "rowsReceived": sum(
                int(item.get("rowsReceived") or 0)
                for item in index.get("entries") or [] if not item.get("derivedFromAccountWide")
            ),
            "rowsAnalyzedByBackend": sum(
                int(item.get("rowsAnalyzedByBackend") or 0)
                for item in index.get("entries") or [] if not item.get("derivedFromAccountWide")
            ),
            "rowsSentToAi": sum(
                int(item.get("rowsSentToAi") or 0)
                for item in index.get("entries") or [] if not item.get("derivedFromAccountWide")
            ),
            "applicableCampaigns": len(campaign_names),
            "coveredCampaigns": len(covered_campaigns),
            "campaignsWithCollectedData": campaigns_with_data,
        },
    }


def collected_capabilities_for_campaign(
    snapshot: dict[str, Any], index: dict[str, Any], campaign_name: str,
) -> dict[str, dict[str, Any]]:
    scope = campaign_scope_for_name(snapshot, campaign_name)
    return {
        str(item["capabilityId"]): item
        for item in index.get("entries") or []
        if item.get("scopeKey") == scope
        and int(item.get("rowsReceived") or 0) > 0
        and item.get("status") in AVAILABLE_EVIDENCE_STATUSES
    }
