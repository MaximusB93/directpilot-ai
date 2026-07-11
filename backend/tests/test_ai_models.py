from fastapi import HTTPException

from app.api.routers.ai import _ai_status_payload, _normalized_ai_error
from app.core.config import (
    DEFAULT_PRODUCTION_AI_MODEL,
    PRODUCTION_AI_MODELS,
    normalize_ai_request_options,
    production_ai_model_ids,
)


def test_production_model_registry_has_three_unique_models() -> None:
    model_ids = production_ai_model_ids()

    assert len(PRODUCTION_AI_MODELS) == 3
    assert len(model_ids) == 3
    assert len(set(model_ids)) == 3
    assert DEFAULT_PRODUCTION_AI_MODEL in model_ids


def test_ai_status_exposes_presets_and_safe_default() -> None:
    payload = _ai_status_payload()

    assert payload["recommended_default_preset"] == "balanced"
    assert payload["recommended_default_model"] == DEFAULT_PRODUCTION_AI_MODEL
    assert payload["default_model"] == DEFAULT_PRODUCTION_AI_MODEL
    assert [model["id"] for model in payload["models"]] == production_ai_model_ids()
    assert "openrouter/auto" not in {model["id"] for model in payload["models"]}
    assert payload["allow_custom_models"] is False
    preset_ids = {item["id"] for item in payload["presets"]}
    assert {"economy", "balanced", "advanced"}.issubset(preset_ids)
    preset_tokens = {item["id"]: item["max_tokens"] for item in payload["presets"]}
    assert preset_tokens == {"economy": 1200, "balanced": 2500, "advanced": 5000}
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

    assert options["ai_preset"] == "balanced"
    assert options["model"] == "openai/gpt-4o-mini"
    assert options["max_tokens"] <= 2500


def test_unknown_production_model_falls_back_to_qwen() -> None:
    options = normalize_ai_request_options(
        model="openrouter/auto",
        ai_preset="balanced",
        max_tokens=None,
        models=production_ai_model_ids(),
        configured_default=DEFAULT_PRODUCTION_AI_MODEL,
        production_only=True,
    )

    assert options["model"] == DEFAULT_PRODUCTION_AI_MODEL
    assert options["is_custom_model"] is False


def test_qwen_production_model_is_accepted() -> None:
    options = normalize_ai_request_options(
        model=DEFAULT_PRODUCTION_AI_MODEL,
        ai_preset="balanced",
        max_tokens=None,
        models=production_ai_model_ids(),
        configured_default=DEFAULT_PRODUCTION_AI_MODEL,
        production_only=True,
    )

    assert options["model"] == DEFAULT_PRODUCTION_AI_MODEL


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


def test_openrouter_429_error_is_normalized() -> None:
    exc = HTTPException(
        status_code=502,
        detail='OpenRouter вернул ошибку: {"error":{"message":"Provider returned error","code":429,"metadata":{"raw":"temporarily rate-limited upstream"}}}',
    )

    payload = _normalized_ai_error(exc, "deepseek/deepseek-v4-flash:free")

    assert payload is not None
    assert payload["error"] is True
    assert payload["error_code"] == "openrouter_rate_limited"
    assert payload["model"] == "deepseek/deepseek-v4-flash:free"
    assert payload["retryable"] is True
    assert payload["suggested_preset"] == "economy"
    assert "Provider returned error" not in payload["message"]
