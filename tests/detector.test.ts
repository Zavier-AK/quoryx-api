// ============================================================
// Quoryx Matching Engine — Intercompany Detection Tests
// All test data derived from mock-data.ts — never hardcoded.
// ============================================================

import { detectIntercompany } from '../matching/detector';
import {
    mockScenarios,
    mockContactMappings,
    mockEntityGroup,
    mockTransactions,
} from '../data/mock-data';
import { Transaction } from '../data/types';

describe('detectIntercompany', () => {
    // --------------------------------------------------------
    // Test 1: ContactMapping Priority
    // --------------------------------------------------------
    test('ContactMapping fires before name checks', () => {
        // contactMappingInvoice has contactId='xero-contact-beta-in-alpha'
        // which maps to entity-beta (different from own entity-alpha)
        const result = detectIntercompany(
            [mockScenarios.contactMapping.invoice],
            mockEntityGroup,
            mockContactMappings
        );

        expect(result[0]!.isIntercompany).toBe(true);

        // Prove ContactMapping fires BEFORE name checks:
        // Use same contactId but a contactName that matches NO entity
        const noNameMatchTx: Transaction = {
            ...mockScenarios.contactMapping.invoice,
            id: 'tx-test-cmap-priority',
            contactName: 'Completely Unknown Vendor XYZ',
        };

        const result2 = detectIntercompany(
            [noNameMatchTx],
            mockEntityGroup,
            mockContactMappings
        );

        // Still flagged — only the contactId mapping triggered it
        expect(result2[0]!.isIntercompany).toBe(true);
    });

    // --------------------------------------------------------
    // Test 2: Exact Name Match
    // --------------------------------------------------------
    test('exact contactName matching another entity flags intercompany', () => {
        // crossCurrencyInvoice: contactName='Gamma Trading',
        // contactId='xero-contact-gamma-unlinked' (NOT in mappings)
        // 'Gamma Trading' exactly matches entity 'Gamma Trading' (entity-gamma)
        const result = detectIntercompany(
            [mockScenarios.crossCurrency.invoice],
            mockEntityGroup,
            mockContactMappings
        );

        expect(result[0]!.isIntercompany).toBe(true);
    });

    // --------------------------------------------------------
    // Test 3: Substring Match
    // --------------------------------------------------------
    test('contactName that is a substring of an entity name flags intercompany', () => {
        // Create a transaction where contactName "Beta" is a substring
        // of entity name "Beta Services"
        const substringTx: Transaction = {
            ...mockScenarios.orphan.invoice,
            id: 'tx-test-substring',
            contactName: 'Beta',
            contactId: 'xero-contact-no-mapping',
        };

        const result = detectIntercompany(
            [substringTx],
            mockEntityGroup,
            mockContactMappings
        );

        expect(result[0]!.isIntercompany).toBe(true);
    });

    // --------------------------------------------------------
    // Test 4: Fuzzy Match
    // --------------------------------------------------------
    test('fuzzy name match flags intercompany', () => {
        // fuzzyNameInvoice: contactName='Gamma Trading Corp',
        // contactId='xero-contact-gamma-unlinked' (NOT in mappings)
        // Matches 'Gamma Trading' entity via substring/fuzzy
        const result = detectIntercompany(
            [mockScenarios.fuzzyName.invoice],
            mockEntityGroup,
            mockContactMappings
        );

        expect(result[0]!.isIntercompany).toBe(true);
    });

    // --------------------------------------------------------
    // Test 5: No Match — External Contact
    // --------------------------------------------------------
    test('external contact with no entity resemblance is not intercompany', () => {
        const externalTx: Transaction = {
            ...mockScenarios.orphan.invoice,
            id: 'tx-test-external',
            contactName: 'Unrelated Vendor Ltd',
            contactId: 'xero-contact-no-mapping',
        };

        const result = detectIntercompany(
            [externalTx],
            mockEntityGroup,
            mockContactMappings
        );

        expect(result[0]!.isIntercompany).toBe(false);
    });

    // --------------------------------------------------------
    // Test 6: Own Entity Excluded
    // --------------------------------------------------------
    test('contactName matching own entity does not flag intercompany', () => {
        // Transaction belongs to entity-alpha, contactName is 'Alpha Holdings'
        // (same as own entity name) — must NOT match itself
        const ownEntityTx: Transaction = {
            ...mockScenarios.exactMatch.invoice,
            id: 'tx-test-own-entity',
            contactName: 'Alpha Holdings',
            contactId: 'xero-contact-no-mapping',
        };

        const result = detectIntercompany(
            [ownEntityTx],
            mockEntityGroup,
            mockContactMappings
        );

        expect(result[0]!.isIntercompany).toBe(false);
    });

    // --------------------------------------------------------
    // Test 7: Empty Contact Name
    // --------------------------------------------------------
    test('empty contactName leaves isIntercompany false without error', () => {
        const emptyContactTx: Transaction = {
            ...mockScenarios.orphan.invoice,
            id: 'tx-test-empty-contact',
            contactName: '',
            contactId: 'xero-contact-no-mapping',
        };

        const result = detectIntercompany(
            [emptyContactTx],
            mockEntityGroup,
            mockContactMappings
        );

        expect(result[0]!.isIntercompany).toBe(false);
    });

    // --------------------------------------------------------
    // Test 8: Immutability
    // --------------------------------------------------------
    test('original transactions are not mutated and returned array is new', () => {
        // Capture original isIntercompany values
        const originalFlags = mockTransactions.map(tx => tx.isIntercompany);

        const result = detectIntercompany(
            mockTransactions,
            mockEntityGroup,
            mockContactMappings
        );

        // Returned array is a new reference
        expect(result).not.toBe(mockTransactions);

        // Original transaction objects are unchanged
        for (let i = 0; i < mockTransactions.length; i++) {
            expect(mockTransactions[i]!.isIntercompany).toBe(originalFlags[i]);
        }
    });
});
