from app.services.ai_prompt_debug import (
    build_context_size_breakdown,
    build_prompt_debug_snapshot,
    estimate_tokens,
    summarize_prompt_size,
)


def test_estimate_tokens_is_conservative_and_non_zero():
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcdef") == 2
    assert estimate_tokens("a" * 300) == 100


def test_gemma_context_limit_and_oversized_detection():
    summary = summarize_prompt_size(
        system_prompt="system",
        user_prompt="x" * 705000,
        model="google/gemma-3-12b-it",
        max_tokens=900,
    )

    assert summary["contextLimit"] == 131072
    assert summary["estimatedTotalTokens"] > summary["contextLimit"]
    assert summary["isTooLarge"] is True


def test_section_breakdown_sorts_largest_first_and_redacts_secrets():
    breakdown = build_context_size_breakdown(
        {
            "client": {"id": "1", "name": "Client"},
            "summary": {"searchQueryInsights": {"items": ["query"] * 1000}},
            "knowledge_snippets": [{"content": "short"}],
            "api_token": "secret-value",
        }
    )

    assert breakdown[0]["estimatedTokens"] >= breakdown[-1]["estimatedTokens"]
    snapshot = build_prompt_debug_snapshot(
        context={"client": {"api_token": "secret-value"}},
        system_prompt="safe system",
        user_prompt='{"api_token": "secret-value"}',
        model="custom/model",
        max_tokens=900,
        include_preview=True,
    )
    assert "secret-value" not in str(snapshot["sections"])
    assert "secret-value" not in str(snapshot["preview"])


def test_chat_debug_breakdown_uses_named_sections_instead_of_other():
    snapshot = build_prompt_debug_snapshot(
        context={
            "chat.message": "Проверь аккаунт",
            "chat.history": [],
            "chat.playbook": "short",
            "chat.serverContext": {},
            "chat.toolResults": [],
            "chat.finalPromptWrapper": {"rules": ["safe"]},
            "serverContext.summary.searchQueryInsights": {"items": ["query"] * 2000},
            "serverContext.campaigns": [{"name": "campaign"}],
        },
        system_prompt="system",
        user_prompt="prompt",
        model="google/gemma-3-12b-it",
        max_tokens=900,
    )

    names = [item["name"] for item in snapshot["sections"]]
    assert "serverContext.summary.searchQueryInsights" in names
    assert "chat.message" in names
    assert snapshot["sections"][0]["name"] == "serverContext.summary.searchQueryInsights"
    assert snapshot["sections"][0]["name"] != "other"
    assert any("Поисковые запросы" in hint["message"] for hint in snapshot["reductionHints"])


def test_chat_debug_campaign_and_history_reduction_hints():
    campaigns_snapshot = build_prompt_debug_snapshot(
        context={
            "serverContext.campaigns": [{"name": "campaign", "notes": "x" * 12000}],
            "chat.history": [],
        },
        system_prompt="system",
        user_prompt="prompt",
        model="google/gemma-3-12b-it",
        max_tokens=900,
    )
    history_snapshot = build_prompt_debug_snapshot(
        context={
            "chat.history": [{"role": "user", "content": "x" * 12000}],
            "serverContext.campaigns": [],
        },
        system_prompt="system",
        user_prompt="prompt",
        model="google/gemma-3-12b-it",
        max_tokens=900,
    )

    assert any("конкретную кампанию" in hint["message"] for hint in campaigns_snapshot["reductionHints"])
    assert any("История чата" in hint["message"] for hint in history_snapshot["reductionHints"])
