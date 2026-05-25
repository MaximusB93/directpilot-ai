from __future__ import annotations

import json
from typing import Any


DIRECT_ANALYST_PLAYBOOK_TEXT = """
DirectPilot Yandex Direct analyst playbook.

Analyze in this exact order:

1. Data quality
- Check whether synced Yandex Direct data exists.
- Check whether Yandex Metrika goal IDs are configured.
- Check whether goal conversions are available.
- Check whether conversion source is total Direct conversions or Metrika goals.
- Check warnings, unmatched campaigns, and goal mapping limitations.

2. Account overview
- Summarize spend, impressions, clicks, CTR, CPC, conversions used, CPA.
- Mention selected goal IDs and target CPA when configured.

3. Campaign segmentation
- critical: spend without goal conversions or high CPA.
- warning: low CTR or inefficient spend share.
- opportunity: conversions with acceptable CPA.
- low data: insufficient clicks/impressions.
- ok: no critical signals.

4. Main issues
For each issue include:
- campaign;
- metric evidence;
- why it matters;
- confidence level based on data volume;
- recommended next step.

5. Optimization actions
Generate draft actions only:
- manual_review;
- tracking_fix;
- add_negative_keywords only as a future/manual draft;
- improve_ads;
- budget_reallocation only as a draft;
- pause_campaign only as a future/manual draft.

6. Safety
- Never claim changes were applied.
- Never recommend write actions without approval.
- If goal data is missing, do not pretend CPA by goal is known.
- Mention limitations clearly.
- Answer in Russian by default.
""".strip()


def build_direct_analyst_instructions(context: dict[str, Any] | None = None) -> str:
    """Return compact prompt instructions with data-quality hints from trusted context."""

    if not context:
        return DIRECT_ANALYST_PLAYBOOK_TEXT

    summary = context.get("summary") or {}
    diagnostics = summary.get("syncDiagnostics") or context.get("syncDiagnostics") or context.get("sync_diagnostics") or {}
    goals = context.get("goals") or {}
    safety = context.get("safety") or {}
    context_hints = {
        "data_quality_level": diagnostics.get("dataQualityLevel"),
        "sync_message": diagnostics.get("message"),
        "selected_goal_ids": diagnostics.get("selectedGoalIds") or goals.get("selected_goal_ids"),
        "has_goal_data": diagnostics.get("hasGoalData") if diagnostics else goals.get("has_goal_data"),
        "conversion_source_counts": diagnostics.get("conversionSourceCounts"),
        "warnings": diagnostics.get("warnings") or context.get("warnings"),
        "no_write_actions": safety.get("no_write_actions", True),
    }
    return (
        f"{DIRECT_ANALYST_PLAYBOOK_TEXT}\n\n"
        "Trusted data-quality hints for this client:\n"
        f"{json.dumps(context_hints, ensure_ascii=False, indent=2)}"
    )
