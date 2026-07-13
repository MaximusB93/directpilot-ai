from __future__ import annotations

import json
from pathlib import Path

from app.ai.evals.schema import EvalCase


EVAL_CASES_DIR = Path(__file__).resolve().parent / "cases"
CASCADE_EVAL_CASES_DIR = Path(__file__).resolve().parent / "cascade_cases"


def load_eval_case(path: Path) -> EvalCase:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EvalCase.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"Invalid AI eval case '{path.name}': {exc}") from exc


def load_eval_cases() -> list[EvalCase]:
    paths = sorted(EVAL_CASES_DIR.glob("*.json"))
    if not paths:
        raise RuntimeError("DirectPilot AI evaluation dataset contains no cases.")

    cases = [load_eval_case(path) for path in paths]
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("DirectPilot AI evaluation case ids must be unique.")
    return cases


def load_cascade_eval_cases() -> list[EvalCase]:
    """Load cascade-only regressions without changing the frozen baseline dataset."""

    paths = sorted(CASCADE_EVAL_CASES_DIR.glob("*.json"))
    if not paths:
        raise RuntimeError("DirectPilot cascade evaluation dataset contains no cases.")
    cases = [load_eval_case(path) for path in paths]
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("DirectPilot cascade evaluation case ids must be unique.")
    return cases
