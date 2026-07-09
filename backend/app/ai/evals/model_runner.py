from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ai.evals.loader import load_eval_cases
from app.ai.evals.schema import EvalCase
from app.ai.prompt_loader import get_system_prompt_metadata
from app.services.openrouter import build_openrouter_trace_metadata, generate_openrouter_response


EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_OUTPUTS_DIR = EVALS_DIR / "model_outputs"
DEFAULT_MAX_TOKENS = 1200


def safe_model_name(model: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", model.strip())
    safe = re.sub(r"_+", "_", safe).strip("._-")
    if not safe:
        raise ValueError("Model id cannot be empty.")
    return safe[:120]


def build_eval_prompt(case: EvalCase) -> str:
    case_payload = {
        "case_id": case.id,
        "title": case.title,
        "description": case.description,
        "task": case.task,
        "tags": case.tags,
        "input_data": case.input_data,
    }
    return f"""
Analyze this Yandex Direct campaign evaluation case.

Use only the provided case data. Do not invent missing metrics, business facts, goal conversions, or campaign history.
If data is insufficient, say so explicitly. Separate facts, assumptions, recommendations, and risks.
Do not apply changes to Yandex Direct. Do not claim that changes were applied.
Any recommendation that can affect budget, bids, strategy, campaigns, keywords, or negative keywords must require human approval.

Return strict JSON without Markdown:
{{
  "summary": "string",
  "findings": ["string"],
  "recommendations": ["string"],
  "risks": ["string"],
  "risk_level": "low|medium|high|unknown",
  "requires_human_approval": true
}}

Evaluation case:
{json.dumps(case_payload, ensure_ascii=False, indent=2)}
""".strip()


def _parse_response(raw_response: str) -> dict[str, Any]:
    stripped = raw_response.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(stripped[start : end + 1])
            if isinstance(parsed, dict):
                return {
                    "summary": str(parsed.get("summary") or "").strip() or raw_response[:500],
                    "findings": [str(item) for item in parsed.get("findings") or [] if str(item).strip()],
                    "recommendations": [str(item) for item in parsed.get("recommendations") or [] if str(item).strip()],
                    "risks": [str(item) for item in parsed.get("risks") or [] if str(item).strip()],
                    "risk_level": str(parsed.get("risk_level") or parsed.get("riskLevel") or "unknown").lower(),
                    "requires_human_approval": bool(
                        parsed.get("requires_human_approval", parsed.get("requiresHumanApproval", True))
                    ),
                }
        except (TypeError, ValueError):
            pass
    return {
        "summary": raw_response[:500],
        "findings": [],
        "recommendations": [raw_response],
        "risks": ["Free-form response could not be parsed as strict JSON."],
        "risk_level": "unknown",
        "requires_human_approval": True,
    }


def _output_payload(case: EvalCase, model: str, raw_response: str, prompt: str) -> dict[str, Any]:
    metadata = get_system_prompt_metadata()
    trace = build_openrouter_trace_metadata(model, task="ai_recommendations_eval")
    return {
        "case_id": case.id,
        "model": model,
        "provider": "openrouter",
        "system_prompt_version": metadata["version"],
        "system_prompt_hash": metadata["hash"][:12],
        "task": "ai_recommendations_eval",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "response": _parse_response(raw_response),
        "raw_response": raw_response,
        "request_debug": {
            "model": model,
            "case_id": case.id,
            "task": "ai_recommendations_eval",
            "system_prompt_version": trace["system_prompt_version"],
            "system_prompt_hash": trace["system_prompt_hash"],
            "system_prompt_source": trace["system_prompt_source"],
            "prompt_chars": len(prompt),
        },
    }


async def run_model_on_case(case: EvalCase, model: str, dry_run: bool = False) -> dict[str, Any]:
    prompt = build_eval_prompt(case)
    if dry_run:
        metadata = get_system_prompt_metadata()
        return {
            "case_id": case.id,
            "model": model,
            "provider": "openrouter",
            "system_prompt_version": metadata["version"],
            "system_prompt_hash": metadata["hash"][:12],
            "task": "ai_recommendations_eval",
            "dry_run": True,
            "prompt_chars": len(prompt),
        }
    response = await generate_openrouter_response(model=model, prompt=prompt, max_tokens=DEFAULT_MAX_TOKENS)
    raw_response = str(response.get("content") or "")
    payload = _output_payload(case, model, raw_response, prompt)
    payload["openrouter_response"] = {
        "model": response.get("model"),
        "usage": response.get("usage"),
        "id": response.get("id"),
    }
    return payload


def _select_cases(limit: int | None, case_id: str | None, all_cases: bool) -> list[EvalCase]:
    cases = load_eval_cases()
    if case_id:
        selected = [case for case in cases if case.id == case_id]
        if not selected:
            raise ValueError(f"Unknown eval case id: {case_id}")
        return selected
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero.")
        return cases[:limit]
    if all_cases:
        return cases
    raise ValueError("Refusing to run all eval cases without --all, --limit, or --case-id.")


def _resolve_output_dir(model: str, output_dir: Path | None) -> Path:
    return output_dir or DEFAULT_MODEL_OUTPUTS_DIR / safe_model_name(model)


async def run_model_eval(
    model: str,
    limit: int | None = None,
    case_id: str | None = None,
    output_dir: Path | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
    all_cases: bool = False,
) -> list[Path]:
    selected_cases = _select_cases(limit=limit, case_id=case_id, all_cases=all_cases)
    resolved_output_dir = _resolve_output_dir(model, output_dir)
    output_paths = [resolved_output_dir / f"{case.id}.json" for case in selected_cases]

    if dry_run:
        for case, path in zip(selected_cases, output_paths, strict=True):
            prompt = build_eval_prompt(case)
            print(f"[dry-run] {case.id} -> {path} ({len(prompt)} prompt chars)")
        return output_paths

    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for case, path in zip(selected_cases, output_paths, strict=True):
        if path.exists() and not overwrite:
            raise FileExistsError(f"Output already exists: {path}. Use --overwrite to replace it.")
        payload = await run_model_on_case(case, model=model, dry_run=False)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written_paths.append(path)
        print(f"Saved {case.id} -> {path}")
    return written_paths


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual OpenRouter model runner for DirectPilot eval cases.")
    parser.add_argument("--model", required=True, help="OpenRouter model id, for example google/gemma-3-12b-it.")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N cases.")
    parser.add_argument("--case-id", default=None, help="Run one eval case by id.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for saved outputs.")
    parser.add_argument("--dry-run", action="store_true", help="Do not call OpenRouter and do not write outputs.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files.")
    parser.add_argument("--all", action="store_true", help="Explicitly run the full eval dataset.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        paths = asyncio.run(
            run_model_eval(
                model=args.model,
                limit=args.limit,
                case_id=args.case_id,
                output_dir=args.output_dir,
                dry_run=args.dry_run,
                overwrite=args.overwrite,
                all_cases=args.all,
            )
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")
    if args.dry_run:
        print(f"Dry run complete. Planned outputs: {len(paths)}")
    else:
        print(f"Model eval complete. Saved outputs: {len(paths)}")


if __name__ == "__main__":
    main()
