from secrets import token_urlsafe
from urllib.parse import urlencode

from fastapi import APIRouter

from app.core.config import settings
from app.schemas import YandexAuthCallbackResponse, YandexAuthStartResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/yandex/start", response_model=YandexAuthStartResponse)
def start_yandex_oauth() -> YandexAuthStartResponse:
    state = token_urlsafe(24)

    if not settings.yandex_client_id:
        return YandexAuthStartResponse(
            configured=False,
            auth_url=None,
            state=state,
            message="Set YANDEX_CLIENT_ID and YANDEX_REDIRECT_URI to enable Yandex OAuth.",
        )

    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.yandex_client_id,
            "redirect_uri": settings.yandex_redirect_uri,
            "state": state,
        }
    )
    return YandexAuthStartResponse(
        configured=True,
        auth_url=f"{settings.yandex_oauth_authorize_url}?{query}",
        state=state,
        message="Open auth_url to connect a Yandex Direct account.",
    )


@router.get("/yandex/callback", response_model=YandexAuthCallbackResponse)
def yandex_oauth_callback(code: str | None = None, state: str | None = None) -> YandexAuthCallbackResponse:
    if not code:
        return YandexAuthCallbackResponse(
            status="missing_code",
            code_received=False,
            state=state,
            message="Yandex OAuth callback did not include a confirmation code.",
        )

    return YandexAuthCallbackResponse(
        status="code_received",
        code_received=True,
        state=state,
        message="Confirmation code received. Token exchange and encrypted storage are the next backend step.",
    )
