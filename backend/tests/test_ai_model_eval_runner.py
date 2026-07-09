from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import app.ai.evals.model_runner as model_runner
from app.ai.evals.loader import load_eval_cases
from app.ai.evals.runner import run_offline_eval
from app.ai.evals.scorer import score_eval_case


def test_build_eval_prompt_hides_expected_fields() -> None:
    case = load_eval_cases()[0]
    prompt = model_runner.build_eval_prompt(case)

    assert '"input_data"' in prompt
    assert "synthetic_lead_goal" in prompt
    assert "synthetic-campaign-001" in prompt
    assert case.title in prompt
    assert case.description in prompt
    assert "expected" not in prompt
    for item in case.expected.should_find + case.expected.should_recommend + case.expected.should_not_do:
        assert item not in prompt


def test_build_eval_prompt_contains_task_rules() -> None:
    prompt = model_runner.build_eval_prompt(load_eval_cases()[0])

    assert "Analyze this Yandex Direct campaign evaluation case." in prompt
    assert "Do not invent missing metrics" in prompt
    assert "requires_human_approval" in prompt
    assert "risk_level" in prompt
    assert "Do not apply changes to Yandex Direct" in prompt


def test_safe_model_name_converts_model_id_to_directory_name() -> None:
    assert model_runner.safe_model_name("google/gemma-3-12b-it") == "google_gemma-3-12b-it"
    assert model_runner.safe_model_name(" qwen/qwen3 14b ") == "qwen_qwen3_14b"
    with pytest.raises(ValueError, match="empty"):
        model_runner.safe_model_name("///")


def test_run_model_eval_refuses_full_dataset_without_explicit_scope() -> None:
    with pytest.raises(ValueError, match="Refusing to run all eval cases"):
        asyncio.run(model_runner.run_model_eval(model="openrouter/auto", dry_run=True))


def test_dry_run_does_not_call_openrouter_or_write_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called = False

    async def fake_generate(*args, **kwargs):
        nonlocal called
        called = True
        return {"content": "{}"}

    monkeypatch.setattr(model_runner, "generate_openrouter_response", fake_generate)

    paths = asyncio.run(
        model_runner.run_model_eval(
            model="openrouter/auto",
            limit=2,
            output_dir=tmp_path,
            dry_run=True,
        )
    )

    assert called is False
    assert len(paths) == 2
    assert not any(path.exists() for path in paths)
    assert not list(tmp_path.glob("*.json"))


def test_existing_output_is_not_overwritten_without_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    case = load_eval_cases()[0]
    existing = tmp_path / f"{case.id}.json"
    existing.write_text("{}", encoding="utf-8")

    async def fake_generate(*args, **kwargs):
        return {"content": "{}"}

    monkeypatch.setattr(model_runner, "generate_openrouter_response", fake_generate)

    with pytest.raises(FileExistsError, match="Use --overwrite"):
        asyncio.run(
            model_runner.run_model_eval(
                model="openrouter/auto",
                case_id=case.id,
                output_dir=tmp_path,
            )
        )


def test_run_model_eval_with_mocked_openrouter_saves_offline_compatible_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = load_eval_cases()[0]

    async def fake_generate(model: str, prompt: str, max_tokens: int | None = None):
        assert model == "openrouter/auto"
        assert case.expected.should_find[0] not in prompt
        assert max_tokens == model_runner.DEFAULT_MAX_TOKENS
        return {
            "model": model,
            "id": "test-response",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "content": json.dumps(
                {
                    "summary": "High CPA by selected goal needs manual review.",
                    "findings": list(case.expected.should_find),
                    "recommendations": list(case.expected.should_recommend),
                    "risks": ["Budget changes require approval."],
                    "risk_level": case.expected.risk_level,
                    "requires_human_approval": case.expected.requires_human_approval,
                },
                ensure_ascii=False,
            ),
        }

    monkeypatch.setattr(model_runner, "generate_openrouter_response", fake_generate)

    paths = asyncio.run(
        model_runner.run_model_eval(
            model="openrouter/auto",
            case_id=case.id,
            output_dir=tmp_path,
        )
    )

    assert len(paths) == 1
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["case_id"] == case.id
    assert payload["provider"] == "openrouter"
    assert payload["system_prompt_version"] == "v1"
    assert payload["system_prompt_hash"]
    assert payload["request_debug"]["system_prompt_hash"] == payload["system_prompt_hash"]
    assert payload["response"]["requires_human_approval"] is True
    assert payload["raw_response"]

    score = score_eval_case(case, payload)
    assert score.passed is True


def test_saved_model_output_can_be_scored_by_offline_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    case = load_eval_cases()[0]

    async def fake_generate(*args, **kwargs):
        return {
            "model": "openrouter/auto",
            "content": json.dumps(
                {
                    "summary": "High CPA by selected goal with enough data.",
                    "findings": list(case.expected.should_find),
                    "recommendations": list(case.expected.should_recommend),
                    "risks": ["Manual approval required."],
                    "risk_level": "high",
                    "requires_human_approval": True,
                },
                ensure_ascii=False,
            ),
        }

    monkeypatch.setattr(model_runner, "generate_openrouter_response", fake_generate)
    asyncio.run(model_runner.run_model_eval(model="openrouter/auto", case_id=case.id, output_dir=tmp_path))

    report = run_offline_eval(outputs_dir=tmp_path)

    assert report.total_cases >= 5
    assert any(score.case_id == case.id and score.passed for score in report.case_scores)
