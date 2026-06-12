// ============================================================
// Quoryx Matching Engine — Database Normalizer
// Converts RawTransaction (from Supabase) into the internal
// Transaction type. Maps DB column names to domain fields.
// ============================================================

import { Transaction, SourceType } from './types';
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
    // Normalize sourceType
    const rawType = raw.transaction_type?.toLowerCase().trim() ?? '';
    let sourceType: SourceType;

    if (rawType === 'receive' || rawType === 'invoice') {
        sourceType = 'invoice';
    } else if (rawType === 'spend' || rawType === 'bill') {
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

    return {
        id: randomUUID(),
        entityId: raw.entity_id,
        entityName: raw.entity_id,
        entityGroupId,
        sourceSystem: raw.provider === 'quickbooks' ? 'quickbooks' : 'xero',
        sourceId: raw.external_id ?? raw.id,
        sourceType,
        date: new Date(raw.transaction_date),
        amount: Math.abs(Number(raw.amount)),
        currency: raw.currency?.trim().toUpperCase() ?? 'USD',
        description: raw.description?.trim() ?? '',
        reference: raw.reference?.trim() ?? '',
        contactName: raw.contact_name?.trim() ?? '',
        contactId: '',
        isIntercompany,
        rawData,
    };
}
