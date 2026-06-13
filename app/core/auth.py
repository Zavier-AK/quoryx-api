"""Authentication dependencies.

Two caller classes (decided: "Both"):
  - Machine-to-machine (e.g. scripts/run-integration.ts) -> X-API-Key service key.
  - Lovable frontend (per-user) -> Supabase-issued JWT in the Authorization header.

All three dependencies short-circuit when settings.AUTH_ENABLED is False, so the
auth layer can be deployed dark and switched on once secrets + callers are ready.
Settings are read at call time (not import time) so tests can toggle them.
"""
import hmac
import logging
from typing import Optional

import jwt
from fastapi import Header, HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# Supabase access tokens carry aud="authenticated".
_SUPABASE_AUDIENCE = "authenticated"


def _service_key_ok(provided: Optional[str]) -> bool:
    """Constant-time compare of the presented key against the configured one."""
    expected = settings.SERVICE_API_KEY
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def _decode_supabase_jwt(authorization: Optional[str]) -> Optional[dict]:
    """Return verified JWT claims, or None if absent/invalid."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    if not settings.SUPABASE_JWT_SECRET:
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience=_SUPABASE_AUDIENCE,
        )
    except jwt.PyJWTError as exc:
        logger.info("JWT verification failed: %s", exc)
        return None


def require_service_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> None:
    """Guard: caller must present a valid service API key."""
    if not settings.AUTH_ENABLED:
        return
    if not _service_key_ok(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def require_user(authorization: Optional[str] = Header(None)) -> dict:
    """Guard: caller must present a valid Supabase JWT. Returns its claims."""
    if not settings.AUTH_ENABLED:
        return {}
    claims = _decode_supabase_jwt(authorization)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )
    return claims


def require_user_or_service(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> None:
    """Guard: accept either a valid service key or a valid Supabase JWT."""
    if not settings.AUTH_ENABLED:
        return
    if _service_key_ok(x_api_key) or _decode_supabase_jwt(authorization) is not None:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
