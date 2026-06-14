// ============================================================
// Quoryx Matching Engine — Database Adapter
// Reads from Supabase. No writes — writes go through
// the Railway PATCH endpoint only.
// ============================================================

import { createClient, SupabaseClient } from '@supabase/supabase-js';

// --- Supabase Client (lazy initialisation) ---

let _supabase: SupabaseClient | null = null;

function getSupabase(): SupabaseClient {
    if (!_supabase) {
        _supabase = createClient(
            process.env.SUPABASE_URL!,
            process.env.SUPABASE_ANON_KEY!
        );
    }
    return _supabase;
}

// --- Interfaces (match exact DB column names) ---

export interface IntercompanyPair {
    id: string;
    source_transaction_id: string;
    target_transaction_id: string;
    status: string;
    created_at: string;
}

export interface RawTransaction {
    id: string;
    external_id: string | null;
    provider: string | null;
    amount: number | string;
    currency: string | null;
    description: string | null;
    transaction_date: string;
    entity_id: string;
    contact_name: string | null;
    transaction_type: string | null;
    reference: string | null;
    raw_payload: string | null;
    status: string | null;
    token_id: string | null;
    matched_transaction_id: string | null;
    created_at: string;
    updated_at: string;
    account_code: string | null;
}

// --- Public API ---

/**
 * Fetch all entities as a map of entity_id → org_name.
 * Used to give transactions their real entity name (for counterparty scoring)
 * instead of the bare UUID.
 */
export async function fetchEntityNames(): Promise<Map<string, string>> {
    const { data, error } = await getSupabase()
        .from('entities')
        .select('id, org_name');

    if (error) throw error;
    const map = new Map<string, string>();
    for (const row of data ?? []) {
        if (row.id && row.org_name) map.set(row.id, row.org_name);
    }
    return map;
}

/**
 * Fetch all unmatched intercompany pairs from Supabase.
 */
export async function fetchUnmatchedPairs(): Promise<IntercompanyPair[]> {
    const { data, error } = await getSupabase()
        .from('intercompany_transactions')
        .select('*')
        .eq('status', 'unmatched');

    if (error) throw error;
    return (data ?? []) as IntercompanyPair[];
}

/**
 * Fetch a single transaction by its external_id.
 * Returns null if not found — never throws on missing row.
 */
export async function fetchTransactionById(id: string): Promise<RawTransaction | null> {
    const { data, error } = await getSupabase()
        .from('transactions')
        .select('*')
        .eq('external_id', id)
        .single();

    if (error || !data) return null;
    return data as RawTransaction;
}

/**
 * Fetch both transactions for an intercompany pair in parallel.
 * Returns null if either transaction is missing.
 */
export async function fetchTransactionPair(
    sourceId: string,
    targetId: string
): Promise<{ source: RawTransaction; target: RawTransaction } | null> {
    const [source, target] = await Promise.all([
        fetchTransactionById(sourceId),
        fetchTransactionById(targetId),
    ]);

    if (!source) {
        console.warn(`Missing transaction: ${sourceId} — skipping pair`);
        return null;
    }
    if (!target) {
        console.warn(`Missing transaction: ${targetId} — skipping pair`);
        return null;
    }

    return { source, target };
}
