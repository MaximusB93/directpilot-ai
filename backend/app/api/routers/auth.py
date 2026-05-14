from secrets import token_urlsafe
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db, get_optional_db
from app.schemas import (
    EmailCodeRequest,
    EmailCodeRequestResponse,
    EmailCodeVerifyRequest,
    EmailCodeVerifyResponse,
    YandexAuthCallbackResponse,
    YandexAuthStartResponse,
    YandexConnectionStatus,
)
from app.services.connected_accounts import get_yandex_connection_status, save_yandex_connection
from app.services.email_auth import request_email_code, verify_email_code
from app.services.yandex_oauth import exchange_code_for_token, fetch_yandex_user_info

router = APIRouter(prefix="/auth", tags=["auth"])




@router.post("/email/request-code", response_model=EmailCodeRequestResponse)
def request_login_code(request: EmailCodeRequest, db: Session = Depends(get_db)) -> EmailCodeRequestResponse:
    try:
        return request_email_code(db, request.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/email/verify-code", response_model=EmailCodeVerifyResponse)
def verify_login_code(request: EmailCodeVerifyRequest, db: Session = Depends(get_db)) -> EmailCodeVerifyResponse:
    try:
        return verify_email_code(db, request.email, request.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _oauth_env_message() -> str:
    if settings.yandex_env_has_redacted_values:
        return (
            "Yandex OAuth environment variables contain redacted placeholder characters. "
            "Open Vercel Environment Variables and paste the real YANDEX_CLIENT_ID and YANDEX_CLIENT_SECRET values, "
            "not the masked bullets shown by the Vercel UI."
        )
    if not settings.yandex_oauth_configured:
        return "Set YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET and YANDEX_REDIRECT_URI to enable Yandex OAuth."
    return "Open auth_url to connect a Yandex Direct account."


@router.get("/yandex/start", response_model=YandexAuthStartResponse)
def start_yandex_oauth() -> YandexAuthStartResponse:
    state = token_urlsafe(24)

    if not settings.yandex_client_id or settings.yandex_env_has_redacted_values:
        return YandexAuthStartResponse(
            configured=False,
            auth_url=None,
            state=state,
            message=_oauth_env_message(),
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
        message=_oauth_env_message(),
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
@router.get("/yandex/connection-status", response_model=YandexConnectionStatus, include_in_schema=False)
def yandex_oauth_status(db: Session | None = Depends(get_optional_db)) -> YandexConnectionStatus:
    status = get_yandex_connection_status(db)
    return YandexConnectionStatus(
        configured=settings.yandex_oauth_configured,
        database_configured=settings.postgres_configured,
        token_storage_configured=settings.token_storage_configured,
        connected=status["connected"],
        accounts=status["accounts"],
        message=_oauth_env_message() if settings.yandex_env_has_redacted_values else status["message"],
    )
