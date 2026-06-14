# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Quoryx intercompany matching engine. Standalone TypeScript module that identifies and scores transaction pairs across entities that share common ownership (e.g. a holding company and its subsidiaries). The `app/` directory is a separate Python/FastAPI backend for Xero/QuickBooks OAuth and transaction ingestion — it is scaffolding around the engine, not the core.

## Commands

### TypeScript matching engine

```bash
# Run all tests
npx jest

# Run a single test file
npx jest tests/scorer.test.ts

# Run the live integration pipeline (reads from Supabase, writes back via Railway)
npx ts-node scripts/run-integration.ts

# Run the test invoice script
npx ts-node scripts/test-invoice.ts

# Type check
npx tsc --noEmit
```

### Python FastAPI backend

```bash
# Create and activate virtualenv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run migrations (production)
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
# API docs: http://localhost:8000/docs  (prefixed /api/v1)

# Bootstrap DB tables for dev (one-off, no alembic)
python -c "from app.models.database import engine; from app.models import transaction; transaction.Base.metadata.create_all(bind=engine)"
```

### Environment

Copy `.env.example` → `.env`. Required keys: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `ANTHROPIC_API_KEY` (for LLM fallback), `APP_SECRET_KEY`, `DATABASE_URL`, `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, `QB_CLIENT_ID`, `QB_CLIENT_SECRET`.

## Architecture

### Matching engine pipeline (`matching/engine.ts` → `runMatchingEngine`)

```
detectIntercompany()     ← tags transactions isIntercompany = true
         ↓
scoreCandidate()         ← 4-dimension scoring per cross-entity pair
         ↓
evaluateWithLLM()        ← Claude fallback for confidenceScore 0.45–0.60
         ↓
greedyAssign()           ← deduplication — each transaction appears in at most one match
         ↓
MatchResult + stats
```

All files under `matching/` and `data/` are internal. The only public exports are `runMatchingEngine`, `normalizeTransaction`, and the types from `data/types.ts`.

### Scoring dimensions (`matching/scorer.ts`)

| Dimension | Max | Key rule |
|---|---|---|
| Amount | 0.40 | Cross-currency → 0.00; > 2% diff → 0.00 |
| Date | 0.30 | > 30 days apart → 0.00 |
| Type | 0.20 | `invoice ↔ bill` only; same-direction → 0.00 |
| Counterparty | 0.10 | ContactMapping > exact > substring > fuzzy ≥ 0.80 |

Confidence tiers: `≥ 0.95` auto-matched, `0.85–0.94` one-click approve, `0.60–0.84` review queue, `0.45–0.59` LLM fallback, `< 0.45` dismissed.

### Data layer

- `data/types.ts` — single source of truth for all interfaces (`Transaction`, `MatchCandidate`, `MatchResult`, `ContactMapping`, `LLMEvaluation`). Never redefine types inline.
- `data/normalizer.ts` — converts raw Xero API responses to `Transaction`.
- `data/db-adapter.ts` — read-only Supabase client. Fetches `intercompany_transactions` (unmatched pairs) and `transactions` rows. **No writes** — all writes go through the Railway PATCH endpoint (`/api/reconciliation/pairs/:id/status`).
- `data/db-normalizer.ts` — converts `RawTransaction` (Supabase columns) to `Transaction`. Maps `receive`→`invoice`, `spend`→`bill`.

### Integration script (`scripts/run-integration.ts`)

Calls `POST /api/reconciliation/run` on Railway to trigger detection, fetches unmatched pairs from Supabase, runs the engine, then PATCHes results back. This is the entry point for production runs. Requires all env vars set.

### LLM fallback (`matching/llm-matcher.ts`)

Uses `claude-sonnet-4-20250514`, max 500 tokens. Caches per pair using `[txA.id, txB.id].sort().join('::')` as key — same pair is never evaluated twice per run. Failed/unparseable responses return `isMatch: false` (never throws). LLM matches are always routed to `review_required`, never auto-approved.

### Folder rules (from PRD)

Maximum directory depth is `Algo_Quoryx/subfolder/file.ts`. No subfolders within subfolders. No `index.ts` barrel files. Do not create api/, prisma schemas, or UI components here.

## Testing

Mock data for all scenarios is in `data/mock-data.ts`. Use `{ skipLLM: true }` in engine tests to avoid live API calls. Tests live in `tests/` and mirror the module they test (`scorer.test.ts`, `engine.test.ts`, `greedy.test.ts`, `detector.test.ts`).