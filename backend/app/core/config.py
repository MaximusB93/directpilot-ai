import os
from dataclasses import dataclass, field


def _split_scopes(value: str) -> list[str]:
    return [scope.strip() for scope in value.replace(",", " ").split() if scope.strip()]


def _split_models(value: str) -> list[str]:
    return [model.strip() for model in value.replace("\n", ",").split(",") if model.strip()]


def _looks_redacted(value: str | None) -> bool:
    if not value:
        return False
    stripped = value.strip()
    return "•" in stripped or stripped in {"********", "****"} or stripped.startswith("<")


AI_MODEL_PRESETS: dict[str, dict[str, object]] = {
    "economy": {
        "id": "economy",
        "label": "Эконом",
        "purpose": "Быстрые вопросы и первичный анализ",
        "cost_tier": "low",
        "max_tokens": 1200,
        "warning": None,
    },
    "balanced": {
        "id": "balanced",
        "label": "Баланс",
        "purpose": "Обычный анализ кампаний",
        "cost_tier": "medium",
        "max_tokens": 2500,
        "warning": None,
    },
    "advanced": {
        "id": "advanced",
        "label": "Максимум",
        "purpose": "Глубокий анализ и сложные рекомендации",
        "cost_tier": "high",
        "max_tokens": 5000,
        "warning": "Может быть дороже",
    },
}

AI_RECOMMENDED_DEFAULT_PRESET = "balanced"
AI_FALLBACK_ECONOMY_MODEL = "openai/gpt-4o-mini"
PRODUCTION_AI_MODELS: tuple[dict[str, str], ...] = (
    {
        "id": "mistralai/mistral-small-3.2-24b-instruct",
        "name": "Mistral Small 3.2 · Эконом",
        "tier": "economy",
        "description": "Быстрые регулярные проверки и короткие ответы с контролем стоимости.",
    },
    {
        "id": "qwen/qwen3-14b",
        "name": "Qwen3 14B · Баланс",
        "tier": "balanced",
        "description": "Основной режим для анализа кампаний, запросов и CPA.",
    },
    {
        "id": "deepseek/deepseek-chat-v3.1",
        "name": "DeepSeek V3.1 · Глубокий анализ",
        "tier": "advanced",
        "description": "Более глубокий разбор сложных аудитов и спорных выводов.",
    },
)
DEFAULT_PRODUCTION_AI_MODEL = "qwen/qwen3-14b"


def production_ai_model_ids() -> list[str]:
    return [item["id"] for item in PRODUCTION_AI_MODELS]


def production_ai_model_map() -> dict[str, dict[str, str]]:
    return {item["id"]: dict(item) for item in PRODUCTION_AI_MODELS}


def normalize_production_ai_model(model: str | None) -> str:
    selected_model = (model or DEFAULT_PRODUCTION_AI_MODEL).strip()
    return selected_model if selected_model in set(production_ai_model_ids()) else DEFAULT_PRODUCTION_AI_MODEL


def ai_model_cost_tier(model_id: str) -> str:
    normalized = model_id.lower()
    production_model = production_ai_model_map().get(model_id)
    if production_model:
        tier = production_model.get("tier")
        return {"economy": "low", "balanced": "medium", "advanced": "medium", "deep": "medium"}.get(tier, "unknown")
    if "mini" in normalized or "flash" in normalized or "haiku" in normalized:
        return "low"
    if "sonnet" in normalized or "opus" in normalized or ("gpt-4" in normalized and "mini" not in normalized):
        return "high"
    if normalized == "openrouter/auto":
        return "unknown"
    return "unknown"


def ai_model_label(model_id: str) -> str:
    production_model = production_ai_model_map().get(model_id)
    if production_model:
        return production_model["name"]
    labels = {
        "openrouter/auto": "OpenRouter Auto",
        "openai/gpt-4o-mini": "GPT-4o mini",
        "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet",
        "google/gemini-flash-1.5": "Gemini Flash 1.5",
    }
    return labels.get(model_id, model_id)


def ai_model_recommended_for(model_id: str) -> list[str]:
    production_model = production_ai_model_map().get(model_id)
    if production_model:
        tier = production_model.get("tier")
        if tier == "economy":
            return ["Быстрые вопросы", "Регулярные проверки", "Короткие сводки"]
        if tier == "balanced":
            return ["Анализ кампаний", "Поисковые запросы", "CPA и цели"]
        return ["Глубокий аудит", "Сложные рекомендации", "Разбор спорных выводов"]
    tier = ai_model_cost_tier(model_id)
    if tier == "low":
        return ["Быстрые вопросы", "Первичный анализ", "Короткие сводки"]
    if tier == "high":
        return ["Глубокий анализ", "Сложные рекомендации", "Стратегические разборы"]
    return ["Обычный анализ", "Fallback-маршрутизация"]


def ai_recommended_default_model(models: list[str], configured_default: str) -> str:
    if configured_default and ai_model_cost_tier(configured_default) in {"low", "medium"}:
        return configured_default
    for model_id in models:
        if ai_model_cost_tier(model_id) == "low":
            return model_id
    return AI_FALLBACK_ECONOMY_MODEL


def ai_preset_cap(preset: str | None) -> int:
    preset_id = preset if preset in AI_MODEL_PRESETS else AI_RECOMMENDED_DEFAULT_PRESET
    return int(AI_MODEL_PRESETS[preset_id]["max_tokens"])


def normalize_ai_request_options(
    *,
    model: str | None,
    ai_preset: str | None,
    max_tokens: int | None,
    models: list[str],
    configured_default: str,
    production_only: bool = False,
) -> dict[str, object]:
    preset_id = ai_preset if ai_preset in AI_MODEL_PRESETS else AI_RECOMMENDED_DEFAULT_PRESET
    allowed_models = production_ai_model_ids() if production_only else models
    default_model = DEFAULT_PRODUCTION_AI_MODEL if production_only else ai_recommended_default_model(models, configured_default)
    selected_model = (model or default_model).strip()
    if production_only:
        selected_model = normalize_production_ai_model(selected_model)
    cap = ai_preset_cap(preset_id)
    requested_tokens = max_tokens if max_tokens is not None else cap
    effective_tokens = max(1, min(int(requested_tokens), cap))
    return {
        "model": selected_model,
        "ai_preset": preset_id,
        "max_tokens": effective_tokens,
        "max_tokens_cap": cap,
        "is_custom_model": bool(selected_model and selected_model not in set(allowed_models)),
        "cost_tier": ai_model_cost_tier(selected_model),
    }


@dataclass(frozen=True)
class Settings:
    api_prefix: str = "/api/v1"
    service_name: str = "directpilot-ai-backend"
    environment: str = os.getenv("ENVIRONMENT", "development")
    database_url: str | None = os.getenv("DATABASE_URL")
    database_schema_patch_on_startup: bool = os.getenv(
        "DATABASE_SCHEMA_PATCH_ON_STARTUP",
        "false" if os.getenv("ENVIRONMENT", "development").lower() == "production" else "true",
    ).lower() == "true"
    token_encryption_key: str | None = os.getenv("TOKEN_ENCRYPTION_KEY")
    email_auth_dev_mode: bool = os.getenv("EMAIL_AUTH_DEV_MODE", "false").lower() == "true"
    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "noreply@directpilot.ai")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openrouter_default_model: str = os.getenv("OPENROUTER_DEFAULT_MODEL", "openrouter/auto")
    openrouter_allow_custom_models: bool = os.getenv("OPENROUTER_ALLOW_CUSTOM_MODELS", "true").lower() == "true"
    openrouter_site_url: str = os.getenv("OPENROUTER_SITE_URL", "https://maximusb93.github.io/directpilot-ai")
    openrouter_app_name: str = os.getenv("OPENROUTER_APP_NAME", "DirectPilot AI")
    openrouter_models: list[str] = field(
        default_factory=lambda: _split_models(
            os.getenv(
                "OPENROUTER_MODELS",
                "openrouter/auto,openai/gpt-4o-mini,anthropic/claude-3.5-sonnet,google/gemini-flash-1.5",
            )
        )
    )
    yandex_client_id: str | None = os.getenv("YANDEX_CLIENT_ID")
    yandex_client_secret: str | None = os.getenv("YANDEX_CLIENT_SECRET")
    yandex_redirect_uri: str = os.getenv(
        "YANDEX_REDIRECT_URI",
        "http://localhost:8000/api/v1/auth/yandex/callback",
    )
    yandex_oauth_authorize_url: str = os.getenv(
        "YANDEX_OAUTH_AUTHORIZE_URL",
        "https://oauth.yandex.ru/authorize",
    )
    yandex_oauth_token_url: str = os.getenv(
        "YANDEX_OAUTH_TOKEN_URL",
        "https://oauth.yandex.ru/token",
    )
    yandex_userinfo_url: str = os.getenv(
        "YANDEX_USERINFO_URL",
        "https://login.yandex.ru/info",
    )
    yandex_oauth_scopes: list[str] = field(
        default_factory=lambda: _split_scopes(
            os.getenv("YANDEX_OAUTH_SCOPES", "direct:api metrika:read login:info")
        )
    )
    yandex_search_api_key: str | None = os.getenv("YANDEX_SEARCH_API_KEY")
    yandex_search_folder_id: str | None = os.getenv("YANDEX_SEARCH_FOLDER_ID")
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://maximusb93.github.io",
            "https://directpilot-ai-backend-mvp.vercel.app",
        ]
    )

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_username and self.smtp_password)

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key and not _looks_redacted(self.openrouter_api_key))

    @property
    def yandex_oauth_configured(self) -> bool:
        return bool(
            self.yandex_client_id
            and self.yandex_client_secret
            and self.yandex_redirect_uri
            and not _looks_redacted(self.yandex_client_id)
            and not _looks_redacted(self.yandex_client_secret)
        )

    @property
    def yandex_env_has_redacted_values(self) -> bool:
        return _looks_redacted(self.yandex_client_id) or _looks_redacted(self.yandex_client_secret)

    @property
    def postgres_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def token_storage_configured(self) -> bool:
        return bool(self.database_url and self.token_encryption_key)


settings = Settings()
