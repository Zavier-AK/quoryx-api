// ============================================================
// Quoryx Matching Engine — Manual Test Harness
// Run with: npx ts-node scripts/test-invoice.ts
//
// Swap INVOICE_A and INVOICE_B with real Xero data to test
// the full pipeline against actual invoices.
// ============================================================

import { Transaction, EntityGroup } from '../data/types';
import { runMatchingEngine } from '../matching/engine';

// --- Test Transactions ---
// Replace these with real Xero data for manual testing.

const INVOICE_A: Transaction = {
    id: 'test-invoice-a',
    entityId: 'entity-alpha',
    entityName: 'Alpha Holdings',
    entityGroupId: 'group-test',
    sourceSystem: 'xero',
    sourceId: 'xero-inv-001',
    sourceType: 'invoice',
    date: new Date('2026-01-15'),
    amount: 10000,
    currency: 'USD',
    description: 'Management fee January 2026',
    reference: 'INV-001',
    contactName: 'Beta Services',
    contactId: 'contact-beta-001',
    isIntercompany: true,
    rawData: {},
};

const INVOICE_B: Transaction = {
    id: 'test-invoice-b',
    entityId: 'entity-beta',
    entityName: 'Beta Services',
    entityGroupId: 'group-test',
    sourceSystem: 'xero',
    sourceId: 'xero-bill-001',
    sourceType: 'bill',
    date: new Date('2026-01-18'),
    amount: 10000,
    currency: 'USD',
    description: 'Management fee January 2026',
    reference: 'BILL-001',
    contactName: 'Alpha Holdings',
    contactId: 'contact-alpha-001',
    isIntercompany: true,
    rawData: {},
};

// --- Entity Group ---

const testEntityGroup: EntityGroup = {
    id: 'group-test',
    entities: [
        { id: 'entity-alpha', name: 'Alpha Holdings' },
        { id: 'entity-beta', name: 'Beta Services' },
    ],
};

// --- Run ---

async function main() {
    console.log('='.repeat(60));
    console.log('Quoryx Matching Engine — Manual Test');
    console.log('='.repeat(60));
    console.log();

    const result = await runMatchingEngine(
        [INVOICE_A, INVOICE_B],
        testEntityGroup,
        [],
        { skipLLM: false }
    );

    // --- Matches ---
    console.log(`Matches found: ${result.matches.length}`);
    console.log('-'.repeat(40));

    for (const match of result.matches) {
        console.log(`  Pair: ${match.transactionA.id} ↔ ${match.transactionB.id}`);
        console.log(`  Confidence: ${match.confidenceScore.toFixed(4)}`);
        console.log(`  Match Type: ${match.matchType}`);
        console.log(`  Amount Difference: ${match.transactionA.currency} ${match.amountDifference.toFixed(2)}`);
        console.log(`  Days Difference: ${match.daysDifference}`);
        console.log(`  Reasons:`);
        for (const reason of match.reasons) {
            console.log(`    - ${reason}`);
        }
        if (match.llmReasoning) {
            console.log(`  LLM Reasoning: ${match.llmReasoning}`);
        }
        console.log();
    }

    // --- Unmatched ---
    console.log(`Unmatched transactions: ${result.unmatched.length}`);
    if (result.unmatched.length > 0) {
        console.log('-'.repeat(40));
        for (const tx of result.unmatched) {
            console.log(`  ${tx.id} — ${tx.entityName} — ${tx.sourceType} — ${tx.currency} ${tx.amount.toFixed(2)}`);
        }
    }
    console.log();

    // --- Stats ---
    console.log('Stats:');
    console.log('-'.repeat(40));
    console.log(`  Total Candidates:  ${result.stats.totalCandidates}`);
    console.log(`  Auto-Matched:      ${result.stats.autoMatched}`);
    console.log(`  Review Required:   ${result.stats.reviewRequired}`);
    console.log(`  LLM Assisted:      ${result.stats.llmAssisted}`);
    console.log(`  Cross-Currency:    ${result.stats.crossCurrency}`);
    console.log(`  Duration:          ${result.stats.runDurationMs}ms`);
    console.log();
    console.log('='.repeat(60));
}

main().catch(console.error);
