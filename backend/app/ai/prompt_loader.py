from __future__ import annotations

from functools import lru_cache
from pathlib import Path


SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt.md"


@lru_cache(maxsize=1)
def get_system_prompt() -> str:
    """Load the versioned DirectPilot system policy from its canonical file."""

    try:
        prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError("DirectPilot AI system prompt is unavailable.") from exc

    if not prompt:
        raise RuntimeError("DirectPilot AI system prompt is empty.")
    return prompt
