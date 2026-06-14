"""Token encryption tests (Phase 3).

Cover the transition-friendly behavior of app.core.crypto:
  - round-trip encrypt -> decrypt returns the original plaintext,
  - legacy plaintext (no enc:v1: prefix) passes through decrypt unchanged,
  - with no key configured, encrypt is a no-op.

Run: pytest tests_py/
"""
from cryptography.fernet import Fernet

from app.core import crypto
from app.core.config import settings


def test_round_trip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", key)

    plaintext = "super-secret-access-token"
    encrypted = crypto.encrypt_token(plaintext)

    assert encrypted != plaintext
    assert encrypted.startswith("enc:v1:")
    assert crypto.decrypt_token(encrypted) == plaintext


def test_legacy_plaintext_passthrough(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", key)

    legacy = "plaintext-token-no-prefix"
    # Even with a key set, an unprefixed value is treated as legacy plaintext.
    assert crypto.decrypt_token(legacy) == legacy


def test_encrypt_noop_without_key(monkeypatch):
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", "")

    plaintext = "token-stays-plaintext"
    assert crypto.encrypt_token(plaintext) == plaintext
