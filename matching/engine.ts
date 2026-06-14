// ============================================================
// Quoryx Matching Engine — Engine Orchestrator
// Coordinates the full matching pipeline:
// filter → score → LLM → greedy → stats
// ============================================================

import {
    Transaction,
    EntityGroup,
    ContactMapping,
    MatchCandidate,
    MatchResult,
    MatchStats,
} from '../data/types';
import { scoreCandidate } from './scorer';
import { greedyAssign } from './greedy';
import { evaluateWithLLM, buildLLMCache } from './llm-matcher';

/**
 * Run the full matching pipeline on a set of transactions.
 *
 * Pipeline steps:
 * A. Filter intercompany transactions (pre-tagged)
 * B. Build entity pairs
 * C. Score all cross-pair combinations
 * D. LLM evaluation for ambiguous pairs (skippable)
 * E. Greedy assignment
 * F. Compute stats
 * G. Return MatchResult
 *
 * @param transactions - All transactions to process
 * @param entityGroup - The entity group for this matching run
 * @param contactMappings - Confirmed counterparty mappings
 * @param options - Optional: { skipLLM: true } to skip LLM evaluation
 * @returns Complete match result with stats
 */
export async function runMatchingEngine(
    transactions: Transaction[],
    entityGroup: EntityGroup,
    contactMappings: ContactMapping[],
    options?: { skipLLM?: boolean }
): Promise<MatchResult> {
    const startTime = Date.now();

    // --- Step A: Filter intercompany transactions ---
    const icTransactions = transactions.filter(tx => tx.isIntercompany === true);

    if (icTransactions.length === 0) {
        return {
            matches: [],
            unmatched: transactions,
            stats: {
                totalCandidates: 0,
                autoMatched: 0,
                reviewRequired: 0,
                llmAssisted: 0,
                crossCurrency: 0,
                runDurationMs: Date.now() - startTime,
            },
        };
    }

    // --- Step B: Build entity pairs ---
    const uniqueEntityIds = [...new Set(icTransactions.map(tx => tx.entityId))].sort();
    const entityPairs: [string, string][] = [];
    for (let i = 0; i < uniqueEntityIds.length; i++) {
        for (let j = i + 1; j < uniqueEntityIds.length; j++) {
            entityPairs.push([uniqueEntityIds[i]!, uniqueEntityIds[j]!]);
        }
    }

    // --- Step C: Score all cross-pair combinations ---
    let candidates: MatchCandidate[] = [];

    for (const [entityAId, entityBId] of entityPairs) {
        const txsA = icTransactions.filter(tx => tx.entityId === entityAId);
        const txsB = icTransactions.filter(tx => tx.entityId === entityBId);

        // Performance guard
        if (txsA.length > 500 || txsB.length > 500) {
            console.warn(
                `Large entity pair detected: ${entityAId} (${txsA.length} txs) × ${entityBId} (${txsB.length} txs). Consider pagination for production.`
            );
        }

        for (const txA of txsA) {
            for (const txB of txsB) {
                const candidate = scoreCandidate(txA, txB, contactMappings);
                if (candidate.confidenceScore >= 0.45) {
                    candidates.push(candidate);
                }
            }
        }
    }

    // --- Step D: LLM evaluation for ambiguous pairs ---
    if (!options?.skipLLM) {
        const cache = buildLLMCache();
        const kept: MatchCandidate[] = [];

        for (const candidate of candidates) {
            if (candidate.confidenceScore >= 0.45 && candidate.confidenceScore < 0.60) {
                const llmResult = await evaluateWithLLM(
                    candidate.transactionA,
                    candidate.transactionB,
                    cache
                );

                if (llmResult.isMatch) {
                    candidate.confidenceScore = llmResult.confidence;
                    candidate.matchType = 'llm_assisted';
                    candidate.llmReasoning = llmResult.reasoning;
                    kept.push(candidate);
                }
                // LLM says not a match → drop from candidates
            } else {
                kept.push(candidate);
            }
        }

        candidates = kept;
    }

    // --- Step E: Greedy assignment ---
    // Pass ALL transactions (not just IC) so unmatched includes everything
    const { matches, unmatched } = greedyAssign(candidates, transactions);

    // --- Step F: Compute stats ---
    const stats: MatchStats = {
        totalCandidates: candidates.length,
        autoMatched: matches.filter(m => m.confidenceScore >= 0.95).length,
        reviewRequired: matches.filter(m => m.confidenceScore >= 0.60 && m.confidenceScore < 0.95).length,
        llmAssisted: matches.filter(m => m.matchType === 'llm_assisted').length,
        crossCurrency: candidates.filter(c => c.isCrossCurrency).length,
        runDurationMs: Date.now() - startTime,
    };

    // --- Step G: Return ---
    return { matches, unmatched, stats };
}
