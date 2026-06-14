// ============================================================
// Quoryx Matching Engine — Mock Data
// Realistic test transactions covering all required edge cases.
// Tests import from here — never hardcode test data elsewhere.
// ============================================================

import { Transaction, ContactMapping, EntityGroup } from './types';

// --- Entity Group ---

export const mockEntityGroup: EntityGroup = {
    id: 'group-1',
    entities: [
        { id: 'entity-alpha', name: 'Alpha Holdings' },
        { id: 'entity-beta', name: 'Beta Services' },
        { id: 'entity-gamma', name: 'Gamma Trading' },
    ],
};

// --- Contact Mappings ---

export const mockContactMappings: ContactMapping[] = [
    {
        contactId: 'xero-contact-beta-in-alpha',
        contactExternalName: 'Beta Services Ltd',
        mapsToEntityId: 'entity-beta',
        sourceSystem: 'xero',
        confirmedBy: 'user-admin-1',
        confirmedAt: new Date('2026-01-15T10:00:00Z'),
    },
    {
        contactId: 'xero-contact-alpha-in-beta',
        contactExternalName: 'Alpha Holdings Group',
        mapsToEntityId: 'entity-alpha',
        sourceSystem: 'xero',
        confirmedBy: 'user-admin-1',
        confirmedAt: new Date('2026-01-15T10:00:00Z'),
    },
];

// --- Helper: Base Transaction Factory ---

function baseTx(overrides: Partial<Transaction> & { id: string }): Transaction {
    return {
        entityId: 'entity-alpha',
        entityName: 'Alpha Holdings',
        entityGroupId: 'group-1',
        sourceSystem: 'xero',
        sourceId: overrides.id,
        sourceType: 'invoice',
        date: new Date('2026-02-01T00:00:00Z'),
        amount: 10_000,
        currency: 'USD',
        description: 'Intercompany service charge',
        reference: 'INV-001',
        contactName: 'Beta Services',
        contactId: 'xero-contact-beta-in-alpha',
        isIntercompany: false,
        rawData: {},
        ...overrides,
    };
}

// ============================================================
// Scenario 1: Exact Match Pair
// Invoice + Bill, same date, same amount, same currency
// Expected: confidenceScore >= 0.95, matchType = 'exact'
// ============================================================

const exactMatchInvoice = baseTx({
    id: 'tx-exact-inv',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-01T00:00:00Z'),
    amount: 10_000,
    currency: 'USD',
    description: 'Management fee January 2026',
    reference: 'INV-1001',
    contactName: 'Beta Services',
    contactId: 'xero-contact-beta-in-alpha',
});

const exactMatchBill = baseTx({
    id: 'tx-exact-bill',
    entityId: 'entity-beta',
    entityName: 'Beta Services',
    sourceType: 'bill',
    date: new Date('2026-02-01T00:00:00Z'),
    amount: 10_000,
    currency: 'USD',
    description: 'Management fee January 2026',
    reference: 'BILL-1001',
    contactName: 'Alpha Holdings',
    contactId: 'xero-contact-alpha-in-beta',
});

// ============================================================
// Scenario 2: Date Offset Match
// Invoice + Bill, 5 days apart, same amount
// Expected: dateScore = 0.28
// ============================================================

const dateOffsetInvoice = baseTx({
    id: 'tx-dateoff-inv',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-01T00:00:00Z'),
    amount: 5_000,
    currency: 'USD',
    description: 'Consulting services Q1',
    reference: 'INV-1002',
    contactName: 'Beta Services',
    contactId: 'xero-contact-beta-in-alpha',
});

const dateOffsetBill = baseTx({
    id: 'tx-dateoff-bill',
    entityId: 'entity-beta',
    entityName: 'Beta Services',
    sourceType: 'bill',
    date: new Date('2026-02-06T00:00:00Z'),
    amount: 5_000,
    currency: 'USD',
    description: 'Consulting services Q1',
    reference: 'BILL-1002',
    contactName: 'Alpha Holdings',
    contactId: 'xero-contact-alpha-in-beta',
});

// ============================================================
// Scenario 3: Amount Tolerance Match
// Invoice $10,000 / Bill $10,050 (0.5% diff)
// Expected: amountScore = 0.38
// ============================================================

const amountToleranceInvoice = baseTx({
    id: 'tx-amttol-inv',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-10T00:00:00Z'),
    amount: 10_000,
    currency: 'USD',
    description: 'IT support services February',
    reference: 'INV-1003',
    contactName: 'Beta Services',
    contactId: 'xero-contact-beta-in-alpha',
});

const amountToleranceBill = baseTx({
    id: 'tx-amttol-bill',
    entityId: 'entity-beta',
    entityName: 'Beta Services',
    sourceType: 'bill',
    date: new Date('2026-02-10T00:00:00Z'),
    amount: 10_050,
    currency: 'USD',
    description: 'IT support services February',
    reference: 'BILL-1003',
    contactName: 'Alpha Holdings',
    contactId: 'xero-contact-alpha-in-beta',
});

// ============================================================
// Scenario 4: Fuzzy Name Match
// "ABC Corp USA" invoice / "ABC Corp" bill
// Expected: counterpartyScore = 0.08 (Levenshtein >= 0.80)
// ============================================================

const fuzzyNameInvoice = baseTx({
    id: 'tx-fuzzy-inv',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-05T00:00:00Z'),
    amount: 7_500,
    currency: 'USD',
    description: 'Licence fee Q1',
    reference: 'INV-1004',
    contactName: 'Gamma Trading Corp',
    contactId: 'xero-contact-gamma-unlinked',
});

const fuzzyNameBill = baseTx({
    id: 'tx-fuzzy-bill',
    entityId: 'entity-gamma',
    entityName: 'Gamma Trading',
    sourceType: 'bill',
    date: new Date('2026-02-05T00:00:00Z'),
    amount: 7_500,
    currency: 'USD',
    description: 'Licence fee Q1',
    reference: 'BILL-1004',
    contactName: 'Alpha Holdings Group',
    contactId: 'xero-contact-alpha-unlinked',
});

// ============================================================
// Scenario 5: Cross-Currency Pair
// Invoice USD $10,000 / Bill GBP £8,000
// Expected: isCrossCurrency = true, amountScore = 0.00
// ============================================================

const crossCurrencyInvoice = baseTx({
    id: 'tx-crosscur-inv',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-01T00:00:00Z'),
    amount: 10_000,
    currency: 'USD',
    description: 'Intercompany loan repayment',
    reference: 'INV-1005',
    contactName: 'Gamma Trading',
    contactId: 'xero-contact-gamma-unlinked',
});

const crossCurrencyBill = baseTx({
    id: 'tx-crosscur-bill',
    entityId: 'entity-gamma',
    entityName: 'Gamma Trading',
    sourceType: 'bill',
    date: new Date('2026-02-01T00:00:00Z'),
    amount: 8_000,
    currency: 'GBP',
    description: 'Intercompany loan repayment',
    reference: 'BILL-1005',
    contactName: 'Alpha Holdings',
    contactId: 'xero-contact-alpha-unlinked',
});

// ============================================================
// Scenario 6: Orphan Invoice
// Invoice with no corresponding bill in any entity
// Expected: appears in unmatched[]
// ============================================================

const orphanInvoice = baseTx({
    id: 'tx-orphan-inv',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-15T00:00:00Z'),
    amount: 3_200,
    currency: 'USD',
    description: 'One-off advisory service',
    reference: 'INV-1006',
    contactName: 'External Client Co',
    contactId: 'xero-contact-external',
});

// ============================================================
// Scenario 7: Same-Direction Pair
// Two invoices — should score 0.00 on type dimension
// Expected: typeScore = 0.00
// ============================================================

const sameDirectionInvoiceA = baseTx({
    id: 'tx-samedir-inv-a',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-01T00:00:00Z'),
    amount: 12_000,
    currency: 'USD',
    description: 'Monthly retainer',
    reference: 'INV-1007A',
    contactName: 'Beta Services',
    contactId: 'xero-contact-beta-in-alpha',
});

const sameDirectionInvoiceB = baseTx({
    id: 'tx-samedir-inv-b',
    entityId: 'entity-beta',
    entityName: 'Beta Services',
    sourceType: 'invoice',
    date: new Date('2026-02-01T00:00:00Z'),
    amount: 12_000,
    currency: 'USD',
    description: 'Monthly retainer',
    reference: 'INV-1007B',
    contactName: 'Alpha Holdings',
    contactId: 'xero-contact-alpha-in-beta',
});

// ============================================================
// Scenario 8: LLM Edge Case
// Different descriptions, same amount/date — ambiguous
// Expected: confidenceScore 0.45–0.60 range → LLM evaluation
// ============================================================

const llmEdgeCaseInvoice = baseTx({
    id: 'tx-llm-inv',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-03T00:00:00Z'),
    amount: 4_500,
    currency: 'USD',
    description: 'Professional services - project Phoenix',
    reference: 'INV-1008',
    contactName: 'Beta Consulting',
    contactId: 'xero-contact-beta-unknown',
});

const llmEdgeCaseBill = baseTx({
    id: 'tx-llm-bill',
    entityId: 'entity-beta',
    entityName: 'Beta Services',
    sourceType: 'bill',
    date: new Date('2026-02-03T00:00:00Z'),
    amount: 4_500,
    currency: 'USD',
    description: 'Contractor payment - Phoenix initiative',
    reference: 'BILL-1008',
    contactName: 'Alpha Group',
    contactId: 'xero-contact-alpha-unknown',
});

// ============================================================
// Scenario 9: High-Volume Group
// 50+ transactions across 3 entities
// Tests performance with larger datasets
// ============================================================

function generateHighVolumeTransactions(): Transaction[] {
    const txs: Transaction[] = [];
    const entities = [
        { id: 'entity-alpha', name: 'Alpha Holdings' },
        { id: 'entity-beta', name: 'Beta Services' },
        { id: 'entity-gamma', name: 'Gamma Trading' },
    ];

    for (let i = 0; i < 54; i++) {
        const entityIndex = i % 3;
        const entity = entities[entityIndex];
        const counterpartIndex = (entityIndex + 1) % 3;
        const counterpart = entities[counterpartIndex];
        const isInvoice = i % 2 === 0;
        const day = (i % 28) + 1;

        txs.push(
            baseTx({
                id: `tx-highvol-${i.toString().padStart(3, '0')}`,
                entityId: entity.id,
                entityName: entity.name,
                sourceType: isInvoice ? 'invoice' : 'bill',
                date: new Date(`2026-02-${day.toString().padStart(2, '0')}T00:00:00Z`),
                amount: 1_000 + i * 100,
                currency: 'USD',
                description: `High-volume transaction #${i + 1}`,
                reference: `HV-${i.toString().padStart(3, '0')}`,
                contactName: counterpart.name,
                contactId: `xero-contact-${counterpart.id}-hv`,
            })
        );
    }

    return txs;
}

const highVolumeTransactions = generateHighVolumeTransactions();

// ============================================================
// Scenario 10: ContactMapping Match
// Contact ID confirmed in mapping table
// Expected: counterpartyScore = 0.10 (confirmed mapping)
// ============================================================

const contactMappingInvoice = baseTx({
    id: 'tx-cmap-inv',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    sourceType: 'invoice',
    date: new Date('2026-02-08T00:00:00Z'),
    amount: 15_000,
    currency: 'USD',
    description: 'Shared services allocation Feb',
    reference: 'INV-1010',
    contactName: 'Beta Services Ltd',
    contactId: 'xero-contact-beta-in-alpha', // This ID exists in mockContactMappings
});

const contactMappingBill = baseTx({
    id: 'tx-cmap-bill',
    entityId: 'entity-beta',
    entityName: 'Beta Services',
    sourceType: 'bill',
    date: new Date('2026-02-08T00:00:00Z'),
    amount: 15_000,
    currency: 'USD',
    description: 'Shared services allocation Feb',
    reference: 'BILL-1010',
    contactName: 'Alpha Holdings Group',
    contactId: 'xero-contact-alpha-in-beta', // This ID exists in mockContactMappings
});

// ============================================================
// Exported Mock Data
// ============================================================

/** All mock transactions, including high-volume set */
export const mockTransactions: Transaction[] = [
    // Scenario 1: Exact match
    exactMatchInvoice,
    exactMatchBill,
    // Scenario 2: Date offset
    dateOffsetInvoice,
    dateOffsetBill,
    // Scenario 3: Amount tolerance
    amountToleranceInvoice,
    amountToleranceBill,
    // Scenario 4: Fuzzy name
    fuzzyNameInvoice,
    fuzzyNameBill,
    // Scenario 5: Cross-currency
    crossCurrencyInvoice,
    crossCurrencyBill,
    // Scenario 6: Orphan
    orphanInvoice,
    // Scenario 7: Same direction
    sameDirectionInvoiceA,
    sameDirectionInvoiceB,
    // Scenario 8: LLM edge case
    llmEdgeCaseInvoice,
    llmEdgeCaseBill,
    // Scenario 9: High-volume (54 transactions)
    ...highVolumeTransactions,
    // Scenario 10: ContactMapping
    contactMappingInvoice,
    contactMappingBill,
];

// --- Named exports for targeted test access ---

export const mockScenarios = {
    exactMatch: { invoice: exactMatchInvoice, bill: exactMatchBill },
    dateOffset: { invoice: dateOffsetInvoice, bill: dateOffsetBill },
    amountTolerance: { invoice: amountToleranceInvoice, bill: amountToleranceBill },
    fuzzyName: { invoice: fuzzyNameInvoice, bill: fuzzyNameBill },
    crossCurrency: { invoice: crossCurrencyInvoice, bill: crossCurrencyBill },
    orphan: { invoice: orphanInvoice },
    sameDirection: { invoiceA: sameDirectionInvoiceA, invoiceB: sameDirectionInvoiceB },
    llmEdgeCase: { invoice: llmEdgeCaseInvoice, bill: llmEdgeCaseBill },
    highVolume: highVolumeTransactions,
    contactMapping: { invoice: contactMappingInvoice, bill: contactMappingBill },
} as const;
