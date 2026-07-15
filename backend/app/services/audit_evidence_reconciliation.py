from __future__ import annotations

import hashlib
from typing import Any

from app.services.audit_evidence import HYPOTHESIS_EVIDENCE_POLICY, evaluate_capability_evidence


AVAILABLE_EVIDENCE_STATUSES = {"collected", "cached", "partial"}


def campaign_scope_key(value: Any) -> str | None:
    """Return an opaque backend-only campaign identity without exposing Direct IDs."""

    text = str(value or "").strip()
    if not text:
        return None
    return "campaign:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def ensure_trusted_campaign_scopes(snapshot: dict[str, Any]) -> dict[str, str]:
    scopes = snapshot.setdefault("_trustedCampaignScopes", {})
    if not isinstance(scopes, dict):
        scopes = {}
        snapshot["_trustedCampaignScopes"] = scopes
    for item in snapshot.get("campaignClassifications") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("campaign_name") or item.get("campaignName") or "").strip()
        scope = str(item.get("campaign_scope_key") or item.get("campaignScopeKey") or "").strip()
        if name and scope:
            scopes[name] = scope
    return {str(key): str(value) for key, value in scopes.items() if key and value}


def _scope_for(snapshot: dict[str, Any], campaign_name: Any) -> str | None:
    name = str(campaign_name or "").strip()
    if name == "__all_campaigns__":
        return "account"
    return ensure_trusted_campaign_scopes(snapshot).get(name)


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
    for result in results:
        if not isinstance(result, dict):
            continue
        request_id = str(result.get("request_id") or "")
        request = requests.get(request_id) or {}
        campaign_name = str(result.get("campaign_name") or request.get("campaign_name") or "")
        scope_key = _scope_for(snapshot, campaign_name)
        if not scope_key:
            continue
        capability = str(result.get("capability_id") or result.get("dimension") or "")
        if not capability:
            continue
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
            "rowsSentToAi": int(samples.get(request_id) or 0),
            "dataQuality": quality,
            "qualityReason": reason,
            "source": str(result.get("source") or result.get("source_type") or "unavailable"),
            "period": dict(result.get("period") or request.get("period") or {}),
            "freshness": result.get("freshness"),
            "fetchedAt": result.get("fetched_at"),
            "limitations": [str(item)[:300] for item in (result.get("limitations") or [])[:5]],
            "result": result,
            "request": request,
        })
    return {
        "entries": entries,
        "byScopeCapability": {
            (item["scopeKey"], item["capabilityId"]): item for item in entries
        },
    }


def evidence_for_hypothesis(
    snapshot: dict[str, Any], hypothesis: dict[str, Any], index: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hypothesis_id = str(hypothesis.get("hypothesis_id") or "")
    campaign_name = str(hypothesis.get("campaign_name") or "")
    scope_key = _scope_for(snapshot, campaign_name)
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


def canonical_coverage_projection(index: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "accountWide": account,
        "campaignScoped": campaigns,
        "summary": {
            "accountCapabilities": len(account),
            "campaignCapabilities": len(campaigns),
            "rowsReceived": sum(int(item.get("rowsReceived") or 0) for item in account + campaigns),
            "rowsAnalyzedByBackend": sum(int(item.get("rowsAnalyzedByBackend") or 0) for item in account + campaigns),
            "rowsSentToAi": sum(int(item.get("rowsSentToAi") or 0) for item in account + campaigns),
        },
    }


def collected_capabilities_for_campaign(
    snapshot: dict[str, Any], index: dict[str, Any], campaign_name: str,
) -> dict[str, dict[str, Any]]:
    scope = _scope_for(snapshot, campaign_name)
    return {
        str(item["capabilityId"]): item
        for item in index.get("entries") or []
        if item.get("scopeKey") == scope
        and int(item.get("rowsReceived") or 0) > 0
        and item.get("status") in AVAILABLE_EVIDENCE_STATUSES
    }
