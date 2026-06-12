// ============================================================
// Quoryx Matching Engine — Greedy Assignment
// Deduplicates matches so each transaction appears in at most
// one match. Highest-confidence match always wins.
// ============================================================

import { MatchCandidate, Transaction } from '../data/types';

/**
 * Greedy assignment — prevents the same transaction from appearing
 * in multiple matches. Candidates are sorted by confidence (highest
 * first) and each transaction is claimed by the first match that
 * includes it. All remaining transactions are returned as unmatched.
 *
 * @param candidates - Scored candidate pairs (typically confidenceScore >= 0.45)
 * @param allTransactions - Every transaction in the dataset
 * @returns Deduplicated matches + unmatched orphan transactions
 */
export function greedyAssign(
    candidates: MatchCandidate[],
    allTransactions: Transaction[]
): { matches: MatchCandidate[]; unmatched: Transaction[] } {
    // 1. Sort descending by confidenceScore.
    //    Tiebreaker: earlier transactionA.date comes first.
    const sorted = [...candidates].sort((a, b) => {
        if (b.confidenceScore !== a.confidenceScore) {
            return b.confidenceScore - a.confidenceScore;
        }
        return a.transactionA.date.getTime() - b.transactionA.date.getTime();
    });

    // 2. Initialise matchedIds set
    const matchedIds = new Set<string>();

    // 3. Initialise kept matches
    const keptMatches: MatchCandidate[] = [];

    // 4. Iterate: skip if either transaction ID is already matched
    for (const candidate of sorted) {
        if (matchedIds.has(candidate.transactionA.id)) continue;
        if (matchedIds.has(candidate.transactionB.id)) continue;

        keptMatches.push(candidate);
        matchedIds.add(candidate.transactionA.id);
        matchedIds.add(candidate.transactionB.id);
    }

    // 5. Build unmatched: all transactions not in matchedIds
    const unmatched = allTransactions.filter(tx => !matchedIds.has(tx.id));

    // 6. Return
    return { matches: keptMatches, unmatched };
}
