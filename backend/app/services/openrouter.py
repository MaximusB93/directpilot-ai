import re

import httpx
from fastapi import HTTPException, status
from typing import Any

from app.core.config import settings
from app.services.ai_prompt_debug import clamp_openrouter_max_tokens

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_SYSTEM_PROMPT = """
Ты senior PPC-стратег DirectPilot AI. Анализируй Яндекс.Директ, Метрику и CRM-данные прагматично.
Всегда разделяй факты, гипотезы и безопасные следующие шаги. Не предлагай применять изменения без approval/dry-run.
Пиши по-русски, структурируй ответ списками и указывай, какие данные нужны для проверки вывода.
""".strip()

SECRET_KEY_PARTS = ("authorization", "api_key", "apikey", "token", "secret", "password", "cookie", "refresh")


def _validate_openrouter_model(model: str | None) -> str:
    allowed_models = set(settings.openrouter_models)
    selected_model = (model or settings.openrouter_default_model).strip()
    if not selected_model or len(selected_model) > 200 or any(char.isspace() for char in selected_model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор модели OpenRouter.")
    if selected_model not in allowed_models and not settings.openrouter_allow_custom_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Модель {selected_model} не разрешена. Добавьте её в OPENROUTER_MODELS или включите OPENROUTER_ALLOW_CUSTOM_MODELS=true.",
        )
    return selected_model


def build_openrouter_payload(model: str, prompt: str, max_tokens: int | None = None) -> dict[str, Any]:
    selected_model = _validate_openrouter_model(model)
    return {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": clamp_openrouter_max_tokens(max_tokens),
    }


def redact_openrouter_debug_payload(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
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


def configured_models() -> list[dict[str, str]]:
    descriptions = {
        "openrouter/auto": "Автовыбор OpenRouter для быстрых прототипов и fallback-маршрутизации.",
        "openai/gpt-4o-mini": "Быстрые и недорогие продуктовые тексты, классификация и черновики рекомендаций.",
        "anthropic/claude-3.5-sonnet": "Сильная модель для глубокого анализа, ревью стратегий и сложных объяснений.",
        "google/gemini-flash-1.5": "Быстрая модель для сводок, коротких отчётов и массовой обработки карточек.",
    }
    return [
        {
            "id": model_id,
            "name": model_id,
            "description": descriptions.get(model_id, "Модель OpenRouter из OPENROUTER_MODELS."),
        }
        for model_id in settings.openrouter_models
    ]


def openrouter_status() -> dict[str, object]:
    configured = settings.openrouter_configured
    return {
        "configured": configured,
        "default_model": settings.openrouter_default_model,
        "models": configured_models(),
        "allow_custom_models": settings.openrouter_allow_custom_models,
        "message": (
            "OpenRouter подключён через backend. Ключ хранится только в переменных окружения сервера."
            if configured
            else "Добавьте OPENROUTER_API_KEY в окружение backend, чтобы включить генерацию ответов."
        ),
    }


async def generate_openrouter_response(model: str, prompt: str, max_tokens: int | None = None) -> dict[str, object]:
    if not settings.openrouter_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenRouter не настроен: добавьте OPENROUTER_API_KEY в окружение backend.",
        )

    allowed_models = set(settings.openrouter_models)
    selected_model = (model or settings.openrouter_default_model).strip()
    if not selected_model or len(selected_model) > 200 or any(char.isspace() for char in selected_model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный идентификатор модели OpenRouter.")
    if selected_model not in allowed_models and not settings.openrouter_allow_custom_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Модель {selected_model} не разрешена. Добавьте её в OPENROUTER_MODELS или включите OPENROUTER_ALLOW_CUSTOM_MODELS=true.",
        )

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": clamp_openrouter_max_tokens(max_tokens),
    }
    payload = build_openrouter_payload(selected_model, prompt, max_tokens=max_tokens)
    selected_model = str(payload["model"])
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(OPENROUTER_CHAT_COMPLETIONS_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
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

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {
        "model": data.get("model", selected_model),
        "content": content,
        "usage": data.get("usage"),
        "id": data.get("id"),
    }
