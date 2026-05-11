import pytest

from config import settings
from utils import secret_crypto


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CONFIG_ENCRYPTION_KEY", "phase2-local-test-key")
    secret_crypto._get_fernet.cache_clear()

    encrypted = secret_crypto.encrypt_secret("sk-test-value-123456")
    assert encrypted != "sk-test-value-123456"

    decrypted = secret_crypto.decrypt_secret(encrypted)
    assert decrypted == "sk-test-value-123456"


def test_mask_secret():
    masked = secret_crypto.mask_secret("abcdefghijklmnopqrstuvwxyz", prefix=4, suffix=3)
    assert masked.startswith("abcd")
    assert masked.endswith("xyz")
    assert "..." in masked


def test_encrypt_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CONFIG_ENCRYPTION_KEY", None)
    secret_crypto._get_fernet.cache_clear()

    with pytest.raises(RuntimeError):
        secret_crypto.encrypt_secret("value")
