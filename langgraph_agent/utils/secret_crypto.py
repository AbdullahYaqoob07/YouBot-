"""
Encryption helpers for tenant/workspace secrets.
"""
import base64
import hashlib
from functools import lru_cache

from config import settings


def _derive_fernet_key(raw: str) -> bytes:
    """
    Accept a valid fernet key or derive one from passphrase text.
    """
    encoded = raw.encode("utf-8")
    if len(encoded) == 44:
        return encoded

    digest = hashlib.sha256(encoded).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _get_fernet():
    key_value = settings.LLM_CONFIG_ENCRYPTION_KEY
    if not key_value:
        raise RuntimeError("LLM_CONFIG_ENCRYPTION_KEY is not configured")

    try:
        from cryptography.fernet import Fernet
    except Exception as exc:
        raise RuntimeError("cryptography package is required for secret encryption") from exc

    return Fernet(_derive_fernet_key(key_value))


def encrypt_secret(plain_text: str) -> str:
    if not plain_text:
        raise ValueError("Secret cannot be empty")
    f = _get_fernet()
    token = f.encrypt(plain_text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    if not cipher_text:
        raise ValueError("Cipher text cannot be empty")
    f = _get_fernet()
    plain = f.decrypt(cipher_text.encode("utf-8"))
    return plain.decode("utf-8")


def mask_secret(value: str, prefix: int = 6, suffix: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= prefix + suffix:
        return "*" * len(value)
    return f"{value[:prefix]}...{value[-suffix:]}"
