import httpx

from app.core.config import settings
from app.schemas import YandexTokenResponse, YandexUserInfo


def exchange_code_for_token(code: str) -> YandexTokenResponse:
    if not settings.yandex_client_id or not settings.yandex_client_secret:
        raise RuntimeError("YANDEX_CLIENT_ID and YANDEX_CLIENT_SECRET are required for token exchange")

    response = httpx.post(
        settings.yandex_oauth_token_url,
        data={"grant_type": "authorization_code", "code": code},
        auth=(settings.yandex_client_id, settings.yandex_client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    if response.status_code >= 400:
        detail = response.text
        try:
            payload = response.json()
            detail = payload.get("error_description") or payload.get("error") or detail
        except ValueError:
            pass
        raise RuntimeError(f"Yandex OAuth token exchange failed: {detail}")
    return YandexTokenResponse.model_validate(response.json())


def fetch_yandex_user_info(access_token: str) -> YandexUserInfo | None:
    response = httpx.get(
        settings.yandex_userinfo_url,
        params={"format": "json"},
        headers={"Authorization": f"OAuth {access_token}"},
        timeout=20,
    )
    if response.status_code >= 400:
        return None
    return YandexUserInfo.model_validate(response.json())
