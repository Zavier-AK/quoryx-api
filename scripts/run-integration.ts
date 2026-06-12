// ============================================================
// Quoryx Matching Engine — Full Integration Pipeline
// Reads unmatched pairs from Supabase, runs the matching
// engine, and writes results back via Railway PATCH endpoint.
//
// Run with: npx ts-node scripts/run-integration.ts
// ============================================================

import * as dotenv from 'dotenv';
dotenv.config();

import { Transaction, EntityGroup } from '../data/types';
import { fetchUnmatchedPairs, fetchTransactionPair, IntercompanyPair } from '../data/db-adapter';
import { normalizeDbTransaction } from '../data/db-normalizer';
import { runMatchingEngine } from '../matching/engine';

const RAILWAY_BASE = 'https://web-production-4f190.up.railway.app';

// --- Helper: Trigger detection endpoint ---

async function triggerDetection(): Promise<void> {
    try {
        console.log('Triggering detection endpoint...');
        await fetch(`${RAILWAY_BASE}/api/reconciliation/run`, {
            method: 'POST',
        });
    } catch (err) {
        console.warn('Detection trigger failed — continuing:', err);
    }
}

// --- Helper: PATCH pair status ---

async function patchPairStatus(pairId: string, payload: object): Promise<boolean> {
    try {
        const response = await fetch(
            `${RAILWAY_BASE}/api/reconciliation/pairs/${pairId}/status`,
            {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            }
        );
        return response.ok;
    } catch {
        return false;
    }
}

// --- Main Pipeline ---

async function main() {
    // STEP 1 — Trigger detection
    await triggerDetection();

    // STEP 2 — Fetch unmatched pairs
    const pairs = await fetchUnmatchedPairs();
    console.log(`Found ${pairs.length} unmatched pairs`);

    if (pairs.length === 0) {
        console.log('Nothing to process');
        return;
    }

    // STEP 3 — Fetch and normalize both transactions per pair
    const allTransactions: Transaction[] = [];
    // Track: normalized transaction internal ID → original DB row ID
    const internalIdToDbId = new Map<string, string>();
    const validPairs: IntercompanyPair[] = [];

    for (const pair of pairs) {
        const txPair = await fetchTransactionPair(
            pair.source_transaction_id,
            pair.target_transaction_id
        );

        if (!txPair) continue;

        const source = normalizeDbTransaction(txPair.source, pair.id, true);
        const target = normalizeDbTransaction(txPair.target, pair.id, true);

        // Track mapping back to pair transaction IDs for PATCH step
        internalIdToDbId.set(source.id, pair.source_transaction_id);
        internalIdToDbId.set(target.id, pair.target_transaction_id);

        allTransactions.push(source, target);
        validPairs.push(pair);
    }

    if (allTransactions.length === 0) {
        console.log('No valid transaction pairs found');
        return;
    }

    // STEP 4 — Build entity group
    const uniqueEntityIds = [...new Set(allTransactions.map(tx => tx.entityId))];
    const entityGroup: EntityGroup = {
        id: 'live-group',
        entities: uniqueEntityIds.map(id => ({ id, name: id })),
    };

    // STEP 5 — Run matching engine
    const result = await runMatchingEngine(
        allTransactions,
        entityGroup,
        [],
        { skipLLM: false }
    );

    // STEP 6 — Write results back
    for (const match of result.matches) {
        // Find the correct pair by mapping internal IDs back to DB IDs
        const dbIdA = internalIdToDbId.get(match.transactionA.id);
        const dbIdB = internalIdToDbId.get(match.transactionB.id);

        const pair = validPairs.find(p =>
            (p.source_transaction_id === dbIdA && p.target_transaction_id === dbIdB) ||
            (p.source_transaction_id === dbIdB && p.target_transaction_id === dbIdA)
        );

        if (!pair) {
            console.error(`❌ Could not find pair for match: ${match.transactionA.id} ↔ ${match.transactionB.id}`);
            continue;
        }

        const status = match.confidenceScore >= 0.85 ? 'matched' : 'review_required';
        const payload = {
            status,
            confidence_score: match.confidenceScore,
            match_type: match.matchType,
            amount_difference: match.amountDifference,
            days_difference: match.daysDifference,
            match_reasons: JSON.stringify(match.reasons),
            llm_reasoning: match.llmReasoning ?? null,
            review_required: match.confidenceScore < 0.85,
        };

        const ok = await patchPairStatus(pair.id, payload);

        if (ok) {
            if (status === 'matched') {
                console.log(`✅ Pair ${pair.id} → matched (confidence: ${match.confidenceScore.toFixed(2)})`);
            } else {
                console.log(`⚠️  Pair ${pair.id} → review_required (confidence: ${match.confidenceScore.toFixed(2)})`);
            }
        } else {
            console.log(`❌ Pair ${pair.id} → PATCH failed`);
        }
    }

    for (const tx of result.unmatched) {
        console.log(`🔍 Unmatched: ${tx.sourceId} from entity ${tx.entityId}`);
    }

    // STEP 7 — Print summary
    console.log();
    console.log('════════════════════════════');
    console.log('Quoryx Engine — Run Complete');
    console.log('════════════════════════════');
    console.log(`Pairs processed: ${pairs.length}`);
    console.log(`Matched: ${result.stats.autoMatched}`);
    console.log(`Review required: ${result.stats.reviewRequired}`);
    console.log(`LLM assisted: ${result.stats.llmAssisted}`);
    console.log(`Unmatched: ${result.unmatched.length}`);
    console.log(`Duration: ${result.stats.runDurationMs}ms`);
}

main().catch(console.error);
