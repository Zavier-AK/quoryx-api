// ============================================================
// Quoryx Matching Engine — Greedy Assignment Tests
// Candidates generated via scoreCandidate — never manually constructed.
// ============================================================

import { greedyAssign } from '../matching/greedy';
import { scoreCandidate } from '../matching/scorer';
import {
    mockScenarios,
    mockContactMappings,
    mockTransactions,
} from '../data/mock-data';

describe('greedyAssign', () => {
    // --------------------------------------------------------
    // Test 1: Basic Deduplication
    // --------------------------------------------------------
    test('each transaction ID appears in exactly one match', () => {
        const candidates = [
            scoreCandidate(
                mockScenarios.exactMatch.invoice,
                mockScenarios.exactMatch.bill,
                mockContactMappings
            ),
            scoreCandidate(
                mockScenarios.amountTolerance.invoice,
                mockScenarios.amountTolerance.bill,
                mockContactMappings
            ),
        ];
        const allTxs = [
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockScenarios.amountTolerance.invoice,
            mockScenarios.amountTolerance.bill,
        ];

        const result = greedyAssign(candidates, allTxs);

        // Collect all IDs from matches
        const matchedIds = new Set<string>();
        for (const match of result.matches) {
            matchedIds.add(match.transactionA.id);
            matchedIds.add(match.transactionB.id);
        }

        // Each ID appears exactly once (set size = matches × 2)
        expect(matchedIds.size).toBe(result.matches.length * 2);

        // No ID appears in both matches[] and unmatched[]
        const unmatchedIds = new Set(result.unmatched.map(tx => tx.id));
        for (const id of matchedIds) {
            expect(unmatchedIds.has(id)).toBe(false);
        }
    });

    // --------------------------------------------------------
    // Test 2: Highest Confidence Wins
    // --------------------------------------------------------
    test('highest confidence candidate wins when two share a transaction', () => {
        const txA = mockScenarios.exactMatch.invoice;
        const txB = mockScenarios.exactMatch.bill;
        const txC = mockScenarios.amountTolerance.bill;

        // Candidate 1: txA + txB → ~1.00
        const candidate1 = scoreCandidate(txA, txB, mockContactMappings);
        // Candidate 2: txA + txC → ~0.93 (shares txA with candidate1)
        const candidate2 = scoreCandidate(txA, txC, mockContactMappings);

        const result = greedyAssign([candidate1, candidate2], [txA, txB, txC]);

        // Only candidate1 should be in matches
        expect(result.matches).toHaveLength(1);
        expect(result.matches[0]!.transactionA.id).toBe(txA.id);
        expect(result.matches[0]!.transactionB.id).toBe(txB.id);

        // txC should be unmatched
        expect(result.unmatched.map(tx => tx.id)).toContain(txC.id);
    });

    // --------------------------------------------------------
    // Test 3: Orphan Appears in Unmatched
    // --------------------------------------------------------
    test('orphan transaction appears in unmatched', () => {
        const candidates = [
            scoreCandidate(
                mockScenarios.exactMatch.invoice,
                mockScenarios.exactMatch.bill,
                mockContactMappings
            ),
        ];
        const allTxs = [
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockScenarios.orphan.invoice,
        ];

        const result = greedyAssign(candidates, allTxs);

        expect(result.unmatched.map(tx => tx.id)).toContain(
            mockScenarios.orphan.invoice.id
        );
    });

    // --------------------------------------------------------
    // Test 4: Empty Candidates
    // --------------------------------------------------------
    test('empty candidates returns all transactions as unmatched', () => {
        const allTxs = [
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
        ];

        const result = greedyAssign([], allTxs);

        expect(result.matches).toHaveLength(0);
        expect(result.unmatched).toHaveLength(allTxs.length);
    });

    // --------------------------------------------------------
    // Test 5: Empty Transactions
    // --------------------------------------------------------
    test('empty candidates and empty transactions returns empty result', () => {
        const result = greedyAssign([], []);

        expect(result.matches).toHaveLength(0);
        expect(result.unmatched).toHaveLength(0);
    });

    // --------------------------------------------------------
    // Test 6: No Duplicate IDs in Output
    // --------------------------------------------------------
    test('no transaction ID appears more than once across output', () => {
        const candidates = [
            scoreCandidate(mockScenarios.exactMatch.invoice, mockScenarios.exactMatch.bill, mockContactMappings),
            scoreCandidate(mockScenarios.dateOffset.invoice, mockScenarios.dateOffset.bill, mockContactMappings),
            scoreCandidate(mockScenarios.amountTolerance.invoice, mockScenarios.amountTolerance.bill, mockContactMappings),
            scoreCandidate(mockScenarios.fuzzyName.invoice, mockScenarios.fuzzyName.bill, mockContactMappings),
            scoreCandidate(mockScenarios.contactMapping.invoice, mockScenarios.contactMapping.bill, mockContactMappings),
        ];
        const allTxs = [
            mockScenarios.exactMatch.invoice, mockScenarios.exactMatch.bill,
            mockScenarios.dateOffset.invoice, mockScenarios.dateOffset.bill,
            mockScenarios.amountTolerance.invoice, mockScenarios.amountTolerance.bill,
            mockScenarios.fuzzyName.invoice, mockScenarios.fuzzyName.bill,
            mockScenarios.contactMapping.invoice, mockScenarios.contactMapping.bill,
            mockScenarios.orphan.invoice,
        ];

        const result = greedyAssign(candidates, allTxs);

        // Collect every ID from the output
        const allIds: string[] = [];
        for (const match of result.matches) {
            allIds.push(match.transactionA.id);
            allIds.push(match.transactionB.id);
        }
        for (const tx of result.unmatched) {
            allIds.push(tx.id);
        }

        const uniqueIds = new Set(allIds);
        expect(uniqueIds.size).toBe(allIds.length);
    });

    // --------------------------------------------------------
    // Test 7: Sort Order Respected
    // --------------------------------------------------------
    test('candidates A and C kept, B blocked because it shares a transaction with A', () => {
        // A: highest score (~1.00)
        const candidateA = scoreCandidate(
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockContactMappings
        );
        // B: shares exactMatch.invoice with A, lower score (~0.58)
        const candidateB = scoreCandidate(
            mockScenarios.exactMatch.invoice,
            mockScenarios.dateOffset.bill,
            mockContactMappings
        );
        // C: independent pair (~0.98)
        const candidateC = scoreCandidate(
            mockScenarios.amountTolerance.invoice,
            mockScenarios.amountTolerance.bill,
            mockContactMappings
        );

        const allTxs = [
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockScenarios.dateOffset.bill,
            mockScenarios.amountTolerance.invoice,
            mockScenarios.amountTolerance.bill,
        ];

        const result = greedyAssign([candidateA, candidateB, candidateC], allTxs);

        // Build pair keys for easy comparison
        const matchedPairs = result.matches.map(m =>
            [m.transactionA.id, m.transactionB.id].sort().join('::')
        );
        const pairA = [mockScenarios.exactMatch.invoice.id, mockScenarios.exactMatch.bill.id].sort().join('::');
        const pairB = [mockScenarios.exactMatch.invoice.id, mockScenarios.dateOffset.bill.id].sort().join('::');
        const pairC = [mockScenarios.amountTolerance.invoice.id, mockScenarios.amountTolerance.bill.id].sort().join('::');

        expect(matchedPairs).toContain(pairA);
        expect(matchedPairs).not.toContain(pairB);
        expect(matchedPairs).toContain(pairC);
    });

    // --------------------------------------------------------
    // Test 8: All Transactions Accounted For
    // --------------------------------------------------------
    test('(matches × 2) + unmatched equals total transactions', () => {
        const candidates = [
            scoreCandidate(mockScenarios.exactMatch.invoice, mockScenarios.exactMatch.bill, mockContactMappings),
            scoreCandidate(mockScenarios.dateOffset.invoice, mockScenarios.dateOffset.bill, mockContactMappings),
            scoreCandidate(mockScenarios.amountTolerance.invoice, mockScenarios.amountTolerance.bill, mockContactMappings),
            scoreCandidate(mockScenarios.fuzzyName.invoice, mockScenarios.fuzzyName.bill, mockContactMappings),
            scoreCandidate(mockScenarios.crossCurrency.invoice, mockScenarios.crossCurrency.bill, mockContactMappings),
            scoreCandidate(mockScenarios.sameDirection.invoiceA, mockScenarios.sameDirection.invoiceB, mockContactMappings),
            scoreCandidate(mockScenarios.llmEdgeCase.invoice, mockScenarios.llmEdgeCase.bill, mockContactMappings),
            scoreCandidate(mockScenarios.contactMapping.invoice, mockScenarios.contactMapping.bill, mockContactMappings),
        ];

        const result = greedyAssign(candidates, mockTransactions);

        const matchedCount = result.matches.length * 2;
        const unmatchedCount = result.unmatched.length;

        expect(matchedCount + unmatchedCount).toBe(mockTransactions.length);
    });
});
