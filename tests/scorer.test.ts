// ============================================================
// Quoryx Matching Engine — Scorer Tests
// All tests use mock data from data/mock-data.ts.
// ============================================================

import { scoreCandidate } from '../matching/scorer';
import { mockScenarios, mockContactMappings } from '../data/mock-data';

describe('scoreCandidate', () => {
    // --------------------------------------------------------
    // Test 1: Exact Match
    // --------------------------------------------------------
    test('exact match pair scores >= 0.95 with matchType exact', () => {
        const result = scoreCandidate(
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockContactMappings
        );

        expect(result.confidenceScore).toBeGreaterThanOrEqual(0.95);
        expect(result.matchType).toBe('exact');
    });

    // --------------------------------------------------------
    // Test 2: Amount Tolerance
    // --------------------------------------------------------
    test('amount tolerance pair ($10,000 vs $10,050) scores amountScore 0.38', () => {
        const result = scoreCandidate(
            mockScenarios.amountTolerance.invoice,
            mockScenarios.amountTolerance.bill,
            mockContactMappings
        );

        expect(result.amountScore).toBe(0.38);
        expect(result.amountDifference).toBe(50);
    });

    // --------------------------------------------------------
    // Test 3: Date Offset
    // --------------------------------------------------------
    test('date offset pair (5 days apart) scores dateScore 0.28', () => {
        const result = scoreCandidate(
            mockScenarios.dateOffset.invoice,
            mockScenarios.dateOffset.bill,
            mockContactMappings
        );

        expect(result.dateScore).toBe(0.28);
        expect(result.daysDifference).toBe(5);
    });

    // --------------------------------------------------------
    // Test 4: Type Mismatch — Same Direction
    // --------------------------------------------------------
    test('same-direction pair (invoice vs invoice) scores typeScore 0.00', () => {
        const result = scoreCandidate(
            mockScenarios.sameDirection.invoiceA,
            mockScenarios.sameDirection.invoiceB,
            mockContactMappings
        );

        expect(result.typeScore).toBe(0.00);
    });

    // --------------------------------------------------------
    // Test 5: Counterparty Fuzzy
    // --------------------------------------------------------
    test('fuzzy name pair scores counterpartyScore 0.08', () => {
        const result = scoreCandidate(
            mockScenarios.fuzzyName.invoice,
            mockScenarios.fuzzyName.bill,
            mockContactMappings
        );

        expect(result.counterpartyScore).toBe(0.08);
    });

    // --------------------------------------------------------
    // Test 6: Cross-Currency
    // --------------------------------------------------------
    test('cross-currency pair has isCrossCurrency true and amountScore 0.00', () => {
        const result = scoreCandidate(
            mockScenarios.crossCurrency.invoice,
            mockScenarios.crossCurrency.bill,
            mockContactMappings
        );

        expect(result.isCrossCurrency).toBe(true);
        expect(result.amountScore).toBe(0.00);
    });

    // --------------------------------------------------------
    // Test 7: Score Sum
    // --------------------------------------------------------
    test('confidenceScore equals sum of all 4 dimension scores', () => {
        const result = scoreCandidate(
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockContactMappings
        );

        const expectedSum = Math.round(
            (result.amountScore + result.dateScore + result.typeScore + result.counterpartyScore) * 10000
        ) / 10000;

        expect(result.confidenceScore).toBeCloseTo(expectedSum, 4);
    });

    // --------------------------------------------------------
    // Test 8: ContactMapping Priority
    // --------------------------------------------------------
    test('ContactMapping pair scores counterpartyScore 0.10 with reason', () => {
        const result = scoreCandidate(
            mockScenarios.contactMapping.invoice,
            mockScenarios.contactMapping.bill,
            mockContactMappings
        );

        expect(result.counterpartyScore).toBe(0.10);
        expect(result.reasons.some(r => r.includes('ContactMapping'))).toBe(true);
    });

    // --------------------------------------------------------
    // Test 9: Reasons Not Empty
    // --------------------------------------------------------
    test('pair scoring >= 0.60 has at least 2 reasons', () => {
        const result = scoreCandidate(
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockContactMappings
        );

        expect(result.confidenceScore).toBeGreaterThanOrEqual(0.60);
        expect(result.reasons.length).toBeGreaterThanOrEqual(2);
    });

    // --------------------------------------------------------
    // Test 10: Pure Function Check
    // --------------------------------------------------------
    test('calling scoreCandidate twice with same inputs gives identical results', () => {
        const result1 = scoreCandidate(
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockContactMappings
        );

        const result2 = scoreCandidate(
            mockScenarios.exactMatch.invoice,
            mockScenarios.exactMatch.bill,
            mockContactMappings
        );

        expect(result1.confidenceScore).toBe(result2.confidenceScore);
        expect(result1.amountScore).toBe(result2.amountScore);
        expect(result1.dateScore).toBe(result2.dateScore);
        expect(result1.typeScore).toBe(result2.typeScore);
        expect(result1.counterpartyScore).toBe(result2.counterpartyScore);
    });
});
