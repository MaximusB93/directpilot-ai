import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    api_prefix: str = "/api/v1"
    service_name: str = "directpilot-ai-backend"
    environment: str = "development"
    yandex_client_id: str | None = os.getenv("YANDEX_CLIENT_ID")
    yandex_redirect_uri: str = os.getenv(
        "YANDEX_REDIRECT_URI",
        "http://localhost:8000/api/v1/auth/yandex/callback",
    )
    yandex_oauth_authorize_url: str = "https://oauth.yandex.com/authorize"
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://maximusb93.github.io",
        ]
    )


settings = Settings()
