// ============================================================
// Tests for data/db-normalizer.ts — the shared boundary every
// provider's rows pass through on the way to the matching engine.
// Bad normalization here corrupts matching for ALL providers, so
// these cover the messy real-world shapes Xero/E-conomic emit.
// ============================================================

import { normalizeDbTransaction } from '../data/db-normalizer';
import { RawTransaction } from '../data/db-adapter';

// Minimal valid row; individual tests override only what they exercise.
function makeRaw(overrides: Partial<RawTransaction> = {}): RawTransaction {
    return {
        id: 'row-1',
        external_id: 'ext-1',
        provider: 'xero',
        amount: 1000,
        currency: 'DKK',
        description: 'Management fee Q1',
        transaction_date: '2026-02-22T00:00:00',
        entity_id: 'entity-a',
        contact_name: 'Quoryx Holdings',
        transaction_type: 'RECEIVE',
        reference: 'ICT-001',
        raw_payload: null,
        status: 'pending',
        token_id: 'tok-1',
        matched_transaction_id: null,
        created_at: '2026-02-22T00:00:00',
        updated_at: '2026-02-22T00:00:00',
        account_code: '',
        ...overrides,
    };
}

describe('normalizeDbTransaction — transaction type', () => {
    it('maps RECEIVE -> invoice and SPEND -> bill', () => {
        expect(normalizeDbTransaction(makeRaw({ transaction_type: 'RECEIVE' }), 'g', true).sourceType).toBe('invoice');
        expect(normalizeDbTransaction(makeRaw({ transaction_type: 'SPEND' }), 'g', true).sourceType).toBe('bill');
    });

    it('collapses Xero compound types to the correct direction (regression)', () => {
        // These previously fell through to the default and were mislabeled.
        expect(normalizeDbTransaction(makeRaw({ transaction_type: 'RECEIVE-OVERPAYMENT' }), 'g', true).sourceType).toBe('invoice');
        expect(normalizeDbTransaction(makeRaw({ transaction_type: 'SPEND-PREPAYMENT' }), 'g', true).sourceType).toBe('bill');
        expect(normalizeDbTransaction(makeRaw({ transaction_type: 'SPEND-TRANSFER' }), 'g', true).sourceType).toBe('bill');
    });

    it('maps economic RECEIVE/SPEND and journal', () => {
        expect(normalizeDbTransaction(makeRaw({ transaction_type: 'receive' }), 'g', true).sourceType).toBe('invoice');
        expect(normalizeDbTransaction(makeRaw({ transaction_type: 'journal' }), 'g', true).sourceType).toBe('journal');
    });
});

describe('normalizeDbTransaction — provider / sourceSystem', () => {
    it('maps each known provider explicitly', () => {
        expect(normalizeDbTransaction(makeRaw({ provider: 'xero' }), 'g', true).sourceSystem).toBe('xero');
        expect(normalizeDbTransaction(makeRaw({ provider: 'economic' }), 'g', true).sourceSystem).toBe('economic');
        expect(normalizeDbTransaction(makeRaw({ provider: 'quickbooks' }), 'g', true).sourceSystem).toBe('quickbooks');
    });

    it('defaults unknown provider to xero with a warning', () => {
        const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
        expect(normalizeDbTransaction(makeRaw({ provider: 'sage' }), 'g', true).sourceSystem).toBe('xero');
        expect(warn).toHaveBeenCalled();
        warn.mockRestore();
    });
});

describe('normalizeDbTransaction — amount safety', () => {
    it('takes the absolute value', () => {
        expect(normalizeDbTransaction(makeRaw({ amount: -75000 }), 'g', true).amount).toBe(75000);
    });

    it('parses numeric strings from the DB (numeric column)', () => {
        expect(normalizeDbTransaction(makeRaw({ amount: '85000.00' }), 'g', true).amount).toBe(85000);
    });

    it('coerces null/garbage amount to 0 instead of NaN', () => {
        const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
        expect(normalizeDbTransaction(makeRaw({ amount: null as unknown as number }), 'g', true).amount).toBe(0);
        expect(normalizeDbTransaction(makeRaw({ amount: 'not-a-number' }), 'g', true).amount).toBe(0);
        warn.mockRestore();
    });
});

describe('normalizeDbTransaction — date safety', () => {
    it('parses a valid date', () => {
        const tx = normalizeDbTransaction(makeRaw({ transaction_date: '2026-02-22T00:00:00' }), 'g', true);
        expect(tx.date.getUTCFullYear()).toBe(2026);
    });

    it('falls back to the epoch on an invalid date instead of Invalid Date', () => {
        const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
        const tx = normalizeDbTransaction(makeRaw({ transaction_date: 'garbage' }), 'g', true);
        expect(Number.isNaN(tx.date.getTime())).toBe(false);
        expect(tx.date.getTime()).toBe(0);
        warn.mockRestore();
    });
});

describe('normalizeDbTransaction — field hygiene', () => {
    it('uppercases/trims currency and defaults empties', () => {
        expect(normalizeDbTransaction(makeRaw({ currency: ' dkk ' }), 'g', true).currency).toBe('DKK');
    });

    it('handles null description/contact and empty account_code without throwing', () => {
        const tx = normalizeDbTransaction(makeRaw({ description: null, contact_name: null, account_code: '' }), 'g', true);
        expect(tx.description).toBe('');
        expect(tx.contactName).toBe('');
    });

    it('parses raw_payload JSON, tolerating malformed JSON', () => {
        const good = normalizeDbTransaction(makeRaw({ raw_payload: '{"Type":"RECEIVE"}' }), 'g', true);
        expect(good.rawData).toEqual({ Type: 'RECEIVE' });
        const bad = normalizeDbTransaction(makeRaw({ raw_payload: '{not json' }), 'g', true);
        expect(bad.rawData).toEqual({});
    });
});
