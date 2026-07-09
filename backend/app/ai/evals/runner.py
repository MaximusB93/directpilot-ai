from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ai.evals.loader import load_eval_cases
from app.ai.evals.report import render_eval_report_markdown
from app.ai.evals.schema import EvalRunReport
from app.ai.evals.scorer import score_eval_case, score_missing_output


EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUTS_DIR = EVALS_DIR / "sample_outputs" / "baseline_v1"


def load_saved_eval_output(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid saved eval output '{path.name}': {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Saved eval output '{path.name}' must be a JSON object.")
    if not str(payload.get("case_id") or "").strip():
        raise ValueError(f"Saved eval output '{path.name}' must include case_id.")
    return payload


def load_saved_eval_outputs(outputs_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    directory = outputs_dir or DEFAULT_OUTPUTS_DIR
    if not directory.exists():
        raise RuntimeError(f"Saved eval outputs directory does not exist: {directory}")
    outputs: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        output = load_saved_eval_output(path)
        case_id = str(output["case_id"])
        if case_id in outputs:
            raise ValueError(f"Duplicate saved eval output for case_id '{case_id}'.")
        outputs[case_id] = output
    if not outputs:
        raise RuntimeError(f"Saved eval outputs directory contains no JSON files: {directory}")
    return outputs


def _report_model(outputs: dict[str, dict[str, Any]]) -> str:
    models = sorted({str(output.get("model") or "unknown") for output in outputs.values()})
    return models[0] if len(models) == 1 else "mixed"


def run_offline_eval(outputs_dir: Path | None = None) -> EvalRunReport:
    cases = load_eval_cases()
    outputs = load_saved_eval_outputs(outputs_dir)
    case_scores = []
    for case in cases:
        output = outputs.get(case.id)
        if output is None:
            case_scores.append(score_missing_output(case))
        else:
            case_scores.append(score_eval_case(case, output))

    known_case_ids = {case.id for case in cases}
    for extra_case_id in sorted(set(outputs) - known_case_ids):
        case_scores.append(
            score_missing_output(
                cases[0],
                note=f"Saved output references unknown case_id '{extra_case_id}'.",
            ).model_copy(update={"case_id": extra_case_id})
        )

    total_cases = len(case_scores)
    passed_cases = sum(1 for score in case_scores if score.passed)
    dangerous_count = sum(1 for score in case_scores if score.has_dangerous_violation)
    average_score = round(sum(score.score for score in case_scores) / total_cases, 2) if total_cases else 0.0
    return EvalRunReport(
        run_id=datetime.now(UTC).strftime("offline-%Y%m%dT%H%M%SZ"),
        model=_report_model(outputs),
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=total_cases - passed_cases,
        average_score=average_score,
        dangerous_violations_count=dangerous_count,
        case_scores=case_scores,
    )


def main() -> None:
    report = run_offline_eval()
    print(render_eval_report_markdown(report))


if __name__ == "__main__":
    main()
