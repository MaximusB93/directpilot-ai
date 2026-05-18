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


@dataclass(frozen=True)
class Settings:
    api_prefix: str = "/api/v1"
    service_name: str = "directpilot-ai-backend"
    environment: str = os.getenv("ENVIRONMENT", "development")
    database_url: str | None = os.getenv("DATABASE_URL")
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
    openrouter_site_url: str = os.getenv("OPENROUTER_SITE_URL", "https://directpilot-ai.vercel.app")
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
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://maximusb93.github.io",
            "https://directpilot-ai.vercel.app",
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
