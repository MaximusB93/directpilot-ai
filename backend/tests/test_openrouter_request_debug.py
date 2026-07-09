from dataclasses import replace

import app.services.openrouter as openrouter_module
from app.core.config import settings as base_settings
from app.services.ai_prompt_debug import build_openrouter_request_debug


def _test_settings():
    return replace(base_settings, openrouter_api_key="test-key", openrouter_allow_custom_models=True)


def test_openrouter_payload_builder_matches_chat_completions_shape(monkeypatch):
    monkeypatch.setattr(openrouter_module, "settings", _test_settings())

    payload = openrouter_module.build_openrouter_payload("custom/model", "hello", max_tokens=1234)

    assert payload["model"] == "custom/model"
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 1234
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1] == {"role": "user", "content": "hello"}


def test_openrouter_debug_redaction_removes_credentials():
    payload = {
        "Authorization": "Bearer secret",
        "api_key": "secret",
        "apikey": "secret",
        "secret": "secret",
        "password": "secret",
        "nested": {
            "access_token": "secret",
            "refresh_token": "secret",
            "oauth_token": "secret",
            "cookie": "secret",
            "safe": "visible",
        },
        "max_tokens": 777,
        "estimatedInputTokens": 120,
        "estimatedTotalTokens": 897,
        "contextLimit": 131072,
        "inputTokens": 120,
        "totalTokens": 897,
    }

    redacted = openrouter_module.redact_openrouter_debug_payload(payload)

    assert redacted["Authorization"] == "[redacted]"
    assert redacted["api_key"] == "[redacted]"
    assert redacted["apikey"] == "[redacted]"
    assert redacted["secret"] == "[redacted]"
    assert redacted["password"] == "[redacted]"
    assert redacted["nested"]["access_token"] == "[redacted]"
    assert redacted["nested"]["refresh_token"] == "[redacted]"
    assert redacted["nested"]["oauth_token"] == "[redacted]"
    assert redacted["nested"]["cookie"] == "[redacted]"
    assert redacted["nested"]["safe"] == "visible"
    assert redacted["max_tokens"] == 777
    assert redacted["estimatedInputTokens"] == 120
    assert redacted["estimatedTotalTokens"] == 897
    assert redacted["contextLimit"] == 131072
    assert redacted["inputTokens"] == 120
    assert redacted["totalTokens"] == 897


def test_openrouter_request_debug_includes_messages_without_credentials(monkeypatch):
    monkeypatch.setattr(openrouter_module, "settings", _test_settings())

    debug = build_openrouter_request_debug(
        mode="chat",
        endpoint="/api/v1/ai/chat",
        system_prompt="system",
        user_prompt='{"api_key": "secret", "question": "hello"}',
        model="custom/model",
        max_tokens=900,
        context={"client": {"id": "1"}},
        compact_options={"compact_context": True},
    )

    assert debug["payload"]["model"] == "custom/model"
    assert debug["payload"]["max_tokens"] == 900
    assert debug["payload"]["messages"][0]["role"] == "system"
    assert debug["payload"]["messages"][1]["role"] == "user"
    assert debug["provider"] == "openrouter"
    assert debug["model"] == "custom/model"
    assert debug["task"] == "chat"
    assert debug["system_prompt_version"] == "v1"
    assert len(debug["system_prompt_hash"]) == 12
    assert debug["systemPromptMetadata"]["hash"] == debug["system_prompt_hash"]
    assert "secret" not in str(debug)
    assert debug["compactOptions"]["compact_context"] is True
