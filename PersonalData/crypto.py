import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _get_fernet() -> Fernet:
    """Ключ выводится из PERSONAL_CRYPTO_KEY (или SECRET_KEY). Добавьте PERSONAL_CRYPTO_KEY в .env."""
    seed = getattr(settings, 'PERSONAL_CRYPTO_KEY', '') or settings.SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode('utf-8')).digest())
    return Fernet(key)


def encrypt_value(raw: str) -> str:
    return _get_fernet().encrypt(raw.encode('utf-8')).decode('utf-8')


def decrypt_value(token: str) -> str:
    if not token:
        return ''
    try:
        return _get_fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return '••• ошибка расшифровки •••'