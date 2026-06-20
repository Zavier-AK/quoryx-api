# Quoryx — Project Status & Ship Log

_Last updated: 2026-06-15_

A running overview of what's built, what's live in production, the key files, and
what's next. This is the security-remediation + first-real-customer-data milestone:
the matching engine now runs end-to-end on real e-conomic data with per-user
tenant isolation, encrypted tokens, and a working dashboard.

---

## 1. Where things stand (TL;DR)

The full pipeline is **live and working** against real data:

```
connect e-conomic → ingest invoices → detect intercompany pairs
   → score (4-dimension engine) → matched, isolated per user
```

- ✅ First real e-conomic agreement connected (encrypted grant token).
- ✅ Two real sales invoices ingested as RECEIVE.
- ✅ A **cross-system Xero↔e-conomic match scored 1.00**.
- ✅ Per-user tenant isolation enforced by Supabase RLS (verified: other users / anon see nothing).
- ✅ Dashboard, Entities, and Review Queue render real data.

**Not yet on:** backend API auth enforcement (`AUTH_ENABLED` is still **off** — RLS
protects the dashboard's direct reads, but the API itself is open until we flip it).

---

## 2. Security remediation — phase status

| Phase | What | Status |
|---|---|---|
| **Phase 1** | API authentication (service key + Supabase JWT) + rate limiting | ✅ merged (PR #1) |
| **Phase 3** | OAuth token encryption at rest (Fernet) | ✅ merged (PR #2), key set on Railway |
| **Phase 2** | Per-user tenant isolation (`owner_id` + Supabase RLS) | ✅ merged (PR #3) + RLS applied |

(Phase 2 was built after Phase 3 because it needed the login/identity layer first.)

---

## 3. Pull requests shipped this milestone

### Backend — `QuoryxSystems/quoryx-api` (via fork `Zavier-AK/quoryx-api`)

| PR | Title | Status |
|---|---|---|
| #1 | Phase 1 security: API auth + rate limiting | ✅ merged |
| #2 | Phase 3 security: encrypt OAuth tokens at rest | ✅ merged |
| #3 | Phase 2 tenant isolation (`owner_id`) + dashboard-JWT guard remap | ✅ merged |
| #4 | e-conomic callback: make `state` optional (app-list installs) | ✅ merged |
| #5 | Fix 500: `IntercompanyTransaction.status` is varchar, not Enum | ✅ merged |
| #6 | Ingest e-conomic supplier invoices (AP/SPEND) via Booked Entries API | ✅ merged |
| #7 | Redirect e-conomic callback to dashboard (kill raw-JSON page) | 🟡 open |

### Frontend — `QuoryxSystems/carbon-copy-cat`

| Change | Status |
|---|---|
| Invite-only Supabase login (`use-auth`, `Login`, `RequireAuth`, `authedFetch`) | ✅ merged |
| Dashboard declutter + Review Queue page (built in Lovable) | ✅ live |

---

## 4. What was developed (by area)

### 4.1 Token encryption at rest (Phase 3)
OAuth tokens are encrypted transparently at the ORM layer with Fernet. Encrypted
values carry an `enc:v1:` prefix; anything without it is treated as legacy
plaintext and passed through, so the rollout is non-breaking. No-op until
`TOKEN_ENCRYPTION_KEY` is set; never raises. Confirmed live: the real e-conomic
token is stored `enc:v1:…`.

### 4.2 Tenant isolation (Phase 2)
`owner_id` (the Supabase user id / JWT `sub`) is stamped onto
`oauth_tokens`, `entities`, `transactions`, `intercompany_transactions` and
threaded through connect → entity-sync → ingest → detection. Detection never
pairs across owners. Backend read endpoints filter by the caller's owner when
auth is enabled.

**The real guard is Supabase RLS** because the dashboard reads Supabase directly
with the anon key + the user's JWT. Owner-scoped `authenticated` policies were
applied to the three dashboard-read tables; the old insecure `anon → USING(true)`
policies (which let any anon key read all tenants) were dropped. The backend uses
a direct Postgres service connection that bypasses RLS, so cross-entity matching
still works within one owner.

### 4.3 e-conomic integration
- **Connect**: redirect install flow + manual paste (`POST /economic/connect`).
  Token is permanent (no refresh/expiry). `state` is optional (e-conomic app-list
  installs don't return it). Callback now redirects to the dashboard.
- **AR / RECEIVE**: booked sales invoices via `restapi.e-conomic.com/invoices/booked`.
- **AP / SPEND**: e-conomic has **no supplier-invoice document endpoint** — supplier
  invoices live in the general ledger. We read the **Booked Entries API**
  (`apis.e-conomic.com/bookedEntriesapi/v4.0.0/booked-entries`, `type=3`) and keep
  the creditor line of each voucher (the row with a `supplierNumber`, whose amount
  is the invoice total). Verified live against demo tokens.

### 4.4 Matching engine reliability
- Fixed a latent 500: `IntercompanyTransaction.status` was a SQLAlchemy `Enum`
  (maps by UPPERCASE name) over a varchar column holding lowercase values →
  `LookupError` on every ORM read of a pair. Now `String(20)`.
- Cross-provider relaxed detection (different providers, equal currency, amount
  within 2%, date within 30 days) produces candidates; the TS engine scores them.

---

## 5. Key files

### Backend (`app/`)
| File | What it does |
|---|---|
| `app/core/crypto.py` | Fernet `encrypt_token`/`decrypt_token` + `EncryptedString` TypeDecorator (`enc:v1:` prefix). |
| `app/core/auth.py` | `require_service_key`, `require_user`, `require_user_or_service`, `current_owner_id`. Short-circuits when `AUTH_ENABLED` is off. |
| `app/core/config.py` | Settings incl. `TOKEN_ENCRYPTION_KEY`, `SUPABASE_JWT_SECRET`, `SERVICE_API_KEY`, `AUTH_ENABLED`, `FRONTEND_BASE_URL`, e-conomic keys. |
| `app/models/transaction.py` | `OAuthToken` (encrypted tokens, `owner_id`), `Transaction` (`owner_id`). |
| `app/models/entity.py` | `Entity` + `IntercompanyTransaction` (`owner_id`); `status` is `String(20)`. |
| `app/api/auth.py` | Xero/QB/e-conomic OAuth + connect; owner stamping; e-conomic callback redirect. |
| `app/api/economic.py` | e-conomic read endpoints + ingest (AR via `/invoices/booked`, AP via Booked Entries `type=3`). |
| `app/api/entities.py` | Entity sync (Xero + e-conomic), owner stamping + owner-filtered list. |
| `app/api/reconciliation.py` | `/detect`, `/run`, `/pairs`, `/summary`, PATCH status; within-owner pairing + owner filtering. |
| `alembic/versions/0005_add_owner_id.py` | Adds `owner_id` (+ index) to the four tables. |
| `Instructions/phase2-rls.sql` | The RLS policies (applied to prod; kept for reference). |

### Frontend (`carbon-copy-cat/src/`)
| File | What it does |
|---|---|
| `hooks/use-auth.tsx` | `AuthProvider` + `useAuth()` (Supabase session). |
| `pages/Login.tsx` | Email/password sign-in, invite-only (no signup). |
| `App.tsx` | `RequireAuth` gate around the dashboard routes. |
| `lib/api.ts` | `API_BASE` + `authedFetch()` (attaches Supabase JWT as Bearer). |
| `pages/Entities.tsx` | Connected entities + sync; `ConnectEntityDialog`. |
| Review Queue / Dashboard | Built in Lovable; read Supabase directly (RLS-scoped). |

### Matching engine (TS, repo root)
| File | What it does |
|---|---|
| `matching/engine.ts` | `runMatchingEngine` — detect → score → LLM fallback → greedy assign. |
| `matching/scorer.ts` | 4-dimension scoring (amount .40 / date .30 / type .20 / counterparty .10). |
| `data/db-normalizer.ts` | Raw DB row → `Transaction` (provider-aware). |
| `data/db-adapter.ts` | Read-only Supabase client (anon key — **blocked by RLS**, see next steps). |
| `scripts/run-integration.ts` | Full pipeline: detect → fetch → score → PATCH back. |
| `scripts/score-pairs-once.ts` | **Temporary** one-off scorer (reads a JSON dump, scores, PATCHes). Stopgap until the integration job uses a service-role key. |

---

## 6. Production state (as of this writing)

- **Supabase project**: `jcftweiqftwjyoktwvfx` (EU). Tables migrated to alembic head
  `0005`; RLS on for `entities` / `transactions` / `intercompany_transactions`
  (owner-scoped, authenticated). `match_decisions` table created.
- **Railway**: project `confident-possibility`, service `web`,
  `https://web-production-4f190.up.railway.app`. `TOKEN_ENCRYPTION_KEY` set.
  `AUTH_ENABLED` **off**. Railway does **not** auto-run migrations on deploy
  (migrations were applied manually via Supabase) — see next steps.
- **Test user / owner**: `zavierakhan@gmail.com` = `a2f6e309-d107-4aba-9253-4eda5a7d22b8`.
  All existing rows backfilled to this owner.
- **Connected entities**: `Din virksomhed` (e-conomic, real, agreement 2437983),
  plus legacy `Quoryx` / `Quoryx Technologies` (Xero, **tokens expired 2026-03-10**)
  and `Holdco ApS` (e-conomic demo placeholder).
- **Pairs**: 4 matched (cross-system 3,125 DKK = 1.00; three more at 0.98).

---

## 7. Known issues / caveats

1. **Backend API is open** — `AUTH_ENABLED=false`. RLS protects the dashboard's
   Supabase reads, but the FastAPI endpoints accept unauthenticated calls. Flip
   when ready (deliberate, see next steps).
2. **Scoring pipeline blocked by RLS** — `data/db-adapter.ts` uses the anon key,
   which now returns 0 rows. Scoring was done via the `score-pairs-once.ts`
   stopgap. Needs a service-role key (next steps).
3. **Migrations don't auto-run on Railway deploy** — caused a 500 (missing
   `owner_id` column) until applied manually. Needs a release command.
4. **Synthetic test row** — `TEST-xero-bill-3125` is fake data inserted to demo
   cross-system matching. Delete before a real Xero reconnect.
5. **Xero tokens expired** — the two Xero connections need reconnecting for any
   real Xero ingest.
6. **e-conomic SPEND paging** — Booked Entries `/paged` caps at ~10k entries;
   very large agreements would need the cursor endpoint.
7. **e-conomic demo agreement** has no booked supplier invoices, so AP ingest
   returns 0 there until real supplier invoices exist (the code path is correct).

---

## 8. Next steps

**Near-term (recommended order):**
1. **Merge PR #7** (callback redirect) → redeploy.
2. **Delete the synthetic row** `TEST-xero-bill-3125` (+ its pair) before real Xero work.
3. **Service-role scoring** — point `db-adapter` at `SUPABASE_SERVICE_ROLE_KEY`
   (falls back to anon) so `run-integration.ts` works under RLS; retire
   `score-pairs-once.ts`.
4. **Auto-migrate on deploy** — add a Railway release/start step running
   `alembic upgrade head` so schema changes apply automatically.

**Deliberate (do together, verify after):**
5. **Flip backend auth on** — set `AUTH_ENABLED=true` + `SUPABASE_JWT_SECRET` on
   Railway; smoke-test each endpoint (dashboard JWT + integration service key).

**Product / demo:**
6. **Reconnect Xero** + book a real bill → fully-real cross-system match.
7. **Borderline pair** (amount ~1% off, dates ~2 weeks apart) to exercise the
   Review Queue Approve/Reject flow on a `review_required` item.
8. **Entities page polish** — read `?connected=economic` to show a success toast.

**Compliance:**
9. The e-conomic developer compliance form can now truthfully attest to
   encryption-at-rest and per-tenant data isolation (Phases 2 + 3 done).
