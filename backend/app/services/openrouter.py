import re

import httpx
from fastapi import HTTPException, status
from typing import Any

from app.ai.prompt_loader import get_system_prompt, get_system_prompt_metadata
from app.core.config import DEFAULT_PRODUCTION_AI_MODEL, PRODUCTION_AI_MODELS, production_ai_model_ids, settings
from app.services.ai_prompt_debug import clamp_openrouter_max_tokens

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT = httpx.Timeout(connect=10.0, read=55.0, write=10.0, pool=10.0)
OPENROUTER_AUDIT_TIMEOUT = httpx.Timeout(connect=10.0, read=115.0, write=10.0, pool=10.0)

DEFAULT_SYSTEM_PROMPT = get_system_prompt()

SECRET_KEY_PARTS = ("authorization", "api_key", "apikey", "token", "secret", "password", "cookie", "refresh")
SAFE_DEBUG_KEYS = {
    "max_tokens",
    "estimatedinputtokens",
    "estimatedtotaltokens",
    "contextlimit",
    "inputtokens",
    "totaltokens",
}


def _validate_openrouter_model(model: str | None) -> str:
    allowed_models = set(settings.openrouter_models) | set(production_ai_model_ids())
    selected_model = (model or settings.openrouter_default_model).strip()
    if not selected_model or len(selected_model) > 200 or any(char.isspace() for char in selected_model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор модели OpenRouter.")
    if selected_model not in allowed_models and not settings.openrouter_allow_custom_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Модель {selected_model} не разрешена. Добавьте её в OPENROUTER_MODELS или включите OPENROUTER_ALLOW_CUSTOM_MODELS=true.",
        )
    return selected_model


def build_openrouter_payload(
    model: str,
    prompt: str,
    max_tokens: int | None = None,
    *,
    max_tokens_cap: int = 8000,
) -> dict[str, Any]:
    selected_model = _validate_openrouter_model(model)
    return {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": clamp_openrouter_max_tokens(max_tokens, cap=max_tokens_cap),
    }


def build_openrouter_trace_metadata(model: str, task: str | None = None) -> dict[str, str]:
    prompt_metadata = get_system_prompt_metadata()
    metadata = {
        "provider": "openrouter",
        "model": _validate_openrouter_model(model),
        "system_prompt_version": prompt_metadata["version"],
        "system_prompt_hash": prompt_metadata["hash"][:12],
        "system_prompt_source": prompt_metadata["source"],
    }
    if task:
        metadata["task"] = task
    return metadata


def redact_openrouter_debug_payload(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in SAFE_DEBUG_KEYS:
                safe[str(key)] = redact_openrouter_debug_payload(item)
                continue
            if any(part in key_text for part in SECRET_KEY_PARTS):
                safe[str(key)] = "[redacted]"
            else:
                safe[str(key)] = redact_openrouter_debug_payload(item)
        return safe
    if isinstance(value, list):
        return [redact_openrouter_debug_payload(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for key in SECRET_KEY_PARTS:
            redacted = re.sub(
                rf'("[^"]*{re.escape(key)}[^"]*"\s*:\s*)"[^"]*"',
                r'\1"[redacted]"',
                redacted,
                flags=re.IGNORECASE,
            )
        return redacted
    return value


def configured_models() -> list[dict[str, object]]:
    return [
        {
            "id": str(model["id"]),
            "name": str(model["name"]),
            "description": str(model["description"]),
            "tier": str(model["tier"]),
            "supports_structured_output": bool(model.get("supports_structured_output", False)),
        }
        for model in PRODUCTION_AI_MODELS
    ]


def openrouter_status() -> dict[str, object]:
    configured = settings.openrouter_configured
    return {
        "configured": configured,
        "default_model": DEFAULT_PRODUCTION_AI_MODEL,
        "models": configured_models(),
        "allow_custom_models": False,
        "message": (
            "OpenRouter подключён через backend. Ключ хранится только в переменных окружения сервера."
            if configured
            else "Добавьте OPENROUTER_API_KEY в окружение backend, чтобы включить генерацию ответов."
        ),
    }


async def generate_openrouter_response(
    model: str,
    prompt: str,
    max_tokens: int | None = None,
    *,
    max_tokens_cap: int = 8000,
    timeout: httpx.Timeout | None = None,
) -> dict[str, object]:
    if not settings.openrouter_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenRouter не настроен: добавьте OPENROUTER_API_KEY в окружение backend.",
        )

    allowed_models = set(settings.openrouter_models) | set(production_ai_model_ids())
    selected_model = (model or settings.openrouter_default_model).strip()
    if not selected_model or len(selected_model) > 200 or any(char.isspace() for char in selected_model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор модели OpenRouter.")
    if selected_model not in allowed_models and not settings.openrouter_allow_custom_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Модель {selected_model} не разрешена. Добавьте её в OPENROUTER_MODELS или включите OPENROUTER_ALLOW_CUSTOM_MODELS=true.",
        )

    payload = build_openrouter_payload(
        selected_model,
        prompt,
        max_tokens=max_tokens,
        max_tokens_cap=max_tokens_cap,
    )
    selected_model = str(payload["model"])
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout or OPENROUTER_TIMEOUT) as client:
            response = await client.post(OPENROUTER_CHAT_COMPLETIONS_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error_code": "openrouter_timeout",
                "message": "OpenRouter не завершил генерацию за установленное время.",
                "retryable": True,
                "suggested_model": "mistralai/mistral-small-3.2-24b-instruct",
            },
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenRouter вернул ошибку: {detail}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось выполнить запрос к OpenRouter.",
        ) from exc

    choice = data.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    return {
        "model": data.get("model", selected_model),
        "content": content,
        "usage": data.get("usage"),
        "id": data.get("id"),
        "finish_reason": choice.get("finish_reason"),
    }
