from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def generate_token_encryption_key() -> str:
    return Fernet.generate_key().decode("utf-8")


def _fernet() -> Fernet:
    if not settings.token_encryption_key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is required for encrypted OAuth token storage")
    return Fernet(settings.token_encryption_key.encode("utf-8"))


def encrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored OAuth token cannot be decrypted with current TOKEN_ENCRYPTION_KEY") from exc
