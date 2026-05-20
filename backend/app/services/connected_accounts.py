from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import ConnectedAccount, OAuthToken, Organization, User
from app.schemas import ConnectedYandexAccount, YandexTokenResponse, YandexUserInfo
from app.services.token_crypto import decrypt_secret, encrypt_secret

DEFAULT_ORG_NAME = "DirectPilot AI"


def _now() -> datetime:
    return datetime.now(UTC)


def ensure_default_organization(db: Session) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.name == DEFAULT_ORG_NAME))
    if organization:
        return organization
    organization = Organization(name=DEFAULT_ORG_NAME)
    db.add(organization)
    db.flush()
    return organization


def _account_to_schema(account: ConnectedAccount) -> ConnectedYandexAccount:
    token = account.tokens[-1] if account.tokens else None
    external_user_id = account.external_user_id
    if external_user_id and external_user_id.endswith(f":{account.organization_id}"):
        external_user_id = external_user_id[: -(len(account.organization_id) + 1)]
    return ConnectedYandexAccount(
        id=account.id,
        provider=account.provider,
        status=account.status,
        login=account.login,
        display_name=account.display_name,
        external_user_id=external_user_id,
        scope=account.scope,
        connected_at=account.connected_at.isoformat(),
        updated_at=account.updated_at.isoformat(),
        token_expires_at=token.expires_at.isoformat() if token and token.expires_at else None,
    )


def _scoped_external_user_id(external_user_id: str | None, organization_id: str) -> str | None:
    if not external_user_id:
        return None
    if external_user_id.endswith(f":{organization_id}"):
        return external_user_id
    return f"{external_user_id}:{organization_id}"


def save_yandex_connection(
    db: Session,
    token: YandexTokenResponse,
    user_info: YandexUserInfo | None,
    organization_id: str | None = None,
) -> ConnectedYandexAccount:
    organization = db.get(Organization, organization_id) if organization_id else None
    if organization_id and organization is None:
        raise RuntimeError("OAuth workspace was not found. Please restart Yandex connection from the app.")
    if organization is None:
        # TODO: Bind OAuth callback to a verified browser session instead of this MVP fallback.
        organization = ensure_default_organization(db)
    external_user_id = user_info.id if user_info else None
    stored_external_user_id = _scoped_external_user_id(external_user_id, organization.id)
    login = user_info.login if user_info else None
    display_name = user_info.display_name if user_info else None

    account = None
    if external_user_id:
        account = db.scalar(
            select(ConnectedAccount).where(
                ConnectedAccount.provider == "yandex",
                or_(
                    ConnectedAccount.external_user_id == external_user_id,
                    ConnectedAccount.external_user_id == stored_external_user_id,
                ),
                ConnectedAccount.organization_id == organization.id,
            )
        )

    if account is None:
        account = ConnectedAccount(organization_id=organization.id, provider="yandex")
        db.add(account)
        db.flush()

    account.external_user_id = stored_external_user_id
    account.login = login
    account.display_name = display_name
    account.status = "connected"
    account.scope = token.scope

    if user_info:
        user = None
        if external_user_id:
            stored_user_external_id = _scoped_external_user_id(external_user_id, organization.id)
            user = db.scalar(
                select(User).where(
                    User.provider == "yandex",
                    or_(User.external_user_id == external_user_id, User.external_user_id == stored_user_external_id),
                    User.organization_id == organization.id,
                )
            )
        if user is None:
            user = User(organization_id=organization.id, provider="yandex")
            db.add(user)
        user.external_user_id = stored_user_external_id if external_user_id else None
        user.email = user_info.default_email
        user.name = display_name or login

    expires_at = _now() + timedelta(seconds=token.expires_in) if token.expires_in else None
    db.add(
        OAuthToken(
            account_id=account.id,
            token_type=token.token_type,
            access_token_encrypted=encrypt_secret(token.access_token),
            refresh_token_encrypted=encrypt_secret(token.refresh_token),
            scope=token.scope,
            expires_at=expires_at,
        )
    )
    db.commit()
    db.refresh(account)
    return _account_to_schema(account)


def list_yandex_accounts(db: Session, organization_id: str | None = None) -> list[ConnectedYandexAccount]:
    query = select(ConnectedAccount).where(ConnectedAccount.provider == "yandex")
    if organization_id:
        query = query.where(ConnectedAccount.organization_id == organization_id)
    accounts = db.scalars(query).unique().all()
    return [_account_to_schema(account) for account in accounts]


def get_latest_yandex_access_token(db: Session) -> str | None:
    token = db.scalar(
        select(OAuthToken)
        .join(ConnectedAccount)
        .where(ConnectedAccount.provider == "yandex", ConnectedAccount.status == "connected")
        .order_by(OAuthToken.created_at.desc())
        .limit(1)
    )
    return decrypt_secret(token.access_token_encrypted) if token else None


def get_yandex_access_token_for_account(db: Session, account_id: str) -> str | None:
    token = db.scalar(
        select(OAuthToken)
        .join(ConnectedAccount)
        .where(
            ConnectedAccount.id == account_id,
            ConnectedAccount.provider == "yandex",
            ConnectedAccount.status == "connected",
        )
        .order_by(OAuthToken.created_at.desc())
        .limit(1)
    )
    return decrypt_secret(token.access_token_encrypted) if token else None


def get_yandex_connection_status(db: Session | None, organization_id: str | None = None) -> dict[str, Any]:
    if db is None:
        return {"connected": False, "accounts": [], "message": "DATABASE_URL is not configured."}
    accounts = list_yandex_accounts(db, organization_id=organization_id)
    return {
        "connected": bool(accounts),
        "accounts": [account.model_dump() for account in accounts],
        "message": "Yandex account is connected." if accounts else "No Yandex account connected yet.",
    }
