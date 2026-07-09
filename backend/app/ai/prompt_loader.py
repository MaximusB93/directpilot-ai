from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path


SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt.md"
SYSTEM_PROMPT_SOURCE = "backend/app/ai/prompts/system_prompt.md"
SYSTEM_PROMPT_VERSION = "v1"


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


def get_system_prompt_version() -> str:
    return SYSTEM_PROMPT_VERSION


def get_system_prompt_hash() -> str:
    return hashlib.sha256(get_system_prompt().encode("utf-8")).hexdigest()


def get_system_prompt_metadata() -> dict[str, str]:
    return {
        "version": get_system_prompt_version(),
        "hash": get_system_prompt_hash(),
        "source": SYSTEM_PROMPT_SOURCE,
    }
