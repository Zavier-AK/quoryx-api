// ============================================================
// Quoryx Matching Engine — Type Definitions
// All TypeScript interfaces and types used across the algorithm.
// Every other file imports from this file. Never redefine types inline.
// ============================================================

// --- Type Aliases ---

export type SourceSystem = 'xero' | 'quickbooks';
export type SourceType = 'invoice' | 'bill' | 'journal';
export type MatchType = 'exact' | 'fuzzy' | 'llm_assisted';

// --- Core Interfaces ---

/**
 * Internal normalized transaction type.
 * All matching operations work with this shape — never raw API responses.
 */
export interface Transaction {
  /** Internal Quoryx ID */
  id: string;
  /** Which entity this belongs to */
  entityId: string;
  /** Human-readable entity name */
  entityName: string;
  /** The group these entities belong to */
  entityGroupId: string;
  /** Source accounting system */
  sourceSystem: SourceSystem;
  /** ID in the source system (e.g. Xero InvoiceID) */
  sourceId: string;
  /** Transaction direction / type */
  sourceType: SourceType;
  /** Normalized to UTC */
  date: Date;
  /** Always positive, decimal precision */
  amount: number;
  /** ISO 4217 currency code (USD, GBP, AUD) */
  currency: string;
  /** Free text reference / description */
  description: string;
  /** Invoice/bill number */
  reference: string;
  /** Counterparty name from source system */
  contactName: string;
  /** Counterparty ID in source system */
  contactId: string;
  /** Computed by detector.ts */
  isIntercompany: boolean;
  /** Original API response for auditability */
  rawData: Record<string, unknown>;
}

/**
 * Output of scorer.ts — a scored candidate pair.
 */
export interface MatchCandidate {
  transactionA: Transaction;
  transactionB: Transaction;
  /** Amount dimension score: 0 to 0.40 */
  amountScore: number;
  /** Date dimension score: 0 to 0.30 */
  dateScore: number;
  /** Transaction type dimension score: 0 to 0.20 */
  typeScore: number;
  /** Counterparty dimension score: 0 to 0.10 */
  counterpartyScore: number;
  /** Sum of all dimension scores: 0.0 to 1.0 */
  confidenceScore: number;
  /** Classification based on confidence */
  matchType: MatchType;
  /** Absolute difference in same currency */
  amountDifference: number;
  /** Absolute days between dates */
  daysDifference: number;
  /** Human-readable explanation of each score */
  reasons: string[];
  /** True if currencies differ */
  isCrossCurrency: boolean;
  /** Set after LLM evaluation, null otherwise */
  llmReasoning: string | null;
}

/**
 * Final output of engine.ts — the complete match result.
 */
export interface MatchResult {
  /** Deduplicated matches from greedy assignment */
  matches: MatchCandidate[];
  /** Transactions with no counterpart found */
  unmatched: Transaction[];
  /** Aggregate statistics for the matching run */
  stats: MatchStats;
}

/**
 * Aggregate statistics for a matching run.
 */
export interface MatchStats {
  /** Total candidates before deduplication */
  totalCandidates: number;
  /** Confidence >= 0.95 — auto-approved */
  autoMatched: number;
  /** Confidence 0.60–0.94 — needs user review */
  reviewRequired: number;
  /** Evaluated by Claude LLM */
  llmAssisted: number;
  /** Flagged cross-currency, needs manual review */
  crossCurrency: number;
  /** Performance tracking in milliseconds */
  runDurationMs: number;
}

/**
 * Learned counterparty relationships — confirmed by a human.
 * ContactMappings are always trusted over computed matches.
 */
export interface ContactMapping {
  /** Source system contact ID */
  contactId: string;
  /** Name in source system */
  contactExternalName: string;
  /** Confirmed Quoryx entity this contact maps to */
  mapsToEntityId: string;
  /** Source accounting system */
  sourceSystem: SourceSystem;
  /** User who confirmed this mapping */
  confirmedBy: string;
  /** When the mapping was confirmed */
  confirmedAt: Date;
}

/**
 * Claude LLM evaluation response schema.
 */
export interface LLMEvaluation {
  /** Whether the LLM considers this a match */
  isMatch: boolean;
  /** LLM confidence: 0.0 to 1.0 */
  confidence: number;
  /** Human-readable reasoning from the LLM */
  reasoning: string;
}

/**
 * Entity group structure used across the algorithm.
 */
export interface EntityGroup {
  id: string;
  entities: Entity[];
}

/**
 * Individual entity within a group.
 */
export interface Entity {
  id: string;
  name: string;
}
