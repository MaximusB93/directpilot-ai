import os
from dataclasses import dataclass, field


def _split_scopes(value: str) -> list[str]:
    return [scope.strip() for scope in value.replace(",", " ").split() if scope.strip()]


@dataclass(frozen=True)
class Settings:
    api_prefix: str = "/api/v1"
    service_name: str = "directpilot-ai-backend"
    environment: str = os.getenv("ENVIRONMENT", "development")
    database_url: str | None = os.getenv("DATABASE_URL")
    token_encryption_key: str | None = os.getenv("TOKEN_ENCRYPTION_KEY")
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
    def yandex_oauth_configured(self) -> bool:
        return bool(self.yandex_client_id and self.yandex_client_secret and self.yandex_redirect_uri)

    @property
    def postgres_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def token_storage_configured(self) -> bool:
        return bool(self.database_url and self.token_encryption_key)


settings = Settings()
