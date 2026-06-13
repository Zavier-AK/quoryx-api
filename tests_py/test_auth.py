"""Auth-layer tests for the FastAPI backend (Phase 1).

These exercise the guard behavior only — a 401 is raised by the dependency before
the handler runs, so no DB/data is needed. We assert that:
  - guarded endpoints reject anonymous callers when AUTH_ENABLED,
  - a valid service key / Supabase JWT passes the guard (status != 401/403),
  - AUTH_ENABLED=false disables the gate.

Run: pytest tests_py/
"""
import datetime

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app, raise_server_exceptions=False)

SERVICE_KEY = "test-service-key"
JWT_SECRET = "test-jwt-secret"


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    """Default every test to auth ON with known secrets."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "SERVICE_API_KEY", SERVICE_KEY)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", JWT_SECRET)


def _valid_jwt() -> str:
    payload = {
        "sub": "user-123",
        "aud": "authenticated",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# --- Service-key endpoints ---

def test_service_endpoint_rejects_anonymous():
    assert client.post("/api/reconciliation/run").status_code == 401


def test_service_endpoint_rejects_wrong_key():
    r = client.post("/api/reconciliation/run", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_service_endpoint_accepts_valid_key():
    # Passes the guard; handler may 4xx/5xx on data, but must not be 401/403.
    r = client.post("/api/reconciliation/run", headers={"X-API-Key": SERVICE_KEY})
    assert r.status_code not in (401, 403)


def test_service_endpoint_rejects_jwt():
    # JWT must not satisfy a service-key-only endpoint.
    r = client.post(
        "/api/reconciliation/run",
        headers={"Authorization": f"Bearer {_valid_jwt()}"},
    )
    assert r.status_code == 401


# --- User (JWT) endpoints ---

def test_user_endpoint_rejects_anonymous():
    assert client.get("/api/reconciliation/pairs").status_code == 401


def test_user_endpoint_rejects_bad_jwt():
    r = client.get(
        "/api/reconciliation/pairs",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


def test_user_endpoint_accepts_valid_jwt():
    r = client.get(
        "/api/reconciliation/pairs",
        headers={"Authorization": f"Bearer {_valid_jwt()}"},
    )
    assert r.status_code not in (401, 403)


# --- user_or_service endpoint accepts either ---

def test_user_or_service_accepts_service_key():
    r = client.get("/api/economic/self", headers={"X-API-Key": SERVICE_KEY})
    assert r.status_code not in (401, 403)


def test_user_or_service_accepts_jwt():
    r = client.get(
        "/api/economic/self", headers={"Authorization": f"Bearer {_valid_jwt()}"}
    )
    assert r.status_code not in (401, 403)


def test_user_or_service_rejects_anonymous():
    assert client.get("/api/economic/self").status_code == 401


# --- Open + flag behavior ---

def test_health_is_open():
    assert client.get("/api/health").status_code == 200


def test_auth_disabled_opens_guarded_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    r = client.post("/api/reconciliation/run")
    assert r.status_code not in (401, 403)
