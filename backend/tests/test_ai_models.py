from app.api.routers.ai import _ai_status_payload
from app.core.config import normalize_ai_request_options


def test_ai_status_exposes_presets_and_safe_default() -> None:
    payload = _ai_status_payload()

    assert payload["recommended_default_preset"] == "economy"
    assert payload["recommended_default_model"]
    assert payload["recommended_default_model"] != "anthropic/claude-3.5-sonnet"
    preset_ids = {item["id"] for item in payload["presets"]}
    assert {"economy", "balanced", "advanced"}.issubset(preset_ids)
    advanced = next(item for item in payload["presets"] if item["id"] == "advanced")
    assert advanced["warning"] == "Может быть дороже"


def test_missing_model_uses_recommended_default() -> None:
    options = normalize_ai_request_options(
        model=None,
        ai_preset=None,
        max_tokens=None,
        models=["openrouter/auto", "openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"],
        configured_default="anthropic/claude-3.5-sonnet",
    )

    assert options["ai_preset"] == "economy"
    assert options["model"] == "openai/gpt-4o-mini"
    assert options["max_tokens"] <= 1200


def test_max_tokens_are_capped_by_preset() -> None:
    economy = normalize_ai_request_options(
        model="openai/gpt-4o-mini",
        ai_preset="economy",
        max_tokens=5000,
        models=["openai/gpt-4o-mini"],
        configured_default="openai/gpt-4o-mini",
    )
    balanced = normalize_ai_request_options(
        model="openai/gpt-4o-mini",
        ai_preset="balanced",
        max_tokens=5000,
        models=["openai/gpt-4o-mini"],
        configured_default="openai/gpt-4o-mini",
    )
    advanced = normalize_ai_request_options(
        model="openai/gpt-4o-mini",
        ai_preset="advanced",
        max_tokens=9000,
        models=["openai/gpt-4o-mini"],
        configured_default="openai/gpt-4o-mini",
    )

    assert economy["max_tokens"] == 1200
    assert balanced["max_tokens"] == 2500
    assert advanced["max_tokens"] == 5000
