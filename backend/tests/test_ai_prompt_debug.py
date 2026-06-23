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
