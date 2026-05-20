from __future__ import annotations

import hashlib
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuthSession, EmailAuthCode, Organization, User
from app.schemas import EmailCodeRequestResponse, EmailCodeVerifyResponse

CODE_TTL_SECONDS = 10 * 60
SESSION_TTL_DAYS = 30
MAX_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_session_token(value: str) -> str:
    return _hash(value)


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("Enter a valid email address.")
    return normalized


def normalize_email(email: str) -> str:
    return _normalize_email(email)


def ensure_user_for_email(db: Session, email: str) -> User:
    normalized_email = _normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized_email, User.provider == "email"))
    if user:
        return user

    organization = db.scalar(select(Organization).where(Organization.name == f"Workspace: {normalized_email}"))
    if organization is None:
        organization = Organization(name=f"Workspace: {normalized_email}")
        db.add(organization)
        db.flush()

    user = User(
        organization_id=organization.id,
        email=normalized_email,
        name=normalized_email,
        external_user_id=normalized_email,
        provider="email",
    )
    db.add(user)
    db.flush()
    return user


def _send_code_email(email: str, code: str) -> None:
    if not settings.smtp_configured:
        if settings.email_auth_dev_mode:
            return
        raise RuntimeError("SMTP is not configured. Set SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD.")

    message = EmailMessage()
    message["Subject"] = "Ваш код DirectPilot AI"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        f"Ваш код для входа в DirectPilot AI: {code}\n\n"
        "Код действует 10 минут. Если вы не запрашивали вход, просто игнорируйте письмо."
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def request_email_code(db: Session, email: str) -> EmailCodeRequestResponse:
    normalized_email = _normalize_email(email)
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = _now() + timedelta(seconds=CODE_TTL_SECONDS)

    db.add(
        EmailAuthCode(
            email=normalized_email,
            code_hash=_hash(code),
            expires_at=expires_at,
        )
    )
    db.commit()
    _send_code_email(normalized_email, code)
    return EmailCodeRequestResponse(
        status="sent",
        message="Login code sent to email.",
        expires_in_seconds=CODE_TTL_SECONDS,
        dev_code=code if settings.email_auth_dev_mode else None,
    )


def verify_email_code(db: Session, email: str, code: str) -> EmailCodeVerifyResponse:
    normalized_email = _normalize_email(email)
    auth_code = db.scalar(
        select(EmailAuthCode)
        .where(EmailAuthCode.email == normalized_email, EmailAuthCode.status == "pending")
        .order_by(EmailAuthCode.created_at.desc())
        .limit(1)
    )
    if auth_code is None:
        raise ValueError("Code was not requested or has already been used.")
    if _as_aware(auth_code.expires_at) < _now():
        auth_code.status = "expired"
        db.commit()
        raise ValueError("Code expired. Request a new code.")
    if auth_code.attempts >= MAX_ATTEMPTS:
        auth_code.status = "blocked"
        db.commit()
        raise ValueError("Too many attempts. Request a new code.")

    auth_code.attempts += 1
    if auth_code.code_hash != _hash(code.strip()):
        db.commit()
        raise ValueError("Invalid code.")

    auth_code.status = "consumed"
    auth_code.consumed_at = _now()
    raw_token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(days=SESSION_TTL_DAYS)
    db.add(
        AuthSession(
            email=normalized_email,
            token_hash=_hash(raw_token),
            expires_at=expires_at,
        )
    )
    ensure_user_for_email(db, normalized_email)
    db.commit()
    return EmailCodeVerifyResponse(
        authenticated=True,
        email=normalized_email,
        session_token=raw_token,
        expires_at=expires_at.isoformat(),
    )
