// ============================================================
// Quoryx Matching Engine — Data Normalizer
// Converts raw Xero (and future QuickBooks) API responses into
// the internal Transaction type. This is the ONLY file that knows
// about external API shapes. Everything else uses Transaction.
// ============================================================

import { Transaction, SourceType } from './types';
import { randomUUID } from 'crypto';

// ============================================================
// Xero API Response Types
// Defined here because they describe external shapes, not our domain.
// ============================================================

/** Xero Contact object (subset of fields we use) */
export interface XeroContact {
    ContactID?: string;
    Name?: string;
}

/** Xero LineItem object (subset of fields we use) */
export interface XeroLineItem {
    Description?: string;
    LineAmount?: number;
    UnitAmount?: number;
    Quantity?: number;
}

/**
 * Raw Xero Invoice/Bill API response shape.
 * Used for both invoices (Type = 'ACCREC') and bills (Type = 'ACCPAY').
 * See: https://developer.xero.com/documentation/api/accounting/invoices
 */
export interface XeroInvoice {
    InvoiceID?: string;
    InvoiceNumber?: string;
    Reference?: string;
    Type?: string;               // 'ACCREC' (invoice) or 'ACCPAY' (bill)
    Contact?: XeroContact;
    DateString?: string;         // ISO 8601 format: '2026-02-01T00:00:00'
    Date?: string;               // Xero date format: '/Date(1706745600000+0000)/'
    DueDate?: string;
    Total?: number;
    SubTotal?: number;
    TotalTax?: number;
    AmountDue?: number;
    AmountPaid?: number;
    AmountCredited?: number;
    CurrencyCode?: string;
    Status?: string;
    LineItems?: XeroLineItem[];
    [key: string]: unknown;     // Preserve unknown fields in rawData
}

// ============================================================
// Date Parsing
// ============================================================

/**
 * Parse a Xero date string into a JS Date object normalized to UTC.
 *
 * Xero returns dates in multiple formats:
 * - `/Date(1706745600000+0000)/`  — timestamp + offset
 * - `/Date(1706745600000)/`       — timestamp only
 * - `2026-02-01T00:00:00`        — ISO 8601
 *
 * Falls back to current date if parsing fails.
 */
function parseXeroDate(dateStr: string | undefined | null): Date {
    if (!dateStr) return new Date();

    // Format 1: /Date(timestamp+offset)/ or /Date(timestamp)/
    const msMatch = dateStr.match(/\/Date\((\d+)([+-]\d{4})?\)\//);
    if (msMatch) {
        const timestamp = parseInt(msMatch[1]!, 10);
        return new Date(timestamp);
    }

    // Format 2: ISO 8601 string
    const parsed = new Date(dateStr);
    if (!isNaN(parsed.getTime())) {
        return parsed;
    }

    // Fallback: current date
    return new Date();
}

// ============================================================
// Amount Parsing
// ============================================================

/**
 * Extract a positive numeric amount from a Xero invoice.
 * Tries Total first, then SubTotal, then sums LineItems.
 * Always returns `Math.abs` — direction is encoded in sourceType, not amount.
 */
function parseAmount(raw: XeroInvoice): number {
    if (raw.Total != null && !isNaN(Number(raw.Total))) {
        return Math.abs(Number(raw.Total));
    }
    if (raw.SubTotal != null && !isNaN(Number(raw.SubTotal))) {
        return Math.abs(Number(raw.SubTotal));
    }

    // Sum LineItem amounts as fallback
    if (raw.LineItems && raw.LineItems.length > 0) {
        let sum = 0;
        for (const item of raw.LineItems) {
            if (item.LineAmount != null) {
                sum += Math.abs(Number(item.LineAmount));
            }
        }
        if (sum > 0) return sum;
    }

    return 0;
}

// ============================================================
// Field Extraction Helpers
// ============================================================

/**
 * Extract the currency code. Uppercase, defaults to 'USD' if missing/empty.
 */
function parseCurrency(raw: XeroInvoice): string {
    const code = raw.CurrencyCode?.trim();
    return code ? code.toUpperCase() : 'USD';
}

/**
 * Extract the reference (invoice/bill number).
 * Tries InvoiceNumber first, then Reference.
 */
function parseReference(raw: XeroInvoice): string {
    if (raw.InvoiceNumber?.trim()) return raw.InvoiceNumber.trim();
    if (raw.Reference?.trim()) return raw.Reference.trim();
    return '';
}

/**
 * Extract the description.
 * Uses lineItems[0].description as fallback if reference is empty.
 */
function parseDescription(raw: XeroInvoice): string {
    // Primary: Reference field as description context
    if (raw.Reference?.trim()) return raw.Reference.trim();

    // Fallback: first line item description
    if (raw.LineItems && raw.LineItems.length > 0) {
        const firstDesc = raw.LineItems[0]?.Description?.trim();
        if (firstDesc) return firstDesc;
    }

    return '';
}

/**
 * Extract contact name. Trim whitespace, preserve original casing.
 */
function parseContactName(raw: XeroInvoice): string {
    return raw.Contact?.Name?.trim() ?? '';
}

/**
 * Extract contact ID from source system. May be null/undefined.
 */
function parseContactId(raw: XeroInvoice): string {
    return raw.Contact?.ContactID?.trim() ?? '';
}

/**
 * Extract the Xero source ID (InvoiceID).
 */
function parseSourceId(raw: XeroInvoice): string {
    return raw.InvoiceID?.trim() ?? '';
}

/**
 * Extract entity name from the raw data or use entityId as fallback.
 * Xero doesn't include the entity name in the invoice response —
 * it's typically resolved from the entity metadata at a higher level.
 * If the caller supplies entityName in the raw data, we'll use it.
 */
function parseEntityName(raw: XeroInvoice, entityId: string): string {
    // Check if entityName was injected into the raw data by the caller
    if (typeof raw['entityName'] === 'string' && raw['entityName'].trim()) {
        return (raw['entityName'] as string).trim();
    }
    return entityId;
}

// ============================================================
// Core Normalization
// ============================================================

/**
 * Internal shared normalizer. Both invoice and bill normalization
 * follow the same logic — only the sourceType differs.
 */
function normalizeXeroTransaction(
    raw: XeroInvoice,
    entityId: string,
    entityGroupId: string,
    sourceType: SourceType
): Transaction {
    return {
        id: randomUUID(),
        entityId,
        entityName: parseEntityName(raw, entityId),
        entityGroupId,
        sourceSystem: 'xero',
        sourceId: parseSourceId(raw),
        sourceType,
        date: parseXeroDate(raw.Date ?? raw.DateString),
        amount: parseAmount(raw),
        currency: parseCurrency(raw),
        description: parseDescription(raw),
        reference: parseReference(raw),
        contactName: parseContactName(raw),
        contactId: parseContactId(raw),
        isIntercompany: false, // Set later by detector.ts
        rawData: raw as Record<string, unknown>,
    };
}

// ============================================================
// Public API
// ============================================================

/**
 * Normalize a raw Xero invoice (Accounts Receivable) into the
 * internal Transaction type.
 *
 * @param raw - Raw Xero API invoice response
 * @param entityId - Quoryx entity ID this transaction belongs to
 * @param entityGroupId - Quoryx group ID for this entity
 * @returns Normalized Transaction with sourceType = 'invoice'
 */
export function normalizeXeroInvoice(
    raw: XeroInvoice,
    entityId: string,
    entityGroupId: string
): Transaction {
    return normalizeXeroTransaction(raw, entityId, entityGroupId, 'invoice');
}

/**
 * Normalize a raw Xero bill (Accounts Payable) into the
 * internal Transaction type.
 *
 * @param raw - Raw Xero API bill response
 * @param entityId - Quoryx entity ID this transaction belongs to
 * @param entityGroupId - Quoryx group ID for this entity
 * @returns Normalized Transaction with sourceType = 'bill'
 */
export function normalizeXeroBill(
    raw: XeroInvoice,
    entityId: string,
    entityGroupId: string
): Transaction {
    return normalizeXeroTransaction(raw, entityId, entityGroupId, 'bill');
}
