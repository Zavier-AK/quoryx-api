# Quoryx Security Remediation Plan

Status of the FastAPI backend (`app/`) as of 2026-06-13. The matching engine logic
is clean; the API layer that exposes customer financial data has no security
controls yet. This document tracks the findings and the phased fix.

## Findings (by severity)

### 🔴 Critical
1. **No authentication on any endpoint.** Anyone with the Railway URL can ingest a
   customer's books, read every customer's transactions, and mutate reconciliation.
2. **No tenant isolation (IDOR).** No owner/org scoping — once there are two
   customers, A can read B's data via `GET /transactions` / `GET /transactions/{id}`.
3. **OAuth tokens stored in plaintext** (`oauth_tokens.access_token/refresh_token`).
   A DB leak = full access to every connected customer's accounting system.

### 🟠 High
4. **No rate limiting** — trivial DoS; ingest fans out to Xero/e-conomic (risking
   our provider access) and the LLM fallback costs money per call.
5. **`APP_DEBUG` defaults to `True`** → `/docs` + `/redoc` public unless prod sets it.
6. **`APP_SECRET_KEY` defaults to `"change-me"`** — known signing key if unset.
7. **OAuth state in-memory & unbounded** (`_pending_states`) — it is the CSRF
   protection for the OAuth flow, breaks across workers, never expires.
8. **Error messages leak upstream provider bodies** to the client.

### 🟡 Medium
9. **Mass assignment** on `POST /transactions/` (`Transaction(**payload.model_dump())`).
10. **Unbounded list endpoints** (no pagination cap).
11. **CORS** pinned to one origin (good) but `allow_methods/headers=["*"]`.

### 🟢 Good
- No SQL injection (SQLAlchemy ORM; the one raw `text()` is a static literal).
- CORS origin locked down; no secrets in code; `.env` gitignored.

## Auth model (decided)
**Both**: Supabase JWT for the Lovable frontend + a service API key for the
`run-integration.ts` machine-to-machine path.

## Phases

### Phase 1 — Authentication + rate limiting  ← IN PROGRESS
- Deps: `slowapi`, `pyjwt[crypto]`, dev `pytest`.
- Config: `SERVICE_API_KEY`, `SUPABASE_JWT_SECRET`, `AUTH_ENABLED` (rollout flag);
  flip `APP_DEBUG` default → `False`.
- `app/core/auth.py`: `require_service_key`, `require_user` (Supabase JWT),
  `require_user_or_service`.
- `app/core/ratelimit.py`: shared `slowapi` limiter keyed on the real client IP
  (`X-Forwarded-For`, since Railway is behind a proxy).
- `app/main.py`: register limiter + global default limit + `RateLimitExceeded` handler.
- Guard every router (see mapping below); stricter per-route limits on the
  expensive endpoints (ingest, reconciliation/run, transactions/fetch).
- `scripts/run-integration.ts`: send `X-API-Key`; move Railway base URL to env.
- Tests: `tests_py/test_auth.py` (FastAPI TestClient).

Endpoint → guard mapping:

| Endpoints | Guard |
|---|---|
| `/reconciliation/run`, `/detect`, `PATCH /pairs/{id}/status` | service key |
| `/xero/ingest`, `/economic/ingest`, `/entities/sync` | service key |
| `POST /transactions/`, `/transactions/{id}/reconcile` | service key |
| `/reconciliation/pairs`, `/summary`, `/entities`, `/transactions` (GET, GET/{id}) | user (JWT) |
| `/xero/*` reads, `/economic/self`, `/economic/invoices/booked`, `/transactions/fetch` | user or service |
| `/auth/*/login`, `/auth/*/callback` | none — hardened via OAuth-state CSRF in Phase 4 |
| `/health` | none; `/health/db` | service key |

Rollout (no-downtime): deploy with `AUTH_ENABLED=false`, set `SERVICE_API_KEY` +
`SUPABASE_JWT_SECRET` in Railway, update the frontend to send the bearer token and
the script to send `X-API-Key`, then set `AUTH_ENABLED=true`.

### Phase 2 — Tenant isolation
Owner/org column linking entities→transactions→pairs to a Supabase user; tie OAuth
login to the authenticated user; filter every read by tenant; fix mass assignment.

### Phase 3 — Secrets at rest + secure-by-default
Encrypt OAuth tokens (Fernet, `TOKEN_ENCRYPTION_KEY`); fail-fast on default secrets
in production; generic error responses (stop leaking provider bodies).

### Phase 4 — Hardening
OAuth state → Redis with TTL; pagination caps; tighten CORS; audit logging.

## Sequencing
P1 first (largest risk reduction, prerequisite for P2). P3 can run in parallel.
P4 is cleanup.
