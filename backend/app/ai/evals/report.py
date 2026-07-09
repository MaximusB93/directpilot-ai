from __future__ import annotations

import json

from app.ai.evals.schema import EvalRunReport


def _md_list(items: list[str]) -> str:
    if not items:
        return "-"
    return "<br>".join(item.replace("|", "\\|") for item in items)


def render_eval_report_markdown(report: EvalRunReport) -> str:
    lines = [
        "# DirectPilot AI Offline Eval Report",
        "",
        f"- Run ID: `{report.run_id}`",
        f"- Model: `{report.model}`",
        f"- Total cases: {report.total_cases}",
        f"- Passed cases: {report.passed_cases}",
        f"- Failed cases: {report.failed_cases}",
        f"- Average score: {report.average_score}",
        f"- Dangerous violations: {report.dangerous_violations_count}",
        "",
        "| case_id | score | passed | missed_should_find | missed_should_recommend | dangerous_violations |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for score in report.case_scores:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{score.case_id}`",
                    f"{score.score:.2f}",
                    "yes" if score.passed else "no",
                    _md_list(score.missed_should_find),
                    _md_list(score.missed_should_recommend),
                    _md_list(score.dangerous_violations),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def render_eval_report_json(report: EvalRunReport) -> str:
    return json.dumps(report.model_dump(), ensure_ascii=False, indent=2)
