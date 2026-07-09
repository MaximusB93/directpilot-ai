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
    assert response.requestTrace["provider"] == "openrouter"
    assert response.requestTrace["system_prompt_version"] == "v1"
    assert len(response.requestTrace["system_prompt_hash"]) == 12
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


def test_ai_chat_keeps_raw_user_message_and_compact_prompt(monkeypatch):
    monkeypatch.setattr(ai_chat_module, "settings", _test_settings())
    raw_message = "Проведи аудит Яндекс.Директа по чеклисту"
    captured = {}

    async def fake_generate(*args, **kwargs):
        captured.update(kwargs)
        return {"model": kwargs["model"], "content": "ok"}

    monkeypatch.setattr(ai_chat_module, "generate_openrouter_response", fake_generate)

    response = asyncio.run(
        ai_chat_module.answer_ai_chat(
            client_id="client-1",
            message=raw_message,
            model="google/gemma-3-12b-it",
            history=[],
            client_context={
                "client": {"id": "client-1", "name": "Green Flow", "directLogin": "hotelgreenflow25"},
                "summary": {
                    "selectedGoalIds": ["35371875", "344527023"],
                    "searchQueryInsights": {"insights": [{"query": "green flow", "cost": 100, "goalConversions": 0}]},
                    "yandexDirectAudit": {"score": 67.9, "grade": "C", "criticalIssues": [], "quickWins": []},
                    "totals": {"cost": 1000, "clicks": 10, "impressions": 100, "goalCpa": 100},
                },
                "search_query_insights": {"insights": [{"query": "duplicate", "cost": 1}]},
                "yandex_direct_audit": {"score": 1},
                "latest_sync_job": {"id": "sync-secret-id", "rows_loaded": 10},
                "yandex_binding": {"account": {"id": "account-secret-uuid"}},
                "direct_analyst_playbook": "full playbook must not be copied",
            },
            max_tokens=777,
        )
    )

    assert response.requestTrace["userMessage"] == raw_message
    assert "Trusted server-side client context follows" not in response.requestTrace["userMessage"]
    assert "DirectPilot analyst playbook" not in response.requestTrace["userMessage"]
    assert '"client"' not in response.requestTrace["userMessage"]
    assert response.requestTrace["analysisPlan"]["intent"] == "global_direct_audit"
    assert response.requestTrace["analysisPlan"]["requiresCascade"] is True

    prompt = captured["prompt"]
    assert "Raw user task:" in prompt
    assert raw_message in prompt
    assert "Trusted server-side client context follows" not in prompt
    assert "search_query_insights" not in prompt
    assert "yandex_direct_audit" not in prompt
    assert "sync-secret-id" not in prompt
    assert "account-secret-uuid" not in prompt
    assert "full playbook must not be copied" not in prompt
    assert "Выполни каскадный анализ" in prompt


def test_search_query_intent_and_brand_classification():
    plan = ai_chat_module.detect_analysis_intent("Проанализируй поисковые запросы за май")
    assert plan["intent"] == "search_queries_analysis"
    assert plan["requestedPeriod"] == "may"

    context = {"client": {"name": "Green Flow"}, "business_context": {"brandName": "Green Flow"}}
    brand = ai_chat_module.classify_search_query("green flow официальный сайт", context)
    assert brand["brandLike"] is True
    assert brand["safeNegativeKeyword"] is False

    compact = ai_chat_module.build_compact_ai_chat_context(
        {
            **context,
            "summary": {
                "searchQueryInsights": {
                    "insights": [
                        {"query": "гринфлоу отзывы", "cost": 500, "goalConversions": 0},
                        {"query": "купить диван", "cost": 700, "goalConversions": 2},
                        {"query": "нерелевантный запрос", "cost": 900, "goalConversions": 0},
                    ]
                }
            },
        },
        plan,
        {"search_query_limit": 20},
    )
    assert compact["searchQueries"]["brandLikeQueries"][0]["classification"] == "brand_or_tracking_review"
    assert compact["searchQueries"]["queriesWithGoalConversions"][0]["safeNegativeKeyword"] is False
    assert compact["searchQueries"]["nonBrandWasteQueries"][0]["query"] == "нерелевантный запрос"


def test_memory_notes_are_reference_only_and_truncated(monkeypatch):
    monkeypatch.setattr(ai_chat_module, "settings", _test_settings())
    long_memory = "previous AI audit " + ("x" * 900) + " unique-tail-should-not-appear"
    captured = {}

    async def fake_generate(*args, **kwargs):
        captured.update(kwargs)
        return {"model": kwargs["model"], "content": "ok"}

    monkeypatch.setattr(ai_chat_module, "generate_openrouter_response", fake_generate)

    response = asyncio.run(
        ai_chat_module.answer_ai_chat(
            client_id="client-1",
            message="Что делать дальше?",
            model="google/gemma-3-12b-it",
            history=[],
            client_context={
                "client": {"id": "client-1", "name": "Green Flow"},
                "business_context": {"fields": {"memoryNotes": long_memory}},
                "summary": {"totals": {"cost": 10}},
            },
            max_tokens=777,
        )
    )

    prompt = captured["prompt"]
    assert "previous AI audit" in prompt
    assert "unique-tail-should-not-appear" not in prompt
    assert response.requestTrace["compactPromptContext"]["limitations"]
    assert response.requestTrace["compactPromptContext"]["omittedSections"]
    assert response.requestTrace["analysisPlan"]["intent"] == "general_question"
