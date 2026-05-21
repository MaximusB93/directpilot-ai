from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx


@dataclass
class MetrikaGoalRow:
    campaign_key: str
    goal_id: str
    goal_conversions: float
    goal_revenue: float | None = None
    date: str | None = None


@dataclass
class MetrikaGoalResult:
    rows: list[MetrikaGoalRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_goal_ids(value: str | None, fallback: str | None = None) -> list[str]:
    source = value or fallback or ""
    for separator in [",", "\n", "\t"]:
        source = source.replace(separator, " ")
    seen: set[str] = set()
    result: list[str] = []
    for item in source.split(" "):
        goal_id = item.strip()
        if goal_id and goal_id not in seen:
            seen.add(goal_id)
            result.append(goal_id)
    return result


def _metric_names(goal_ids: list[str]) -> str:
    return ",".join(f"ym:s:goal{goal_id}reaches" for goal_id in goal_ids)


def load_metrika_goal_conversions(
    *,
    access_token: str,
    counter_id: str | None,
    goal_ids: list[str],
    date_from: date,
    date_to: date,
) -> MetrikaGoalResult:
    if not counter_id:
        return MetrikaGoalResult(warnings=["Metrika counter is not configured for this client."])
    if not goal_ids:
        return MetrikaGoalResult(warnings=["Conversion goal IDs are not configured."])

    params = {
        "ids": counter_id,
        "date1": date_from.isoformat(),
        "date2": date_to.isoformat(),
        "metrics": _metric_names(goal_ids),
        "dimensions": "ym:s:lastsignUTMCampaign",
        "accuracy": "full",
        "limit": 100000,
    }
    try:
        response = httpx.get(
            "https://api-metrika.yandex.net/stat/v1/data",
            params=params,
            headers={"Authorization": f"OAuth {access_token}"},
            timeout=45,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except Exception as exc:
        return MetrikaGoalResult(warnings=[f"Metrika goal data unavailable: {exc}"])

    rows: list[MetrikaGoalRow] = []
    for item in payload.get("data", []):
        dimensions = item.get("dimensions") or []
        campaign_key = str(dimensions[0].get("name") or dimensions[0].get("id") or "").strip() if dimensions else ""
        metrics = item.get("metrics") or []
        if not campaign_key:
            continue
        for index, goal_id in enumerate(goal_ids):
            value = float(metrics[index] or 0) if index < len(metrics) else 0.0
            rows.append(MetrikaGoalRow(campaign_key=campaign_key, goal_id=goal_id, goal_conversions=value))

    warnings = [] if rows else ["Metrika did not return campaign-level goal data for exact matching."]
    return MetrikaGoalResult(rows=rows, warnings=warnings)
