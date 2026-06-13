// ============================================================
// Quoryx Matching Engine — Database Normalizer
// Converts RawTransaction (from Supabase) into the internal
// Transaction type. Maps DB column names to domain fields.
// ============================================================

import { Transaction, SourceType, SourceSystem } from './types';
import { RawTransaction } from './db-adapter';
import { randomUUID } from 'crypto';

/**
 * Convert a raw Supabase transaction row into the internal
 * Transaction type used by the matching engine.
 *
 * @param raw - Raw row from the transactions table
 * @param entityGroupId - Group ID for this matching run
 * @param isIntercompany - Whether this transaction is intercompany
 * @returns Normalized Transaction
 */
export function normalizeDbTransaction(
    raw: RawTransaction,
    entityGroupId: string,
    isIntercompany: boolean
): Transaction {
    // Normalize sourceType. Match by prefix so Xero compound types
    // (RECEIVE-OVERPAYMENT, SPEND-PREPAYMENT, SPEND-TRANSFER, ...) collapse to
    // the correct direction instead of silently falling through to a default.
    const rawType = raw.transaction_type?.toLowerCase().trim() ?? '';
    let sourceType: SourceType;

    if (rawType.startsWith('receive') || rawType === 'invoice') {
        sourceType = 'invoice';
    } else if (rawType.startsWith('spend') || rawType === 'bill') {
        sourceType = 'bill';
    } else if (rawType === 'journal') {
        sourceType = 'journal';
    } else {
        console.warn(`Unknown transaction_type: ${raw.transaction_type}`);
        sourceType = 'invoice';
    }

    // Parse raw_payload safely
    let rawData: Record<string, unknown> = {};
    if (raw.raw_payload) {
        try {
            rawData = JSON.parse(raw.raw_payload);
        } catch {
            rawData = {};
        }
    }

    // Map the DB provider column to the internal SourceSystem. Each provider is
    // listed explicitly so a new provider can't silently inherit Xero's label.
    let sourceSystem: SourceSystem;
    switch (raw.provider) {
        case 'quickbooks':
            sourceSystem = 'quickbooks';
            break;
        case 'economic':
            sourceSystem = 'economic';
            break;
        case 'xero':
            sourceSystem = 'xero';
            break;
        default:
            console.warn(`Unknown provider: ${raw.provider} — defaulting to xero`);
            sourceSystem = 'xero';
    }

    // Coerce amount safely. Number(null) is 0 and Number('x') is NaN; a NaN or
    // non-finite amount would poison the scorer (it divides by amount), so guard
    // it down to 0 with a warning rather than letting it flow downstream.
    const parsedAmount = Math.abs(Number(raw.amount));
    const amount = Number.isFinite(parsedAmount) ? parsedAmount : 0;
    if (!Number.isFinite(parsedAmount)) {
        console.warn(`Invalid amount for ${raw.external_id ?? raw.id}: ${raw.amount}`);
    }

    // Guard against an unparseable date. An Invalid Date silently produces NaN in
    // day-difference math; fall back to the epoch so the row surfaces as an
    // unmatched orphan instead of corrupting a pair's date score.
    let date = new Date(raw.transaction_date);
    if (Number.isNaN(date.getTime())) {
        console.warn(`Invalid date for ${raw.external_id ?? raw.id}: ${raw.transaction_date}`);
        date = new Date(0);
    }

    return {
        id: randomUUID(),
        entityId: raw.entity_id,
        entityName: raw.entity_id,
        entityGroupId,
        sourceSystem,
        sourceId: raw.external_id ?? raw.id,
        sourceType,
        date,
        amount,
        currency: raw.currency?.trim().toUpperCase() ?? 'USD',
        description: raw.description?.trim() ?? '',
        reference: raw.reference?.trim() ?? '',
        contactName: raw.contact_name?.trim() ?? '',
        contactId: '',
        isIntercompany,
        rawData,
    };
}
