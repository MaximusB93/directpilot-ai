from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from app.schemas import AuditDataRequest
from app.services.yandex_direct_read_capabilities import YANDEX_DIRECT_READ_CAPABILITIES


@dataclass(frozen=True)
class AuditExecutionProfile:
    id: str
    soft_target_seconds: int
    hard_deadline_seconds: int
    finalization_reserve_seconds: int
    max_requests: int
    max_depth_rounds: int


AUDIT_EXECUTION_PROFILES: dict[str, AuditExecutionProfile] = {
    "full_account": AuditExecutionProfile(
        id="full_account",
        soft_target_seconds=7 * 60,
        hard_deadline_seconds=10 * 60,
        finalization_reserve_seconds=2 * 60,
        max_requests=96,
        max_depth_rounds=3,
    ),
    "short_summary": AuditExecutionProfile(
        id="short_summary",
        soft_target_seconds=3 * 60,
        hard_deadline_seconds=5 * 60,
        finalization_reserve_seconds=75,
        max_requests=36,
        max_depth_rounds=1,
    ),
}

_SHORT_SCOPE_ALIASES = {"summary", "short_summary", "quick_summary", "campaign_summary"}

MINIMUM_CAPABILITIES_BY_SUBTYPE: dict[str, tuple[str, ...]] = {
    "search": (
        "ad_groups", "ads", "keywords", "autotargeting", "search_queries",
        "goals", "devices", "geo",
    ),
    "brand_search": (
        "ad_groups", "ads", "keywords", "autotargeting", "search_queries",
        "goals", "devices", "geo",
    ),
    "yan_prospecting": (
        "ad_groups", "ads", "placements", "audience_targets", "goals",
        "devices", "geo", "frequency",
    ),
    "yan_retargeting": (
        "ad_groups", "ads", "placements", "audience_targets",
        "retargeting_segments", "goals", "devices", "geo", "frequency",
    ),
    "unknown": ("campaign_settings",),
}


def execution_profile_for_scope(scope: str | None) -> AuditExecutionProfile:
    normalized = str(scope or "full_account").strip().lower()
    return AUDIT_EXECUTION_PROFILES[
        "short_summary" if normalized in _SHORT_SCOPE_ALIASES else "full_account"
    ]


def initialize_scheduler_state(
    snapshot: dict[str, Any],
    *,
    scope: str | None,
    started_at: datetime,
) -> dict[str, Any]:
    profile = execution_profile_for_scope(scope)
    started = started_at if started_at.tzinfo else started_at.replace(tzinfo=UTC)
    runtime = snapshot.setdefault("auditRuntime", {})
    runtime.setdefault("executionProfile", profile.id)
    runtime.setdefault("softTargetAt", (started + timedelta(seconds=profile.soft_target_seconds)).isoformat())
    runtime.setdefault("hardDeadlineAt", (started + timedelta(seconds=profile.hard_deadline_seconds)).isoformat())
    runtime.setdefault(
        "collectionDeadlineAt",
        (started + timedelta(seconds=profile.hard_deadline_seconds - profile.finalization_reserve_seconds)).isoformat(),
    )
    runtime.setdefault("finalizationReserveSeconds", profile.finalization_reserve_seconds)
    runtime.setdefault("requestSafetyLimit", profile.max_requests)
    runtime.setdefault("maxDepthRounds", profile.max_depth_rounds)
    runtime.setdefault("schedulerPhase", "breadth")
    runtime.setdefault("lastProgressAt", started.isoformat())
    runtime.setdefault("lastSuccessfulActionAt", None)
    runtime.setdefault("nextRetryAt", None)
    runtime.setdefault("waitingReason", None)
    runtime.setdefault("recoveryStatus", "idle")
    runtime.setdefault("campaignsTotal", 0)
    runtime.setdefault("campaignsCovered", 0)
    runtime.setdefault("breadthRequestsTotal", 0)
    runtime.setdefault("breadthRequestsCompleted", 0)
    runtime.setdefault("depthRequestsTotal", 0)
    return runtime


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def scheduler_deadline_state(snapshot: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    runtime = snapshot.get("auditRuntime") or {}
    current = now or datetime.now(UTC)
    current = current if current.tzinfo else current.replace(tzinfo=UTC)
    hard = _parse_datetime(runtime.get("hardDeadlineAt"))
    collection = _parse_datetime(runtime.get("collectionDeadlineAt"))
    soft = _parse_datetime(runtime.get("softTargetAt"))
    return {
        "softReached": bool(soft and current >= soft),
        "collectionDeadlineReached": bool(collection and current >= collection),
        "hardDeadlineReached": bool(hard and current >= hard),
        "remainingSeconds": max(0, int((hard - current).total_seconds())) if hard else None,
        "hardDeadlineAt": hard.isoformat() if hard else None,
        "collectionDeadlineAt": collection.isoformat() if collection else None,
    }


def mark_scheduler_progress(
    snapshot: dict[str, Any],
    *,
    action: str,
    successful: bool = False,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    current = current if current.tzinfo else current.replace(tzinfo=UTC)
    runtime = snapshot.setdefault("auditRuntime", {})
    runtime["lastProgressAt"] = current.isoformat()
    runtime["lastAction"] = str(action)[:120]
    runtime["waitingReason"] = None
    runtime["nextRetryAt"] = None
    runtime["recoveryStatus"] = "idle"
    if successful:
        runtime["lastSuccessfulActionAt"] = current.isoformat()


def mark_scheduler_waiting(
    snapshot: dict[str, Any],
    *,
    reason: str,
    next_retry_at: datetime | str | None = None,
) -> None:
    runtime = snapshot.setdefault("auditRuntime", {})
    runtime["waitingReason"] = reason
    runtime["nextRetryAt"] = (
        next_retry_at.isoformat() if isinstance(next_retry_at, datetime) else next_retry_at
    )
    runtime["recoveryStatus"] = "waiting"


def scheduler_health(snapshot: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    runtime = snapshot.get("auditRuntime") or {}
    current = now or datetime.now(UTC)
    current = current if current.tzinfo else current.replace(tzinfo=UTC)
    next_retry = _parse_datetime(runtime.get("nextRetryAt"))
    waiting_reason = str(runtime.get("waitingReason") or "") or None
    last_progress = _parse_datetime(runtime.get("lastProgressAt"))
    age = max(0, int((current - last_progress).total_seconds())) if last_progress else 0
    expected_wait = bool(waiting_reason and (next_retry is None or next_retry >= current))
    if expected_wait:
        state = "waiting"
    elif age >= 90:
        state = "recovering"
    elif age >= 60:
        state = "delayed"
    else:
        state = "working"
    return {
        "status": state,
        "secondsSinceProgress": age,
        "waitingReason": waiting_reason,
        "nextRetryAt": next_retry.isoformat() if next_retry else None,
    }


def _period(snapshot: dict[str, Any]) -> dict[str, Any]:
    source = snapshot.get("analysisPeriod") or {}
    return {
        "date_from": source.get("dateFrom"),
        "date_to": source.get("dateTo"),
        "days": source.get("days"),
        "comparison_date_from": source.get("comparisonDateFrom"),
        "comparison_date_to": source.get("comparisonDateTo"),
    }


def build_minimum_coverage_requests(snapshot: dict[str, Any]) -> list[AuditDataRequest]:
    """Build deterministic campaign breadth requests without raw Direct identities."""

    result: list[AuditDataRequest] = []
    period = _period(snapshot)
    for campaign_index, classification in enumerate(snapshot.get("campaignClassifications") or []):
        if not isinstance(classification, dict):
            continue
        campaign_name = str(classification.get("campaign_name") or "").strip()
        family = str(classification.get("campaign_family") or "unknown")
        subtype = str(classification.get("campaign_subtype") or "unknown")
        if not campaign_name:
            continue
        for capability_index, capability_id in enumerate(MINIMUM_CAPABILITIES_BY_SUBTYPE.get(subtype, ("campaign_settings",))):
            capability = YANDEX_DIRECT_READ_CAPABILITIES.get(capability_id)
            if (
                capability is None
                or not capability.read_only
                or family not in capability.supported_families
                or subtype not in capability.supported_subtypes
            ):
                continue
            result.append(AuditDataRequest(
                request_id=f"breadth_{campaign_index:03d}_{capability_index:02d}_{capability_id}",
                hypothesis_id=f"breadth_{campaign_index:03d}",
                campaign_name=campaign_name,
                campaign_family=family,
                campaign_subtype=subtype,
                dimension=capability_id,
                capability_id=capability_id,
                reason="Минимальное применимое покрытие кампании до углубления расследования.",
                expected_information_gain="Подтвердить базовые объекты и срезы этой кампании.",
                period=period,
                filters={"campaign_name": campaign_name},
                metrics=list(capability.allowed_metrics)[:12],
                priority="high",
                required_for_conclusion=True,
                data_preference="live_preferred",
            ))
    return result


def partition_breadth_and_depth_requests(
    requests: Iterable[AuditDataRequest],
    breadth_requests: Iterable[AuditDataRequest],
    *,
    profile: AuditExecutionProfile,
) -> tuple[list[AuditDataRequest], list[AuditDataRequest]]:
    breadth_keys = {
        (item.campaign_name, item.capability_id or item.dimension)
        for item in breadth_requests
    }
    breadth: list[AuditDataRequest] = []
    depth: list[AuditDataRequest] = []
    seen: set[tuple[str, str]] = set()
    for item in requests:
        key = (item.campaign_name, item.capability_id or item.dimension)
        if key in seen:
            continue
        seen.add(key)
        (breadth if key in breadth_keys else depth).append(item)
    if profile.id == "short_summary":
        # Preserve all-account breadth, then deepen only the highest-priority
        # campaigns with a small, deterministic request allowance.
        depth = depth[: min(8, max(0, profile.max_requests - len(breadth)))]
    return breadth, depth
