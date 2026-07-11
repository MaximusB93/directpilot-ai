import asyncio
from dataclasses import replace

import httpx
import pytest
from fastapi import HTTPException

import app.services.ai_chat as ai_chat_module
import app.services.openrouter as openrouter_module
from app.core.config import AI_MODEL_PRESETS, settings as base_settings


def _configured_settings():
    return replace(base_settings, openrouter_api_key="test-key", openrouter_allow_custom_models=True)


def test_openrouter_timeout_is_normalized(monkeypatch):
    monkeypatch.setattr(openrouter_module, "settings", _configured_settings())
    captured = {}

    class AsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            request = httpx.Request("POST", url)
            raise httpx.ReadTimeout("provider took too long", request=request)

    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", AsyncClient)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            openrouter_module.generate_openrouter_response(
                model="custom/model",
                prompt="short prompt",
                max_tokens=900,
            )
        )

    assert error.value.status_code == 504
    assert error.value.detail["error_code"] == "openrouter_timeout"
    assert error.value.detail["retryable"] is True
    assert error.value.detail["suggested_model"] == "mistralai/mistral-small-3.2-24b-instruct"
    assert captured["timeout"].read == 55.0


def test_ai_chat_normalizes_openrouter_timeout_and_records_timings(monkeypatch):
    monkeypatch.setattr(ai_chat_module, "settings", _configured_settings())

    async def fake_generate(*args, **kwargs):
        raise HTTPException(
            status_code=504,
            detail={"error_code": "openrouter_timeout", "retryable": True},
        )

    monkeypatch.setattr(ai_chat_module, "generate_openrouter_response", fake_generate)

    response = asyncio.run(
        ai_chat_module.answer_ai_chat(
            client_id="client-1",
            message="Проверь CPA кампаний",
            model="custom/model",
            history=[],
            client_context={"client": {"id": "client-1"}},
            max_tokens=900,
            initial_timings={"contextBuildMs": 12, "specificDateFetchMs": 3},
        )
    )

    assert response.error is True
    assert response.error_code == "openrouter_timeout"
    assert response.retryable is True
    assert response.suggested_preset == "economy"
    assert "Mistral Small 3.2" in response.message
    assert response.requestTrace["timings"]["contextBuildMs"] >= 12
    assert response.requestTrace["timings"]["specificDateFetchMs"] == 3
    assert response.requestTrace["timings"]["totalMs"] >= 0
    assert "test-key" not in str(response.requestTrace)


def test_model_meta_question_skips_campaign_and_audit_tools():
    assert ai_chat_module._select_mcp_tools("Какая ты модель?") == []

    campaign_tools = {name for name, _ in ai_chat_module._select_mcp_tools("Проанализируй CPA кампаний")}
    assert "list_campaigns" in campaign_tools
    assert "list_audit_issues" in campaign_tools


def test_backend_ai_preset_token_budgets_are_stable():
    assert AI_MODEL_PRESETS["economy"]["max_tokens"] == 1200
    assert AI_MODEL_PRESETS["balanced"]["max_tokens"] == 2500
    assert AI_MODEL_PRESETS["advanced"]["max_tokens"] == 5000
