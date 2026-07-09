from __future__ import annotations

import json
import math
import re
from typing import Any

MODEL_CONTEXT_LIMITS = {
    "google/gemma-3-12b-it": 131072,
    "qwen/qwen3-14b": 132000,
}
DEFAULT_CONTEXT_LIMIT = 128000
SECRET_KEY_PARTS = ("token", "secret", "api_key", "apikey", "authorization", "password", "refresh")


def estimate_tokens(text: str) -> int:
    """Approximate token count. Conservative on purpose; no external tokenizer dependency."""

    return max(1, math.ceil(len(text or "") / 3))


def context_limit_for_model(model: str | None) -> int:
    return MODEL_CONTEXT_LIMITS.get((model or "").strip(), DEFAULT_CONTEXT_LIMIT)


def clamp_openrouter_max_tokens(max_tokens: int | None) -> int:
    if max_tokens is None:
        return 900
    return max(256, min(int(max_tokens), 8000))


def summarize_prompt_size(system_prompt: str, user_prompt: str, model: str, max_tokens: int) -> dict[str, Any]:
    safe_max_tokens = clamp_openrouter_max_tokens(max_tokens)
    input_tokens = estimate_tokens(f"{system_prompt or ''}\n{user_prompt or ''}")
    total_tokens = input_tokens + safe_max_tokens
    context_limit = context_limit_for_model(model)
    is_too_large = total_tokens > context_limit
    return {
        "model": model,
        "maxTokens": safe_max_tokens,
        "systemChars": len(system_prompt or ""),
        "userPromptChars": len(user_prompt or ""),
        "estimatedInputTokens": input_tokens,
        "estimatedTotalTokens": total_tokens,
        "contextLimit": context_limit,
        "isTooLarge": is_too_large,
        "warning": (
            "Контекст слишком большой для выбранной модели. Сократите период, выберите конкретную кампанию или ограничьте поисковые запросы."
            if is_too_large
            else ""
        ),
    }


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in SECRET_KEY_PARTS):
                safe[str(key)] = "[redacted]"
            else:
                safe[str(key)] = _redact_secrets(item)
        return safe
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _json_size(value: Any) -> tuple[int, int]:
    text = json.dumps(_redact_secrets(value), ensure_ascii=False, default=str)
    return len(text), estimate_tokens(text)


def _section_items(context: dict[str, Any]) -> list[tuple[str, Any]]:
    if any(str(key).startswith(("chat.", "serverContext.")) for key in (context or {})):
        ordered_names = [
            "chat.message",
            "chat.history",
            "chat.playbook",
            "chat.serverContext",
            "chat.toolResults",
            "chat.finalPromptWrapper",
            "serverContext.client",
            "serverContext.business_context",
            "serverContext.summary",
            "serverContext.summary.yesterdayCampaignSummary",
            "serverContext.summary.searchQueryInsights",
            "serverContext.campaigns",
            "serverContext.diagnostics",
            "serverContext.optimization",
            "serverContext.knowledge_snippets",
            "serverContext.warnings",
            "serverContext.other",
        ]
        known = set(ordered_names)
        items = [(name, context.get(name)) for name in ordered_names]
        other = {key: value for key, value in context.items() if key not in known}
        if other:
            items.append(("other", other))
        return items

    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    known = {
        "client",
        "business_context",
        "summary",
        "campaigns",
        "diagnostics",
        "optimization_plan",
        "knowledge_snippets",
        "ai_model_settings",
        "warnings",
    }
    items: list[tuple[str, Any]] = [
        ("client", context.get("client")),
        ("business_context", context.get("business_context")),
        ("summary", summary),
        ("summary.yesterdayCampaignSummary", summary.get("yesterdayCampaignSummary") or context.get("yesterday_campaign_summary")),
        ("summary.searchQueryInsights", summary.get("searchQueryInsights") or context.get("search_query_insights")),
        ("campaigns", context.get("campaigns")),
        ("diagnostics", context.get("diagnostics")),
        ("optimization", context.get("optimization_plan") or context.get("saved_optimization_actions")),
        ("knowledge_snippets", context.get("knowledge_snippets")),
        ("ai_model_settings", context.get("ai_model_settings")),
        ("warnings", context.get("warnings")),
    ]
    other = {key: value for key, value in context.items() if key not in known}
    items.append(("other", other))
    return items


def build_context_size_breakdown(context: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for name, value in _section_items(context or {}):
        chars, tokens = _json_size(value)
        sections.append({"name": name, "chars": chars, "estimatedTokens": tokens})
    return sorted(sections, key=lambda item: item["estimatedTokens"], reverse=True)


def build_reduction_hints(sections: list[dict[str, Any]]) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    largest_name = str((sections[0] if sections else {}).get("name") or "")
    lowered = largest_name.lower()

    if "toolresults" in lowered or "tool_results" in lowered:
        hints.append(
            {
                "section": largest_name,
                "message": "Результаты MCP-инструментов занимают больше всего места. Включите summary-режим MCP, чтобы не отправлять полный JSON в AI.",
                "action": "enable_tool_summary",
            }
        )
    if "searchqueryinsights" in lowered or "search_query" in lowered:
        hints.append(
            {
                "section": largest_name,
                "message": "Поисковые запросы раздувают контекст. Ограничьте их до top 20 или выберите конкретную кампанию.",
                "action": "limit_search_queries",
            }
        )
    if "campaigns" in lowered or "servercontext.campaigns" in lowered:
        hints.append(
            {
                "section": largest_name,
                "message": "Список кампаний занимает больше всего места. Выберите конкретную кампанию вместо всего аккаунта.",
                "action": "select_campaign",
            }
        )
    if "history" in lowered:
        hints.append(
            {
                "section": largest_name,
                "message": "История чата занимает больше всего места. Очистите историю чата перед повторным запросом.",
                "action": "clear_chat_history",
            }
        )
    if "optimization" in lowered:
        hints.append(
            {
                "section": largest_name,
                "message": "Черновики оптимизации занимают больше всего места. Ограничьте список черновиков или откройте конкретное действие.",
                "action": "limit_optimization",
            }
        )

    generic_hints = [
        {
            "section": "serverContext.campaigns",
            "message": "Выберите конкретную кампанию вместо всего аккаунта.",
            "action": "select_campaign",
        },
        {
            "section": "chat.history",
            "message": "Очистите историю чата перед повторным запросом.",
            "action": "clear_chat_history",
        },
        {
            "section": "chat.serverContext",
            "message": "Используйте сжатый контекст.",
            "action": "enable_compact_context",
        },
    ]
    for hint in generic_hints:
        if not any(item.get("message") == hint["message"] for item in hints):
            hints.append(hint)
    return hints


def _preview(text: str, limit: int) -> str:
    return _redact_text(text or "")[:limit]


def _preview_end(text: str, limit: int) -> str:
    return _redact_text(text or "")[-limit:] if text else ""


def _redact_text(text: str) -> str:
    redacted = text
    for key in SECRET_KEY_PARTS:
        redacted = re.sub(
            rf'("[^"]*{re.escape(key)}[^"]*"\s*:\s*)"[^"]*"',
            r'\1"[redacted]"',
            redacted,
            flags=re.IGNORECASE,
        )
    return redacted


def build_prompt_debug_snapshot(
    context: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    include_preview: bool = False,
) -> dict[str, Any]:
    sections = build_context_size_breakdown(context)
    snapshot = {
        "size": summarize_prompt_size(system_prompt, user_prompt, model, max_tokens),
        "sections": sections,
        "reductionHints": build_reduction_hints(sections),
        "preview": None,
    }
    if include_preview:
        snapshot["preview"] = {
            "systemPromptStart": _preview(system_prompt, 2000),
            "userPromptStart": _preview(user_prompt, 6000),
            "userPromptEnd": _preview_end(user_prompt, 6000),
        }
    return snapshot


def build_openrouter_request_debug(
    *,
    mode: str,
    endpoint: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    context: dict[str, Any] | None = None,
    compact_options: dict[str, Any] | None = None,
    include_preview: bool = True,
) -> dict[str, Any]:
    from app.services.openrouter import (
        build_openrouter_payload,
        build_openrouter_trace_metadata,
        redact_openrouter_debug_payload,
    )

    snapshot = build_prompt_debug_snapshot(
        context=context or {},
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        max_tokens=max_tokens,
        include_preview=include_preview,
    )
    payload = build_openrouter_payload(model, user_prompt, max_tokens=max_tokens)
    safe_payload = redact_openrouter_debug_payload(payload)
    trace_metadata = build_openrouter_trace_metadata(str(payload["model"]), task=mode)
    return {
        "mode": mode,
        "endpoint": endpoint,
        "source": endpoint,
        **trace_metadata,
        "systemPromptMetadata": {
            "version": trace_metadata["system_prompt_version"],
            "hash": trace_metadata["system_prompt_hash"],
            "source": trace_metadata["system_prompt_source"],
        },
        "payload": safe_payload,
        "systemPrompt": redact_openrouter_debug_payload(system_prompt),
        "userPrompt": redact_openrouter_debug_payload(user_prompt),
        "messages": safe_payload.get("messages", []),
        "size": snapshot["size"],
        "sections": snapshot["sections"],
        "reductionHints": snapshot["reductionHints"],
        "compactOptions": compact_options or {},
    }
