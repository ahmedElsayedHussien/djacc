import base64
import hashlib
import logging
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _get_fernet_key(secret_key: str) -> bytes:
    """Derive a valid Fernet key from Django's SECRET_KEY"""
    raw = hashlib.sha256(secret_key.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(raw)


def get_fernet() -> Fernet:
    key = _get_fernet_key(settings.SECRET_KEY)
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return ''
    f = get_fernet()
    return f.encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt_value(ciphertext: str) -> str:
    if not ciphertext:
        return ''
    try:
        f = get_fernet()
        return f.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        logger.error("Decryption failed: invalid token or wrong key")
        return ''
    except Exception as e:
        logger.error(f"Decryption failed with unexpected error: {e}")
        return ''
