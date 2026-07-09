from __future__ import annotations

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
