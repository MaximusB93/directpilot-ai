from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.ai import prompt_loader
from app.services import openrouter


def test_system_prompt_file_exists_and_loader_reads_it() -> None:
    prompt_path = Path(prompt_loader.SYSTEM_PROMPT_PATH)

    assert prompt_path.is_file()
    assert prompt_loader.get_system_prompt() == prompt_path.read_text(encoding="utf-8").strip()


def test_system_prompt_contains_core_role_and_safety_rules() -> None:
    prompt = prompt_loader.get_system_prompt()

    assert prompt
    assert "Ты являешься AI Performance Analyst для Яндекс.Директа." in prompt
    assert "Никогда не придумывай отсутствующие" in prompt
    assert "Массовые изменения запрещены без отдельного явного подтверждения." in prompt
    assert "Работай только в режиме dry-run." in prompt


def test_system_prompt_version_hash_and_metadata() -> None:
    prompt = prompt_loader.get_system_prompt()
    expected_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    assert prompt_loader.get_system_prompt_version() == "v1"
    assert prompt_loader.get_system_prompt_hash() == expected_hash
    assert prompt_loader.get_system_prompt_hash() == expected_hash
    assert prompt_loader.get_system_prompt_metadata() == {
        "version": "v1",
        "hash": expected_hash,
        "source": "backend/app/ai/prompts/system_prompt.md",
    }


def test_system_prompt_hash_changes_with_prompt_content(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_path = tmp_path / "system_prompt.md"
    prompt_path.write_text("prompt version one", encoding="utf-8")
    monkeypatch.setattr(prompt_loader, "SYSTEM_PROMPT_PATH", prompt_path)
    prompt_loader.get_system_prompt.cache_clear()

    try:
        first_hash = prompt_loader.get_system_prompt_hash()
        prompt_path.write_text("prompt version two", encoding="utf-8")
        prompt_loader.get_system_prompt.cache_clear()
        second_hash = prompt_loader.get_system_prompt_hash()
        assert first_hash != second_hash
    finally:
        prompt_loader.get_system_prompt.cache_clear()


def test_missing_system_prompt_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_loader.get_system_prompt.cache_clear()
    monkeypatch.setattr(prompt_loader, "SYSTEM_PROMPT_PATH", tmp_path / "missing-system-prompt.md")

    try:
        with pytest.raises(RuntimeError, match="system prompt is unavailable"):
            prompt_loader.get_system_prompt()
    finally:
        prompt_loader.get_system_prompt.cache_clear()


def test_openrouter_payload_uses_canonical_system_prompt() -> None:
    payload = openrouter.build_openrouter_payload("openrouter/auto", "Проверь кампании.", max_tokens=900)
    system_message = payload["messages"][0]

    assert system_message == {"role": "system", "content": prompt_loader.get_system_prompt()}
    assert openrouter.DEFAULT_SYSTEM_PROMPT == prompt_loader.get_system_prompt()
    assert "Ты senior PPC-стратег DirectPilot AI." not in system_message["content"]


def test_openrouter_trace_metadata_uses_system_prompt_version_and_short_hash() -> None:
    metadata = openrouter.build_openrouter_trace_metadata("openrouter/auto", task="ai_recommendations")

    assert metadata["provider"] == "openrouter"
    assert metadata["model"] == "openrouter/auto"
    assert metadata["task"] == "ai_recommendations"
    assert metadata["system_prompt_version"] == "v1"
    assert metadata["system_prompt_hash"] == prompt_loader.get_system_prompt_hash()[:12]
    assert metadata["system_prompt_source"] == "backend/app/ai/prompts/system_prompt.md"
