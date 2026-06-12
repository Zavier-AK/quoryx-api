# QUORYX — Intercompany Matching Engine
## Product Requirements Document — v1.1
**Matching Algorithm Scope Only | February 2026 | For use with Claude Code / Cursor IDE**

---

> **HOW TO USE:** This document is written to be used directly as a prompt in Claude Code or Cursor IDE. Read every section before writing any code. Follow the folder guide exactly — do not create subfolders or files not listed here.

---

## Table of Contents

1. [Business Context](#1-business-context)
2. [Folder Structure](#2-folder-structure--follow-exactly)
3. [Data Types](#3-data-types-datatypests)
4. [Intercompany Detection](#4-intercompany-detection-matchingdetectorts)
5. [Scoring Engine](#5-scoring-engine-matchingscorersts)
6. [Greedy Assignment](#6-greedy-assignment-matchinggreedyts)
7. [LLM Fallback](#7-llm-fallback-matchingllm-matcherts)
8. [Engine Orchestrator](#8-engine-orchestrator-matchingenginets)
9. [Data Normalizer](#9-data-normalizer-datanormalizerts)
10. [Utilities](#10-utilities)
11. [Mock Data](#11-mock-data-datamock-datats)
12. [Testing Requirements](#12-testing-requirements)
13. [Build Sequence](#13-build-sequence)
14. [Success Criteria](#14-success-criteria)

---

## 1. Business Context

Quoryx builds intercompany financial management technology for SMB business groups. The platform automates reconciliation, consolidation, and reporting across Xero and QuickBooks entities — transforming manual month-end processes into seamless, audit-ready workflows.

**The problem we solve:** in any group of companies (e.g. a holding company with 3–10 subsidiaries), the same transaction appears twice — once as a sale in Company A, once as a purchase in Company B. Accountants manually trace every one of these pairs at month-end to eliminate them before producing group financial statements. For a group with 50+ intercompany transactions a month, this takes days. Quoryx reduces it to minutes.

### Our customers
- SMB business groups: 2–15 legal entities under common ownership
- Accountants and bookkeepers managing the month-end close for these groups
- Group CFOs who need consolidated financial visibility without enterprise-grade ERP costs

### Why this is hard
- Transaction descriptions are inconsistent across entities — Entity A calls it "Management fee Jan" while Entity B calls it "Consulting services Q1"
- Timing differences — Entity A invoices on the 28th, Entity B records the bill on the 3rd of the following month
- Amount differences — FX rounding, withholding tax, partial payments
- No shared reference system between entities — they operate in separate Xero accounts with no linked IDs

**The Matching Engine is Quoryx's core IP. It is the reason customers pay us. Everything else — the UI, the reporting, the integrations — is scaffolding around this engine.**

> **SCOPE NOTE:** This PRD covers the Matching Algorithm only. Xero/QuickBooks integration, user auth, dashboard UI, and journal posting are specified separately. Do not build those here.

---

## 2. Folder Structure — Follow Exactly

You are working inside the `Algo_Quoryx` folder. This folder contains the matching algorithm and its direct dependencies only. Do not create any folders or files not listed below. If you think you need a new file, check this guide first.

> **STRICT RULE:** Do not create subfolders within subfolders. Maximum depth is `Algo_Quoryx / subfolder / file.ts`. No deeper nesting. No `index.ts` barrel files unless explicitly listed.

### Top-level structure

```
Algo_Quoryx/
├── instructions/          ← This PRD and any reference docs live here
├── matching/              ← Core algorithm logic
├── data/                  ← Data normalization and schema types
├── utils/                 ← Shared utilities (string similarity, etc.)
├── tests/                 ← All test files
└── README.md              ← Quick start for any new developer
```

### Full file list — create only these files

| File path | Purpose |
|---|---|
| `instructions/PRD.md` | This document |
| `matching/engine.ts` | Core orchestrator — runs full matching pipeline |
| `matching/scorer.ts` | 4-dimension scoring logic for a candidate pair |
| `matching/greedy.ts` | Greedy assignment — deduplicates final match list |
| `matching/llm-matcher.ts` | Claude fallback for ambiguous pairs (0.45–0.60) |
| `matching/detector.ts` | Intercompany detection — flags transactions before matching |
| `data/types.ts` | All TypeScript interfaces and types used across the algo |
| `data/normalizer.ts` | Converts raw Xero/QB transaction to internal Transaction type |
| `data/mock-data.ts` | Realistic mock transactions for testing without live API |
| `utils/string-similarity.ts` | Levenshtein distance — no external dependency |
| `utils/currency.ts` | Currency helpers — flag cross-currency pairs (Phase 2 stub) |
| `tests/scorer.test.ts` | Unit tests for all 4 scoring dimensions |
| `tests/engine.test.ts` | Integration tests for full pipeline |
| `tests/greedy.test.ts` | Tests for greedy assignment correctness |
| `README.md` | Setup, run instructions, how the algorithm works |

> **DO NOT CREATE:** api/ routes, app/ directories, database/ folders, prisma schemas, UI components, or any server-side infrastructure. Those belong in the main application repo, not here.

### How this folder connects to the main app

When the main Quoryx application needs matching, it will import from this folder. The engine exports a single clean public API. Everything internal stays internal.

```typescript
// The only public exports from this module:
export { runMatchingEngine } from './matching/engine'
export { normalizeTransaction } from './data/normalizer'
export type { Transaction, MatchCandidate, MatchResult } from './data/types'
```

---

## 3. Data Types (`data/types.ts`)

Define all types here first before writing any logic. Every other file imports from this file. Never redefine types inline.

### Transaction — internal normalized type

| Field | Type + Notes |
|---|---|
| `id` | `string` — internal Quoryx ID |
| `entityId` | `string` — which entity this belongs to |
| `entityName` | `string` — human-readable entity name |
| `entityGroupId` | `string` — the group these entities belong to |
| `sourceSystem` | `'xero' \| 'quickbooks'` |
| `sourceId` | `string` — ID in the source system (e.g. Xero InvoiceID) |
| `sourceType` | `'invoice' \| 'bill' \| 'journal'` |
| `date` | `Date` — normalized to UTC |
| `amount` | `number` — always positive, Decimal precision |
| `currency` | `string` — ISO 4217 (USD, GBP, AUD) |
| `description` | `string` — free text reference |
| `reference` | `string` — invoice/bill number |
| `contactName` | `string` — counterparty name from source system |
| `contactId` | `string` — counterparty ID in source system |
| `isIntercompany` | `boolean` — computed by detector.ts |
| `rawData` | `Record<string, unknown>` — original API response |

### MatchCandidate — output of `scorer.ts`

| Field | Type + Notes |
|---|---|
| `transactionA` | `Transaction` |
| `transactionB` | `Transaction` |
| `amountScore` | `number` — 0 to 0.40 |
| `dateScore` | `number` — 0 to 0.30 |
| `typeScore` | `number` — 0 to 0.20 |
| `counterpartyScore` | `number` — 0 to 0.10 |
| `confidenceScore` | `number` — sum of all scores, 0.0 to 1.0 |
| `matchType` | `'exact' \| 'fuzzy' \| 'llm_assisted'` |
| `amountDifference` | `number` — absolute difference in same currency |
| `daysDifference` | `number` — absolute days between dates |
| `reasons` | `string[]` — human-readable explanation of each score |
| `isCrossCurrency` | `boolean` — true if currencies differ |
| `llmReasoning` | `string \| null` — set after LLM evaluation |

### MatchResult — final output of `engine.ts`

| Field | Type + Notes |
|---|---|
| `matches` | `MatchCandidate[]` — deduplicated by greedy assignment |
| `unmatched` | `Transaction[]` — no counterpart found |
| `stats.totalCandidates` | `number` — before deduplication |
| `stats.autoMatched` | `number` — confidence >= 0.95 |
| `stats.reviewRequired` | `number` — confidence 0.60–0.94 |
| `stats.llmAssisted` | `number` — evaluated by Claude |
| `stats.crossCurrency` | `number` — flagged, needs manual review |
| `stats.runDurationMs` | `number` — performance tracking |

### ContactMapping — learned counterparty relationships

| Field | Type + Notes |
|---|---|
| `contactId` | `string` — source system contact ID |
| `contactExternalName` | `string` — name in source system |
| `mapsToEntityId` | `string` — confirmed Quoryx entity |
| `sourceSystem` | `'xero' \| 'quickbooks'` |
| `confirmedBy` | `string` — userId |
| `confirmedAt` | `Date` |

---

## 4. Intercompany Detection (`matching/detector.ts`)

Runs before the matching engine. Takes a list of transactions for an entity group and sets `isIntercompany = true` on any transaction that is likely to involve another entity in the same group.

This is not matching — it is filtering. It narrows the dataset so the engine only scores relevant pairs.

### Detection logic — run in strict priority order

1. **ContactMapping lookup** — check if `contactId` has a confirmed mapping to any entity in this group. If yes, `isIntercompany = true` immediately. Do not run further checks.
2. **Exact name match** — check if `contactName` exactly equals (case-insensitive, trimmed) any entity name in the group.
3. **Substring match** — check if `contactName` contains or is contained by any entity name (case-insensitive).
4. **Fuzzy match** — Levenshtein similarity >= 0.80 between `contactName` and any entity name in the group.

> **IMPORTANT:** Priority order matters. ContactMapping is permanent and confirmed by a human — always trust it over any computed match. Once a ContactMapping exists, skip all other checks for that `contactId`.

### Function signature

```typescript
detectIntercompany(
  transactions: Transaction[],
  entityGroup: { id: string; entities: { id: string; name: string }[] },
  contactMappings: ContactMapping[]
): Transaction[]   // returns transactions with isIntercompany set correctly
```

---

## 5. Scoring Engine (`matching/scorer.ts`)

Takes two transactions and returns a `MatchCandidate` with scores for all 4 dimensions. **This is a pure function — no side effects, no DB calls, no API calls.**

### Scoring model overview

| Dimension | Weight | Max Score | What it measures |
|---|---|---|---|
| Amount | 40% | 0.40 | Transaction value alignment |
| Date | 30% | 0.30 | Timing proximity |
| Transaction Type | 20% | 0.20 | Invoice/bill directionality |
| Counterparty | 10% | 0.10 | Contact name similarity |

### Dimension 1: Amount (max 0.40)

Same currency only for MVP. If currencies differ, set `amountScore = 0.00` and `isCrossCurrency = true`. Do not attempt FX conversion — that is Phase 2.

| Tolerance | Score |
|---|---|
| Exact match (0% difference) | 0.40 |
| ≤ 0.5% difference | 0.38 |
| ≤ 1.0% difference | 0.35 |
| ≤ 2.0% difference | 0.30 |
| > 2.0% difference | 0.00 |
| Cross-currency pair | 0.00 — set `isCrossCurrency = true` |

Calculate difference as: `Math.abs(amountA - amountB) / amountA * 100`. Store the raw absolute difference (not percent) in `amountDifference` for display.

### Dimension 2: Date (max 0.30)

30-day tolerance is intentional — SMBs routinely have timing differences at month-end. Never reduce this threshold without customer data to justify it.

| Days apart | Score |
|---|---|
| 0 days (same day) | 0.30 |
| 1–7 days | 0.28 |
| 8–14 days | 0.25 |
| 15–30 days | 0.20 |
| > 30 days | 0.00 |

### Dimension 3: Transaction Type (max 0.20)

Invoice/bill pairing is the canonical intercompany case. Entity A raises an invoice (AR), Entity B records the corresponding bill (AP). Same-direction pairs score zero.

| Pair | Score |
|---|---|
| `invoice ↔ bill` (either order) | 0.20 |
| `journal ↔ journal` | 0.15 |
| `invoice ↔ invoice` | 0.00 — same direction |
| `bill ↔ bill` | 0.00 — same direction |
| Any other combination | 0.00 |

### Dimension 4: Counterparty (max 0.10)

Use ContactMappings first (confirmed by human), then fall back to name matching. Import string similarity from `utils/string-similarity.ts`.

| Match quality | Score |
|---|---|
| Confirmed ContactMapping match | 0.10 |
| Exact name match (case-insensitive) | 0.10 |
| Substring containment match | 0.09 |
| Levenshtein similarity >= 0.80 | 0.08 |
| No match found | 0.00 |

### Match classification — set `matchType` based on final `confidenceScore`

| Confidence | matchType | status | Routing |
|---|---|---|---|
| ≥ 0.95 | `exact` | `auto_matched` | Summary view only |
| 0.85 – 0.94 | `fuzzy` | `matched` | One-click approve queue |
| 0.60 – 0.84 | `fuzzy` | `review_required` | Full review queue |
| 0.45 – 0.59 | `llm_assisted` | `review_required` | LLM evaluates → review queue |
| < 0.45 | — | `dismissed` | Not surfaced to user |

### Function signature

```typescript
scoreCandidate(
  txA: Transaction,
  txB: Transaction,
  contactMappings: ContactMapping[]
): MatchCandidate
```

This must be a pure function. No async. No I/O. Takes two transactions, returns a scored candidate. Test this in isolation.

---

## 6. Greedy Assignment (`matching/greedy.ts`)

Prevents the same transaction from appearing in multiple matches. Without this, one invoice could match three different bills. The highest-confidence match always wins.

> **CRITICAL:** This is the most commonly missed implementation detail in matching engines. Do not skip it. A transaction can only appear in one match. Ever.

### Algorithm — implement exactly as described

1. Input: `MatchCandidate[]` from scorer, all pairs with `confidenceScore >= 0.45`
2. Sort candidates **descending** by `confidenceScore` (highest first)
3. Initialize an empty `Set<string>` called `matchedIds`
4. Iterate through sorted candidates:
   - If `transactionA.id` is in `matchedIds` → skip this candidate
   - If `transactionB.id` is in `matchedIds` → skip this candidate
   - Otherwise → keep this match, add both IDs to `matchedIds`
5. Return: kept matches + all transactions whose IDs are not in `matchedIds` (these are "unmatched orphans")

### Function signature

```typescript
greedyAssign(
  candidates: MatchCandidate[],
  allTransactions: Transaction[]
): { matches: MatchCandidate[]; unmatched: Transaction[] }
```

### Edge cases to handle

- Two candidates with identical `confidenceScore` — use date (earlier transaction first) as tiebreaker
- A transaction that appears as `txA` in one candidate and `txB` in another — same rule applies, first match in sorted order wins
- An entity group with only one entity — no pairs possible, return all as unmatched

---

## 7. LLM Fallback (`matching/llm-matcher.ts`)

For pairs where the rules-based scorer returns confidence between 0.45 and 0.60, Claude acts as an expert accountant and evaluates whether the two transactions are the same intercompany event viewed from both sides.

### When to call
- `confidenceScore >= 0.45` AND `confidenceScore < 0.60` — rules are uncertain
- `isCrossCurrency = true` — amount dimension scored 0, Claude can reason about likely FX equivalence

### When NOT to call
- `confidenceScore >= 0.60` — rules are confident enough
- `confidenceScore < 0.45` — too far apart, not worth the API call
- Candidate pair has been evaluated before — check cache first

### Caching requirement

Cache all LLM responses in a `Map<string, LLMEvaluation>` keyed by a deterministic pair ID:

```typescript
const pairId = [txA.id, txB.id].sort().join('::')
```

Never call the LLM twice for the same pair within a session.

### Model and prompt
- Model: `claude-sonnet-4-20250514`
- Max tokens: `500`
- Temperature: default (do not set)
- Response format: JSON only — no markdown fences, no preamble

### What to include in every prompt
Both entity names, both transaction types, both dates, both amounts with currencies, both descriptions, both reference numbers, both contact names. Ask Claude to respond as a chartered accountant reviewing intercompany transactions for a group close.

> **PROMPT RULE:** Always end the prompt with: `"Respond with ONLY a JSON object. No markdown. No explanation outside the JSON."` This prevents malformed responses.

### Required JSON response schema

```json
{
  "isMatch": true,
  "confidence": 0.72,
  "reasoning": "Both transactions relate to a management fee for January. The 3-day date difference and matching amounts strongly suggest these are the same intercompany charge recorded on different dates."
}
```

### Function signature

```typescript
evaluateWithLLM(
  txA: Transaction,
  txB: Transaction,
  cache: Map<string, LLMEvaluation>
): Promise<LLMEvaluation>
```

If `isMatch = true`, update the `MatchCandidate`'s `confidenceScore` to the LLM confidence value, set `matchType = 'llm_assisted'`, and set `llmReasoning` to the reasoning string. **Always route to `review_required` — never auto-approve an LLM match.**

---

## 8. Engine Orchestrator (`matching/engine.ts`)

Coordinates the full pipeline. This is the only file the rest of the application needs to import from. All other matching files are internal.

### Pipeline steps — in order

1. Receive input: `transactions[]`, `entityGroup`, `contactMappings[]`
2. Run `detectIntercompany` → tag all transactions
3. Filter to `isIntercompany = true` only
4. Build all entity pairs in the group
5. For each entity pair, run `scoreCandidate` on all cross-pair combinations
6. Collect all candidates with `confidenceScore >= 0.45`
7. For candidates with `confidenceScore` between 0.45 and 0.60 → run `evaluateWithLLM`
8. Run `greedyAssign` on all candidates
9. Compute stats (counts by tier, run duration, cross-currency count)
10. Return `MatchResult`

### Function signature

```typescript
runMatchingEngine(
  transactions: Transaction[],
  entityGroup: { id: string; entities: { id: string; name: string }[] },
  contactMappings: ContactMapping[],
  options?: { skipLLM?: boolean }   // for testing without API calls
): Promise<MatchResult>
```

> **PERFORMANCE NOTE:** For groups with many transactions, the O(n²) pair comparison can get slow. For MVP this is acceptable. If an entity pair has >500 transactions, log a warning but do not fail.

---

## 9. Data Normalizer (`data/normalizer.ts`)

Converts raw Xero or QuickBooks API responses into the internal `Transaction` type. This is the only file that knows about external API shapes. Everything else works with the internal `Transaction` type only.

### Function signatures

```typescript
normalizeXeroInvoice(raw: XeroInvoice, entityId: string, entityGroupId: string): Transaction
normalizeXeroBill(raw: XeroInvoice, entityId: string, entityGroupId: string): Transaction
// QuickBooks normalizers come in Phase 2
```

### Normalization rules

- `date`: convert Xero date string `/Date(timestamp+offset)/` to JS Date, normalize to UTC
- `amount`: parse to number, always positive — bills are still positive (direction encoded in `sourceType`)
- `currency`: uppercase ISO code, default to `'USD'` if missing
- `description`: use `lineItems[0].description` if reference is empty
- `contactName`: trim whitespace, preserve original casing for display, lowercase only for matching operations
- `rawData`: store the complete original object for auditability

---

## 10. Utilities

### `utils/string-similarity.ts`

Implement Levenshtein distance from scratch. No external libraries. Export two functions:

```typescript
levenshteinDistance(str1: string, str2: string): number   // raw edit distance
stringSimilarity(str1: string, str2: string): number      // 0.0 to 1.0 similarity ratio
```

Normalize inputs before comparing: trim whitespace, lowercase, remove common legal suffixes (`Ltd`, `LLC`, `Inc`, `Corp`, `Limited`) to improve matching accuracy.

### `utils/currency.ts`

Phase 2 stub. For MVP, export one function:

```typescript
isCrossCurrency(currencyA: string, currencyB: string): boolean
```

When called with differing currencies, return `true` and log: `"Cross-currency pair detected — manual review required. FX conversion coming in Phase 2."`

---

## 11. Mock Data (`data/mock-data.ts`)

Realistic test transactions for development and testing without a live Xero connection. Must cover all edge cases the algorithm needs to handle.

### Required mock scenarios — build all of these

| Scenario | Description |
|---|---|
| Exact match pair | Invoice + Bill, same date, same amount, same currency |
| Date offset match | Invoice + Bill, 5 days apart, same amount |
| Amount tolerance match | Invoice $10,000 / Bill $10,050 (0.5% diff) |
| Fuzzy name match | "ABC Corp USA" invoice / "ABC Corp" bill |
| Cross-currency pair | Invoice USD $10,000 / Bill GBP £8,000 |
| Orphan invoice | Invoice with no corresponding bill in any entity |
| Same-direction pair | Two invoices — should score 0.00 on type dimension |
| LLM edge case | Different descriptions, same amount/date — ambiguous |
| High-volume group | 50+ transactions across 3 entities |
| ContactMapping match | Contact ID confirmed in mapping table |

Export all mock data as named arrays: `mockTransactions`, `mockEntityGroup`, `mockContactMappings`. Tests import from here.

---

## 12. Testing Requirements

Every function in the algorithm must have tests. No exceptions. Use mock data from `data/mock-data.ts` for all tests.

### `tests/scorer.test.ts` — required test cases

- Exact match: `confidenceScore >= 0.95`, `matchType = 'exact'`
- Amount tolerance: $10,000 vs $10,050 → `amountScore = 0.38`
- Date offset: 5 days apart → `dateScore = 0.28`
- Type mismatch: invoice vs invoice → `typeScore = 0.00`
- Counterparty fuzzy: "ABC Corp USA" vs "ABC Corp" → `counterpartyScore = 0.08`
- Cross-currency: `isCrossCurrency = true`, `amountScore = 0.00`
- Full score sum: all 4 dimensions present → total equals sum of parts

### `tests/greedy.test.ts` — required test cases

- One transaction cannot appear in two matches
- Highest confidence wins when two candidates share a transaction
- All unmatched transaction IDs returned in `unmatched` array
- Empty input returns empty matches and empty unmatched

### `tests/engine.test.ts` — required test cases

- Full pipeline with exact match pair → 1 match, 0 unmatched
- Full pipeline with orphan transaction → 0 matches, 1 unmatched
- Full pipeline with 3-entity group → correct entity pair matching
- `skipLLM` option disables LLM calls (candidates in LLM range returned as-is)
- Stats object has correct counts for each tier

---

## 13. Build Sequence

Follow this order. Do not jump ahead. Each step has a verification checkpoint.

### Step 1 — Types and mock data
1. Create `data/types.ts` with all interfaces
2. Create `data/mock-data.ts` with all required scenarios

**Checkpoint:** Import types in a scratch file, confirm TypeScript compiles with no errors.

### Step 2 — Utilities
1. Create `utils/string-similarity.ts` with `levenshteinDistance` and `stringSimilarity`
2. Create `utils/currency.ts` stub

**Checkpoint:** `stringSimilarity('ABC Corp USA', 'ABC Corp')` returns value > 0.80.

### Step 3 — Normalizer
1. Create `data/normalizer.ts`
2. Test against `rawData` from `mock-data.ts`

**Checkpoint:** `normalizeXeroInvoice(mockRawInvoice)` returns valid `Transaction` with all fields populated.

### Step 4 — Scorer
1. Create `matching/scorer.ts`
2. Write `tests/scorer.test.ts` immediately — before moving on

**Checkpoint:** All scorer tests pass. Run: `npx jest tests/scorer.test.ts`

### Step 5 — Greedy assignment
1. Create `matching/greedy.ts`
2. Write `tests/greedy.test.ts` immediately

**Checkpoint:** All greedy tests pass. Verify a transaction cannot appear in two matches.

### Step 6 — Detector
1. Create `matching/detector.ts`
2. Test against mock transactions with known intercompany relationships

**Checkpoint:** `detectIntercompany` correctly flags intercompany transactions using all 4 detection methods.

### Step 7 — LLM fallback
1. Create `matching/llm-matcher.ts`
2. Test with the LLM edge case from `mock-data.ts`
3. Verify caching: same pair called twice → only one API call made

**Checkpoint:** `evaluateWithLLM` returns valid `LLMEvaluation`, caching works correctly.

### Step 8 — Engine orchestrator
1. Create `matching/engine.ts` wiring all pieces together
2. Write `tests/engine.test.ts`

**Checkpoint:** `runMatchingEngine` with full mock dataset returns correct `MatchResult` with accurate stats.

### Step 9 — README
1. Write `README.md`: setup instructions, how to run tests, how the algorithm works in plain English, how to add a new scoring dimension

---

## 14. Success Criteria

| Metric | Target |
|---|---|
| Auto-match rate | >= 70% of intercompany pairs matched automatically |
| False positive rate | < 5% incorrect matches in `matched` status |
| Test coverage | All functions in `matching/` and `data/` have passing tests |
| TypeScript | Zero type errors — strict mode enabled |
| LLM cache hit rate | Same pair never evaluated twice |
| Performance | 500 transaction group completes in < 10 seconds |
| Orphan detection | All transactions with no counterpart appear in `unmatched[]` |

---

> **FINAL NOTE:** The Quoryx matching engine is the reason customers pay us. When in doubt, favour accuracy over speed. A false positive (wrong match shown as correct) destroys trust faster than a missed match. If confidence is borderline, route to review — never auto-approve.

---

*Quoryx — Internal Engineering Document | Matching Algorithm Only | v1.1 | February 2026*
