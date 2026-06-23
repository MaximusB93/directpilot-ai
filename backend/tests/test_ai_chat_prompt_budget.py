import asyncio
from dataclasses import replace

import app.services.ai_chat as ai_chat_module
from app.core.config import settings as base_settings


def _test_settings():
    return replace(base_settings, openrouter_api_key="test-key", openrouter_allow_custom_models=True)


def test_chat_oversized_prompt_guard_returns_error_without_openrouter_call(monkeypatch):
    monkeypatch.setattr(ai_chat_module, "settings", _test_settings())
    called = False

    async def fake_generate(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("OpenRouter should not be called for oversized chat prompts")

    monkeypatch.setattr(ai_chat_module, "generate_openrouter_response", fake_generate)

    response = asyncio.run(
        ai_chat_module.answer_ai_chat(
            client_id="client-1",
            message="x" * 430000,
            model="google/gemma-3-12b-it",
            history=[],
            client_context={"client": {"id": "client-1"}},
            max_tokens=900,
        )
    )

    assert called is False
    assert response.error is True
    assert response.error_code == "ai_prompt_too_large"
    assert response.source == "prompt_budget_guard"
    assert response.requestTrace is not None
    assert response.requestTrace["guard"]["blocked"] is True
    assert response.requestTrace["guard"]["reason"] == "ai_prompt_too_large"


def test_answer_ai_chat_passes_max_tokens_to_openrouter(monkeypatch):
    monkeypatch.setattr(ai_chat_module, "settings", _test_settings())
    captured = {}

    async def fake_generate(*args, **kwargs):
        captured.update(kwargs)
        return {"model": kwargs["model"], "content": "ok"}

    monkeypatch.setattr(ai_chat_module, "generate_openrouter_response", fake_generate)

    response = asyncio.run(
        ai_chat_module.answer_ai_chat(
            client_id="client-1",
            message="short question",
            model="google/gemma-3-12b-it",
            history=[],
            client_context={"client": {"id": "client-1"}},
            max_tokens=777,
        )
    )

    assert response.answer == "ok"
    assert captured["max_tokens"] == 777
    assert captured["model"] == "google/gemma-3-12b-it"
    assert response.requestDebug is None
    assert response.requestTrace is not None
    assert response.requestTrace["mode"] == "ai_chat"
    assert response.requestTrace["openrouterPayload"]["max_tokens"] == 777


def test_answer_ai_chat_includes_request_debug_when_inspected(monkeypatch):
    monkeypatch.setattr(ai_chat_module, "settings", _test_settings())

    async def fake_generate(*args, **kwargs):
        return {"model": kwargs["model"], "content": "ok"}

    monkeypatch.setattr(ai_chat_module, "generate_openrouter_response", fake_generate)

    response = asyncio.run(
        ai_chat_module.answer_ai_chat(
            client_id="client-1",
            message="short question",
            model="google/gemma-3-12b-it",
            history=[],
            client_context={"client": {"id": "client-1"}},
            max_tokens=777,
            inspect_request=True,
        )
    )

    assert response.requestDebug is not None
    assert response.requestDebug["payload"]["messages"][1]["role"] == "user"
    assert response.requestTrace is not None
    assert response.requestTrace["prompt"]["messages"][1]["role"] == "user"


def test_chat_prompt_debug_snapshot_uses_chat_mode_and_requested_max_tokens():
    snapshot = ai_chat_module.build_chat_prompt_debug_snapshot(
        client_id="client-1",
        message="short question",
        model="google/gemma-3-12b-it",
        history=[],
        client_context={"client": {"id": "client-1"}},
        max_tokens=777,
        include_preview=False,
    )

    assert snapshot["mode"] == "chat"
    assert snapshot["requestTracePreview"]["mode"] == "ai_chat"
    assert snapshot["requestTracePreview"]["openrouterPayload"]["max_tokens"] == 777
    assert snapshot["size"]["model"] == "google/gemma-3-12b-it"
    assert snapshot["size"]["maxTokens"] == 777
    assert snapshot["size"]["isTooLarge"] is False
    section_names = {item["name"] for item in snapshot["sections"]}
    assert "chat.message" in section_names
    assert "chat.serverContext" in section_names
    assert "chat.toolResults" in section_names
    assert snapshot["reductionHints"]


def test_chat_prompt_debug_summary_tool_results_are_smaller_than_full():
    context = {
        "client": {"id": "client-1"},
        "summary": {"searchQueryInsights": {"insights": [{"query": "x" * 1000} for _ in range(100)]}},
        "campaigns": [{"name": f"campaign-{index}", "notes": "x" * 1000} for index in range(40)],
    }
    full_snapshot = ai_chat_module.build_chat_prompt_debug_snapshot(
        client_id="client-1",
        message="direct campaign analysis",
        model="google/gemma-3-12b-it",
        history=[],
        client_context=context,
        max_tokens=900,
        tool_results_mode="full",
        compact_context=False,
        search_query_limit=None,
    )
    compact_snapshot = ai_chat_module.build_chat_prompt_debug_snapshot(
        client_id="client-1",
        message="direct campaign analysis",
        model="google/gemma-3-12b-it",
        history=[],
        client_context=context,
        max_tokens=900,
        tool_results_mode="summary",
        compact_context=True,
        search_query_limit=20,
    )

    full_tool_tokens = next(item["estimatedTokens"] for item in full_snapshot["sections"] if item["name"] == "chat.toolResults")
    compact_tool_tokens = next(item["estimatedTokens"] for item in compact_snapshot["sections"] if item["name"] == "chat.toolResults")
    assert compact_tool_tokens < full_tool_tokens
    assert compact_snapshot["size"]["estimatedTotalTokens"] < full_snapshot["size"]["estimatedTotalTokens"]


def test_ai_chat_request_trace_redacts_secret_like_values(monkeypatch):
    monkeypatch.setattr(ai_chat_module, "settings", _test_settings())

    async def fake_generate(*args, **kwargs):
        return {"model": kwargs["model"], "content": "ok"}

    monkeypatch.setattr(ai_chat_module, "generate_openrouter_response", fake_generate)

    response = asyncio.run(
        ai_chat_module.answer_ai_chat(
            client_id="client-1",
            message='check this {"api_key":"super-secret"}',
            model="google/gemma-3-12b-it",
            history=[],
            client_context={"client": {"id": "client-1"}, "token": "secret-token"},
            max_tokens=777,
        )
    )

    trace_text = str(response.requestTrace)
    assert "super-secret" not in trace_text
    assert "secret-token" not in trace_text
    assert "[redacted]" in trace_text
