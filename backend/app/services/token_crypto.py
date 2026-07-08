from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class OAuthTokenDecryptionError(RuntimeError):
    """Raised when an encrypted OAuth token was created with another key."""


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
        raise OAuthTokenDecryptionError(
            "Сохранённый OAuth-токен не удалось расшифровать текущим TOKEN_ENCRYPTION_KEY. "
            "Переподключите Яндекс-аккаунт или перенесите старый ключ шифрования."
        ) from exc
