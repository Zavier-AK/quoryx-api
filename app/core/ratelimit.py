"""Shared rate limiter.

Lives in its own module so both app.main (to register it) and the routers (to
apply per-route limits) can import the same Limiter without a circular import.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def client_ip(request: Request) -> str:
    """
    Real client IP for rate-limit keying.

    Railway terminates TLS at a proxy, so request.client.host is the proxy's IP
    (every caller would share one bucket). Prefer the first hop in X-Forwarded-For.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Global default applies to every route via SlowAPIMiddleware; expensive routes
# add a tighter per-route @limiter.limit(...) on top.
limiter = Limiter(key_func=client_ip, default_limits=["120/minute"])

# Tight limit for endpoints that fan out to external provider APIs or cost money
# (ingest, reconciliation runs, live provider fetches).
EXPENSIVE_LIMIT = "10/minute"
