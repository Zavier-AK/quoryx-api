-- ============================================================================
-- Phase 2 — Supabase Row-Level Security (tenant isolation)
--
-- The dashboard reads these three tables DIRECTLY from Supabase using the anon
-- key + the logged-in user's JWT, so RLS is the real per-user guard. The backend
-- writes through a direct Postgres (service/owner) connection, which BYPASSES RLS
-- — that is intentional: matching must see every entity belonging to ONE owner.
--
-- owner_id is TEXT and holds the Supabase user id (auth.uid()). We cast auth.uid()
-- (uuid) to text to compare.
--
-- DO NOT run this blindly against prod. Run AFTER:
--   1) migration 0005 is applied (owner_id columns exist), and
--   2) existing rows are backfilled with the correct owner_id (or you accept that
--      legacy NULL-owner rows become invisible to user sessions — visible only to
--      the service connection).
--
-- Apply via Supabase MCP apply_migration or the SQL editor, reviewing each block.
-- ============================================================================

-- 1. entities -----------------------------------------------------------------
alter table public.entities enable row level security;

drop policy if exists "owner can read own entities" on public.entities;
create policy "owner can read own entities"
  on public.entities for select
  to authenticated
  using (owner_id = auth.uid()::text);

-- 2. transactions -------------------------------------------------------------
alter table public.transactions enable row level security;

drop policy if exists "owner can read own transactions" on public.transactions;
create policy "owner can read own transactions"
  on public.transactions for select
  to authenticated
  using (owner_id = auth.uid()::text);

-- 3. intercompany_transactions (the review queue) -----------------------------
alter table public.intercompany_transactions enable row level security;

drop policy if exists "owner can read own pairs" on public.intercompany_transactions;
create policy "owner can read own pairs"
  on public.intercompany_transactions for select
  to authenticated
  using (owner_id = auth.uid()::text);

-- Notes:
--  * No INSERT/UPDATE/DELETE policies are created → anon/authenticated sessions
--    cannot write these tables at all. All writes go through the backend service
--    connection (which bypasses RLS). If the dashboard later needs to write
--    directly, add narrowly-scoped policies with the same owner_id check.
--  * oauth_tokens is NEVER read by the frontend and is omitted here on purpose —
--    leave RLS as-is (or enable with NO policies to hard-deny anon access).
