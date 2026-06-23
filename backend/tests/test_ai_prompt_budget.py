import asyncio
from dataclasses import replace

import app.services.ai_recommendations as ai_recommendations_module
import app.services.openrouter as openrouter_module
from app.core.config import settings as base_settings


def test_oversized_prompt_guard_returns_error_without_openrouter_call(monkeypatch):
    test_settings = replace(base_settings, openrouter_api_key="test-key", openrouter_allow_custom_models=True)
    monkeypatch.setattr(ai_recommendations_module, "settings", test_settings)
    called = False

    async def fake_generate(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("OpenRouter should not be called for oversized prompts")

    monkeypatch.setattr(ai_recommendations_module, "generate_openrouter_response", fake_generate)
    context = {
        "client": {"id": "client-1", "name": "Client"},
        "business_context": {"status": "good", "fields": {"manual_notes": "x" * 430000}},
        "campaigns": [{"campaign_name": "Campaign", "cost": 100, "goal_conversions": 0}],
    }

    response = asyncio.run(
        ai_recommendations_module.generate_client_recommendations_from_context(
            context=context,
            model="google/gemma-3-12b-it",
            ai_preset="economy",
            max_tokens=900,
        )
    )

    assert called is False
    assert response.error is True
    assert response.error_code == "ai_prompt_too_large"
    assert response.source == "prompt_budget_guard"
    assert response.recommendations[0].requires_approval is False


def test_generate_openrouter_response_clamps_max_tokens(monkeypatch):
    test_settings = replace(base_settings, openrouter_api_key="test-key", openrouter_allow_custom_models=True)
    monkeypatch.setattr(openrouter_module, "settings", test_settings)
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"model": "openrouter/auto", "choices": [{"message": {"content": "ok"}}]}

    class AsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            captured["payload"] = json
            captured["headers"] = headers
            return Response()

    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", AsyncClient)

    response = asyncio.run(
        openrouter_module.generate_openrouter_response(
            model="openrouter/auto",
            prompt="short prompt",
            max_tokens=999999,
        )
    )

    assert response["content"] == "ok"
    assert captured["payload"]["max_tokens"] == 8000
    assert captured["headers"]["Authorization"] == "Bearer test-key"
