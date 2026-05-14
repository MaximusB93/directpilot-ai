from secrets import token_urlsafe
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.schemas import YandexAuthCallbackResponse, YandexAuthStartResponse, YandexConnectionStatus
from app.services.connected_accounts import get_yandex_connection_status, save_yandex_connection
from app.services.yandex_oauth import exchange_code_for_token, fetch_yandex_user_info

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/yandex/start", response_model=YandexAuthStartResponse)
def start_yandex_oauth() -> YandexAuthStartResponse:
    state = token_urlsafe(24)

    if not settings.yandex_client_id:
        return YandexAuthStartResponse(
            configured=False,
            auth_url=None,
            state=state,
            message="Set YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET and YANDEX_REDIRECT_URI to enable Yandex OAuth.",
        )

    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.yandex_client_id,
            "redirect_uri": settings.yandex_redirect_uri,
            "scope": " ".join(settings.yandex_oauth_scopes),
            "state": state,
        }
    )
    return YandexAuthStartResponse(
        configured=settings.yandex_oauth_configured,
        auth_url=f"{settings.yandex_oauth_authorize_url}?{query}",
        state=state,
        message="Open auth_url to connect a Yandex Direct account.",
    )


@router.get("/yandex/callback", response_model=YandexAuthCallbackResponse)
def yandex_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
) -> YandexAuthCallbackResponse:
    if not code:
        return YandexAuthCallbackResponse(
            status="missing_code",
            code_received=False,
            state=state,
            message="Yandex OAuth callback did not include a confirmation code.",
        )

    if not settings.token_encryption_key:
        raise HTTPException(status_code=500, detail="TOKEN_ENCRYPTION_KEY is required before storing OAuth tokens.")

    try:
        token = exchange_code_for_token(code)
        user_info = fetch_yandex_user_info(token.access_token)
        account = save_yandex_connection(db=db, token=token, user_info=user_info)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return YandexAuthCallbackResponse(
        status="connected",
        code_received=True,
        state=state,
        message="Yandex account connected and OAuth token stored encrypted.",
        account=account,
    )


@router.get("/yandex/status", response_model=YandexConnectionStatus)
def yandex_oauth_status(db: Session = Depends(get_db)) -> YandexConnectionStatus:
    status = get_yandex_connection_status(db)
    return YandexConnectionStatus(
        configured=settings.yandex_oauth_configured,
        database_configured=settings.postgres_configured,
        token_storage_configured=settings.token_storage_configured,
        connected=status["connected"],
        accounts=status["accounts"],
        message=status["message"],
    )
