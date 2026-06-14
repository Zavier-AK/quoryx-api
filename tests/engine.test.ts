// ============================================================
// Quoryx Matching Engine — Engine Orchestrator Tests
// All tests use skipLLM: true — no real API calls.
// ============================================================

import { runMatchingEngine } from '../matching/engine';
import {
    mockScenarios,
    mockContactMappings,
    mockEntityGroup,
} from '../data/mock-data';
import { Transaction } from '../data/types';

/** Helper: clone a transaction with isIntercompany = true */
function asIC(tx: Transaction): Transaction {
    return { ...tx, isIntercompany: true };
}

describe('runMatchingEngine', () => {
    // --------------------------------------------------------
    // Test 1: Exact Match Pipeline
    // --------------------------------------------------------
    test('exact match pair produces one match with confidence >= 0.95', async () => {
        const txA = asIC(mockScenarios.exactMatch.invoice);
        const txB = asIC(mockScenarios.exactMatch.bill);

        const result = await runMatchingEngine(
            [txA, txB],
            mockEntityGroup,
            mockContactMappings,
            { skipLLM: true }
        );

        expect(result.matches).toHaveLength(1);
        expect(result.unmatched).toHaveLength(0);
        expect(result.matches[0]!.confidenceScore).toBeGreaterThanOrEqual(0.95);
    });

    // --------------------------------------------------------
    // Test 2: Orphan Transaction
    // --------------------------------------------------------
    test('orphan transaction with no counterpart lands in unmatched', async () => {
        const orphan = asIC(mockScenarios.orphan.invoice);

        const result = await runMatchingEngine(
            [orphan],
            mockEntityGroup,
            [],
            { skipLLM: true }
        );

        expect(result.matches).toHaveLength(0);
        expect(result.unmatched.map(tx => tx.id)).toContain(orphan.id);
    });

    // --------------------------------------------------------
    // Test 3: Zero Intercompany
    // --------------------------------------------------------
    test('all non-intercompany transactions returns early with empty matches', async () => {
        // Use mock transactions as-is (isIntercompany = false)
        const txs = [
            { ...mockScenarios.exactMatch.invoice },
            { ...mockScenarios.exactMatch.bill },
        ];

        const result = await runMatchingEngine(
            txs,
            mockEntityGroup,
            mockContactMappings,
            { skipLLM: true }
        );

        expect(result.matches).toHaveLength(0);
        expect(result.unmatched).toHaveLength(txs.length);
    });

    // --------------------------------------------------------
    // Test 4: Multi-Pair Group
    // --------------------------------------------------------
    test('two valid pairs matched, orphan in unmatched, no ID overlap', async () => {
        const txs = [
            asIC(mockScenarios.exactMatch.invoice),
            asIC(mockScenarios.exactMatch.bill),
            asIC(mockScenarios.dateOffset.invoice),
            asIC(mockScenarios.dateOffset.bill),
            asIC(mockScenarios.orphan.invoice),
        ];

        const result = await runMatchingEngine(
            txs,
            mockEntityGroup,
            mockContactMappings,
            { skipLLM: true }
        );

        expect(result.matches).toHaveLength(2);
        expect(result.unmatched).toHaveLength(1);

        // No ID appears in both matches and unmatched
        const matchedIds = new Set<string>();
        for (const m of result.matches) {
            matchedIds.add(m.transactionA.id);
            matchedIds.add(m.transactionB.id);
        }
        for (const tx of result.unmatched) {
            expect(matchedIds.has(tx.id)).toBe(false);
        }
    });

    // --------------------------------------------------------
    // Test 5: Skip LLM Option
    // --------------------------------------------------------
    test('skipLLM: true runs without error on ambiguous pair', async () => {
        const txA = asIC(mockScenarios.llmEdgeCase.invoice);
        const txB = asIC(mockScenarios.llmEdgeCase.bill);

        const result = await runMatchingEngine(
            [txA, txB],
            mockEntityGroup,
            [],
            { skipLLM: true }
        );

        // Pair either in matches (scored >= 0.45) or unmatched — no crash
        const allIds = [
            ...result.matches.flatMap(m => [m.transactionA.id, m.transactionB.id]),
            ...result.unmatched.map(tx => tx.id),
        ];
        expect(allIds).toContain(txA.id);
        expect(allIds).toContain(txB.id);
    });

    // --------------------------------------------------------
    // Test 6: Stats Accuracy
    // --------------------------------------------------------
    test('stats reflect correct candidate and match counts', async () => {
        const txs = [
            asIC(mockScenarios.exactMatch.invoice),
            asIC(mockScenarios.exactMatch.bill),
            asIC(mockScenarios.orphan.invoice),
        ];

        const result = await runMatchingEngine(
            txs,
            mockEntityGroup,
            mockContactMappings,
            { skipLLM: true }
        );

        expect(result.stats.totalCandidates).toBeGreaterThanOrEqual(1);
        expect(result.stats.runDurationMs).toBeGreaterThanOrEqual(0);
        expect(result.stats.autoMatched + result.stats.reviewRequired).toBe(
            result.matches.length
        );
    });
});
