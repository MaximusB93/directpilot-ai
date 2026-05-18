import httpx
from fastapi import HTTPException, status

from app.core.config import settings

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_SYSTEM_PROMPT = """
Ты senior PPC-стратег DirectPilot AI. Анализируй Яндекс.Директ, Метрику и CRM-данные прагматично.
Всегда разделяй факты, гипотезы и безопасные следующие шаги. Не предлагай применять изменения без approval/dry-run.
Пиши по-русски, структурируй ответ списками и указывай, какие данные нужны для проверки вывода.
""".strip()


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
        "message": (
            "OpenRouter подключён через backend. Ключ хранится только в переменных окружения сервера."
            if configured
            else "Добавьте OPENROUTER_API_KEY в окружение backend, чтобы включить генерацию ответов."
        ),
    }


async def generate_openrouter_response(model: str, prompt: str) -> dict[str, object]:
    if not settings.openrouter_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenRouter не настроен: добавьте OPENROUTER_API_KEY в окружение backend.",
        )

    allowed_models = set(settings.openrouter_models)
    selected_model = model or settings.openrouter_default_model
    if selected_model not in allowed_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Модель {selected_model} не разрешена. Добавьте её в OPENROUTER_MODELS.",
        )

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 900,
    }
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
