"""Token encryption at rest (Phase 3).

Encrypts OAuth tokens transparently at the ORM layer via the ``EncryptedString``
``TypeDecorator``. The design tolerates a gradual transition from existing
plaintext tokens:

  * Encrypted values are tagged with an ``enc:v1:`` prefix.
  * ``decrypt_token`` treats any value without that prefix as legacy plaintext
    and passes it through unchanged, so rows written before this change still
    read correctly.
  * When ``TOKEN_ENCRYPTION_KEY`` is empty, ``encrypt_token`` is a no-op, so the
    app keeps booting / writing plaintext until a key is configured.

Nothing here ever raises on bad/missing keys — decryption failures degrade to
returning the stored value as-is and emit a warning.
"""

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"


def encrypt_token(value: Optional[str]) -> Optional[str]:
    """Encrypt a plaintext token, returning ``enc:v1:<ciphertext>``.

    No-op (returns ``value`` unchanged) when ``value`` is empty/None or no
    encryption key is configured.
    """
    if not value:
        return value

    key = settings.TOKEN_ENCRYPTION_KEY
    if not key:
        logger.warning(
            "TOKEN_ENCRYPTION_KEY is not set; storing OAuth token as plaintext."
        )
        return value

    token = Fernet(key.encode()).encrypt(value.encode()).decode()
    return _PREFIX + token


def decrypt_token(value: Optional[str]) -> Optional[str]:
    """Decrypt an ``enc:v1:`` token; pass legacy plaintext through unchanged.

    Never raises: a missing/invalid key on a prefixed value logs a warning and
    returns the stored value as-is.
    """
    if not value or not value.startswith(_PREFIX):
        return value

    ciphertext = value[len(_PREFIX):]
    key = settings.TOKEN_ENCRYPTION_KEY
    if not key:
        logger.warning(
            "Encountered an encrypted token but TOKEN_ENCRYPTION_KEY is not set; "
            "returning the stored value unchanged."
        )
        return value

    try:
        return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.warning("Failed to decrypt token: %s", exc)
        return value


class EncryptedString(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts/decrypts strings."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_token(value)

    def process_result_value(self, value, dialect):
        return decrypt_token(value)
