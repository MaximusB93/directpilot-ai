from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClientAccount, DirectCampaignDailyStat


DEFAULT_PERIODS = [7, 14, 30]


@dataclass(frozen=True)
class Window:
    name: str
    date_from: date
    date_to: date


def _date_to(today: date | None) -> date:
    return (today or datetime.now(UTC).date()) - timedelta(days=1)


def _windows(date_to: date) -> dict[str, Window]:
    return {
        "last7": Window("last7", date_to - timedelta(days=6), date_to),
        "previous7": Window("previous7", date_to - timedelta(days=13), date_to - timedelta(days=7)),
        "last14": Window("last14", date_to - timedelta(days=13), date_to),
        "previous14": Window("previous14", date_to - timedelta(days=27), date_to - timedelta(days=14)),
        "last30": Window("last30", date_to - timedelta(days=29), date_to),
    }


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _pct_delta(current: float | None, previous: float | None) -> float | None:
    current_value = float(current or 0)
    previous_value = float(previous or 0)
    if previous_value == 0:
        return 0.0 if current_value == 0 else None
    return _round((current_value - previous_value) / previous_value * 100)


def _aggregate(rows: list[DirectCampaignDailyStat]) -> dict[str, Any]:
    cost = sum(item.cost or 0 for item in rows)
    impressions = sum(item.impressions or 0 for item in rows)
    clicks = sum(item.clicks or 0 for item in rows)
    goal_conversions = sum(item.goal_conversions or 0 for item in rows)
    return {
        "cost": _round(cost),
        "impressions": impressions,
        "clicks": clicks,
        "ctr": _round(clicks / impressions * 100) if impressions else 0.0,
        "avgCpc": _round(cost / clicks) if clicks else 0.0,
        "goalConversions": _round(goal_conversions),
        "goalCpa": _round(cost / goal_conversions) if goal_conversions else None,
        "conversionRate": _round(goal_conversions / clicks * 100) if clicks else 0.0,
    }


def _changes(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, float | None]:
    return {
        "costDeltaPct": _pct_delta(current.get("cost"), previous.get("cost")),
        "clicksDeltaPct": _pct_delta(current.get("clicks"), previous.get("clicks")),
        "impressionsDeltaPct": _pct_delta(current.get("impressions"), previous.get("impressions")),
        "ctrDeltaPct": _pct_delta(current.get("ctr"), previous.get("ctr")),
        "avgCpcDeltaPct": _pct_delta(current.get("avgCpc"), previous.get("avgCpc")),
        "goalConversionsDeltaPct": _pct_delta(current.get("goalConversions"), previous.get("goalConversions")),
        "goalCpaDeltaPct": _pct_delta(current.get("goalCpa"), previous.get("goalCpa")),
    }


def _between(rows: list[DirectCampaignDailyStat], window: Window) -> list[DirectCampaignDailyStat]:
    return [item for item in rows if window.date_from <= item.stat_date <= window.date_to]


def _campaign_key(item: DirectCampaignDailyStat) -> str:
    return item.campaign_id or item.campaign_name


def _classify_campaign(
    *,
    last7: dict[str, Any],
    previous7: dict[str, Any],
    changes7: dict[str, float | None],
    target_cpa: int | None,
) -> list[str]:
    flags: list[str] = []
    clicks = int(last7.get("clicks") or 0)
    impressions = int(last7.get("impressions") or 0)
    cost = float(last7.get("cost") or 0)
    conversions = float(last7.get("goalConversions") or 0)
    goal_cpa = last7.get("goalCpa")
    previous_conversions = float(previous7.get("goalConversions") or 0)

    if impressions < 100 or clicks < 10:
        flags.append("low_data")
    if cost > 0 and conversions == 0 and clicks >= 10:
        flags.append("spend_without_conversions")
    if target_cpa and goal_cpa is not None and goal_cpa > target_cpa * 1.25:
        flags.append("high_cpa")
    if changes7.get("goalCpaDeltaPct") is not None and changes7["goalCpaDeltaPct"] > 30 and clicks >= 10:
        flags.append("cpa_growth")
    if (
        changes7.get("goalConversionsDeltaPct") is not None
        and changes7["goalConversionsDeltaPct"] < -30
        and previous_conversions > 0
        and changes7.get("costDeltaPct") is not None
        and changes7["costDeltaPct"] >= -10
    ):
        flags.append("conversion_drop")
    if changes7.get("ctrDeltaPct") is not None and changes7["ctrDeltaPct"] < -20 and impressions >= 100:
        flags.append("ctr_drop")
    if changes7.get("avgCpcDeltaPct") is not None and changes7["avgCpcDeltaPct"] > 25 and clicks >= 10:
        flags.append("cpc_growth")
    if (
        (changes7.get("clicksDeltaPct") is not None and changes7["clicksDeltaPct"] < -30)
        or (changes7.get("impressionsDeltaPct") is not None and changes7["impressionsDeltaPct"] < -30)
    ) and previous7.get("clicks", 0):
        flags.append("volume_drop")
    if (
        target_cpa
        and goal_cpa is not None
        and goal_cpa <= target_cpa
        and conversions > 0
        and (changes7.get("goalConversionsDeltaPct") or 0) > 0
    ):
        flags.append("promising_growth")
    return flags or ["ok"]


def _severity(flags: list[str]) -> str:
    if any(item in flags for item in ["spend_without_conversions", "high_cpa", "conversion_drop"]):
        return "critical"
    if any(item in flags for item in ["cpa_growth", "ctr_drop", "cpc_growth", "volume_drop"]):
        return "warning"
    if "promising_growth" in flags:
        return "opportunity"
    if "low_data" in flags:
        return "info"
    return "ok"


def _drilldown_for_flag(flag: str) -> tuple[list[str], list[str], list[str]]:
    mapping = {
        "spend_without_conversions": (
            ["search_queries", "goals", "landing", "strategy"],
            ["search query report", "goal tracking check", "landing page conversion path"],
            ["manual_review", "negative_keyword_draft", "tracking_fix_draft"],
        ),
        "high_cpa": (
            ["search_queries", "ad_groups", "goals", "landing"],
            ["query-level spend", "ad group split", "selected goal validity"],
            ["manual_review", "budget_reallocation_draft"],
        ),
        "cpa_growth": (
            ["search_queries", "bids", "auction", "competitors"],
            ["CPC change", "query mix", "strategy settings"],
            ["manual_review", "dry_run"],
        ),
        "conversion_drop": (
            ["goals", "landing", "search_queries", "ads"],
            ["goal availability", "landing errors", "query intent shift"],
            ["manual_review", "tracking_fix_draft"],
        ),
        "ctr_drop": (
            ["ads", "keywords", "search_queries"],
            ["ad text relevance", "query intent", "keyword match type"],
            ["manual_review", "improve_ads_draft"],
        ),
        "cpc_growth": (
            ["bids", "auction", "competitors", "strategy"],
            ["bid strategy", "auction pressure", "average CPC by query"],
            ["manual_review", "dry_run"],
        ),
        "volume_drop": (
            ["budget", "impressions", "bids", "moderation_status"],
            ["budget limits", "impression share", "campaign status"],
            ["manual_review"],
        ),
        "promising_growth": (
            ["budget", "search_queries", "audiences"],
            ["lead quality", "incremental volume", "query quality"],
            ["manual_review", "budget_reallocation_draft"],
        ),
    }
    return mapping.get(flag, (["campaign"], ["more daily data"], ["manual_review"]))


def _missing_days(rows: list[DirectCampaignDailyStat], date_from: date, date_to: date) -> list[str]:
    present = {item.stat_date for item in rows}
    missing: list[str] = []
    current = date_from
    while current <= date_to:
        if current not in present:
            missing.append(current.isoformat())
        current += timedelta(days=1)
    return missing


def analyze_campaign_dynamics(
    db: Session,
    client_id: str,
    periods: list[int] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    requested_periods = periods or DEFAULT_PERIODS
    client = db.get(ClientAccount, client_id)
    target_cpa = client.target_cpa if client else None
    date_to = _date_to(today)
    windows = _windows(date_to)
    date_from = windows["last30"].date_from
    rows = list(
        db.scalars(
            select(DirectCampaignDailyStat)
            .where(
                DirectCampaignDailyStat.client_id == client_id,
                DirectCampaignDailyStat.stat_date >= date_from,
                DirectCampaignDailyStat.stat_date <= date_to,
            )
            .order_by(DirectCampaignDailyStat.stat_date.asc(), DirectCampaignDailyStat.campaign_name.asc())
        )
    )
    campaigns = sorted({_campaign_key(item) for item in rows if _campaign_key(item)})
    missing_days = _missing_days(rows, date_from, date_to)
    has_goal_data = any(item.goal_conversions is not None for item in rows)

    account: dict[str, Any] = {}
    for name in ["last7", "previous7", "last14", "previous14", "last30"]:
        account[name] = _aggregate(_between(rows, windows[name]))
    account["changes"] = {
        "last7VsPrevious7": _changes(account["last7"], account["previous7"]),
        "last14VsPrevious14": _changes(account["last14"], account["previous14"]),
    }

    campaign_items: list[dict[str, Any]] = []
    for campaign_key in campaigns:
        campaign_rows = [item for item in rows if _campaign_key(item) == campaign_key]
        name = campaign_rows[0].campaign_name if campaign_rows else campaign_key
        item_windows = {name_key: _aggregate(_between(campaign_rows, window)) for name_key, window in windows.items()}
        changes7 = _changes(item_windows["last7"], item_windows["previous7"])
        flags = _classify_campaign(
            last7=item_windows["last7"],
            previous7=item_windows["previous7"],
            changes7=changes7,
            target_cpa=target_cpa,
        )
        severity = _severity(flags)
        campaign_items.append(
            {
                "campaignId": campaign_rows[0].campaign_id if campaign_rows else campaign_key,
                "campaignName": name,
                "severity": severity,
                "issueFlags": flags,
                "last7": item_windows["last7"],
                "previous7": item_windows["previous7"],
                "last14": item_windows["last14"],
                "previous14": item_windows["previous14"],
                "last30": item_windows["last30"],
                "changes": {"last7VsPrevious7": changes7},
            }
        )

    severity_rank = {"critical": 0, "warning": 1, "info": 2, "ok": 3, "opportunity": 4}
    worst = sorted(
        [item for item in campaign_items if item["severity"] in {"critical", "warning", "info"}],
        key=lambda item: (severity_rank.get(item["severity"], 9), -(item["last7"].get("cost") or 0)),
    )[:8]
    best = sorted(
        [item for item in campaign_items if item["severity"] in {"opportunity", "ok"}],
        key=lambda item: (item["severity"] != "opportunity", -(item["last7"].get("goalConversions") or 0), item["last7"].get("goalCpa") or 999999),
    )[:8]

    drilldown = []
    recommendations = []
    for item in worst[:6]:
        primary = next((flag for flag in item["issueFlags"] if flag != "low_data"), item["issueFlags"][0])
        next_level, needed, safe_actions = _drilldown_for_flag(primary)
        why = f"{item['campaignName']}: {primary}; last7 cost={item['last7']['cost']}, goalConversions={item['last7']['goalConversions']}, goalCpa={item['last7']['goalCpa']}."
        drilldown.append(
            {
                "campaignName": item["campaignName"],
                "issue": primary,
                "why": why,
                "nextLevel": next_level,
                "neededData": needed,
                "safeActions": safe_actions,
            }
        )
        recommendations.append(
            {
                "priority": "high" if item["severity"] == "critical" else "medium",
                "actionType": "manual_review",
                "title": f"Check dynamics for {item['campaignName']}",
                "evidence": why,
                "requiresApproval": True,
            }
        )

    limitations = []
    if not rows:
        limitations.append("No cached daily campaign stats. Run Yandex Direct sync.")
    elif len(missing_days) > 3:
        limitations.append("Daily campaign cache is incomplete; trend confidence is limited.")
    if not has_goal_data:
        limitations.append("Selected goal conversions are missing in daily campaign stats.")

    return {
        "period": {
            "dateTo": date_to.isoformat(),
            "windows": {
                key: {"dateFrom": window.date_from.isoformat(), "dateTo": window.date_to.isoformat()}
                for key, window in windows.items()
                if key in {"last7", "previous7", "last14", "previous14", "last30"}
            },
            "requestedPeriods": requested_periods,
        },
        "dataQuality": {
            "rows": len(rows),
            "campaigns": len(campaigns),
            "hasGoalData": has_goal_data,
            "missingDays": missing_days[:30],
            "limitations": limitations,
        },
        "accountDynamics": {
            **account,
            "mainFindings": [
                item["title"]
                for item in recommendations[:5]
            ],
        },
        "campaignDynamics": {
            "worstCampaigns": worst,
            "bestCampaigns": best,
            "allCampaignsCompact": campaign_items[:20],
        },
        "drilldownPlan": drilldown,
        "recommendations": recommendations,
        "missingData": limitations,
        "safety": {
            "readOnly": True,
            "canApplyAutomatically": False,
            "message": "Campaign dynamics analysis is read-only; actions are draft/manual-review only.",
        },
    }
