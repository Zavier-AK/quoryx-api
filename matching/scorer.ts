// ============================================================
// Quoryx Matching Engine — Scoring Engine
// Pure function: no async, no I/O, no side effects.
// Scores a candidate pair across 4 dimensions.
// ============================================================

import { Transaction, MatchCandidate, ContactMapping } from '../data/types';
import { stringSimilarity } from '../utils/string-similarity';
import { isCrossCurrency } from '../utils/currency';

// ============================================================
// Counterparty Normalization — Substring Check Only
// ============================================================

/**
 * Suffixes stripped before substring comparison so that
 * suffix-only differences (e.g. "Corp", "Group") defer to fuzzy
 * matching instead of triggering the substring tier.
 */
const COMPANY_SUFFIXES = [
    'ltd', 'llc', 'inc', 'corp', 'limited', 'corporation',
    'pty', 'plc', 'gmbh', 'ag', 'sa', 'srl', 'group', 'co', 'company',
];

/**
 * Strip a trailing company suffix from names with 3+ words.
 * Only strips the last word to avoid over-normalizing short names
 * (e.g. "Alpha Group" stays as-is because it has only 2 words).
 */
function normalizeForSubstringCheck(name: string): string {
    const result = name.toLowerCase().trim();
    const words = result.split(/\s+/);

    if (words.length >= 3) {
        const lastWord = words[words.length - 1]!.replace(/\.$/, '');
        if (COMPANY_SUFFIXES.includes(lastWord)) {
            words.pop();
            return words.join(' ');
        }
    }

    return result;
}

// ============================================================
// Dimension 1: Amount (max 0.40)
// ============================================================

function scoreAmount(
    txA: Transaction,
    txB: Transaction
): { score: number; difference: number; crossCurrency: boolean; reason: string } {
    // Cross-currency → 0.00
    if (isCrossCurrency(txA.currency, txB.currency)) {
        return {
            score: 0.00,
            difference: Math.abs(txA.amount - txB.amount),
            crossCurrency: true,
            reason: '',
        };
    }

    const difference = Math.abs(txA.amount - txB.amount);
    const percentDiff = (difference / txA.amount) * 100;

    let score: number;
    let reason: string;

    if (percentDiff === 0) {
        score = 0.40;
        reason = `Exact amount match (${txA.currency} ${txA.amount.toFixed(2)})`;
    } else if (percentDiff <= 0.5) {
        score = 0.38;
        reason = `Amount within 0.5% — difference: ${txA.currency} ${difference.toFixed(2)}`;
    } else if (percentDiff <= 1.0) {
        score = 0.35;
        reason = `Amount within 1.0% — difference: ${txA.currency} ${difference.toFixed(2)}`;
    } else if (percentDiff <= 2.0) {
        score = 0.30;
        reason = `Amount within 2.0% — difference: ${txA.currency} ${difference.toFixed(2)}`;
    } else {
        score = 0.00;
        reason = '';
    }

    return { score, difference, crossCurrency: false, reason };
}

// ============================================================
// Dimension 2: Date (max 0.30)
// ============================================================

function scoreDate(
    txA: Transaction,
    txB: Transaction
): { score: number; daysDiff: number; reason: string } {
    const msPerDay = 86_400_000;
    const daysDiff = Math.round(
        Math.abs(txA.date.getTime() - txB.date.getTime()) / msPerDay
    );

    let score: number;
    let reason: string;

    if (daysDiff === 0) {
        score = 0.30;
        reason = 'Same date';
    } else if (daysDiff <= 7) {
        score = 0.28;
        reason = `Within 7 days (${daysDiff} day${daysDiff === 1 ? '' : 's'} apart)`;
    } else if (daysDiff <= 14) {
        score = 0.25;
        reason = `Within 14 days (${daysDiff} days apart)`;
    } else if (daysDiff <= 30) {
        score = 0.20;
        reason = `Within 30 days (${daysDiff} days apart)`;
    } else {
        score = 0.00;
        reason = '';
    }

    return { score, daysDiff, reason };
}

// ============================================================
// Dimension 3: Transaction Type (max 0.20)
// ============================================================

function scoreType(
    txA: Transaction,
    txB: Transaction
): { score: number; reason: string } {
    const a = txA.sourceType;
    const b = txB.sourceType;

    // Invoice ↔ Bill (either order)
    if ((a === 'invoice' && b === 'bill') || (a === 'bill' && b === 'invoice')) {
        return { score: 0.20, reason: 'Invoice ↔ Bill pair' };
    }

    // Journal ↔ Journal
    if (a === 'journal' && b === 'journal') {
        return { score: 0.15, reason: 'Journal ↔ Journal pair' };
    }

    // Same direction or other
    return { score: 0.00, reason: '' };
}

// ============================================================
// Dimension 4: Counterparty (max 0.10)
// ============================================================

function scoreCounterparty(
    txA: Transaction,
    txB: Transaction,
    contactMappings: ContactMapping[]
): { score: number; reason: string } {
    // Priority 1: ContactMapping lookup
    // Check if txA.contactId maps to txB's entity, or txB.contactId maps to txA's entity
    for (const mapping of contactMappings) {
        if (
            mapping.contactId === txA.contactId &&
            mapping.mapsToEntityId === txB.entityId
        ) {
            return { score: 0.10, reason: 'Confirmed ContactMapping match' };
        }
        if (
            mapping.contactId === txB.contactId &&
            mapping.mapsToEntityId === txA.entityId
        ) {
            return { score: 0.10, reason: 'Confirmed ContactMapping match' };
        }
    }

    // Priority 2: Exact name match (case-insensitive, trimmed)
    const contactA = txA.contactName.toLowerCase().trim();
    const contactB = txB.contactName.toLowerCase().trim();
    const entityNameA = txA.entityName.toLowerCase().trim();
    const entityNameB = txB.entityName.toLowerCase().trim();

    if (contactA === entityNameB || contactB === entityNameA) {
        return { score: 0.10, reason: 'Exact counterparty name match' };
    }

    // Priority 3: Substring containment (case-insensitive)
    // Normalize to strip common company suffixes so that suffix-only
    // differences (e.g. "Corp", "Group") defer to the fuzzy tier.
    const normContactA = normalizeForSubstringCheck(txA.contactName);
    const normEntityB = normalizeForSubstringCheck(txB.entityName);
    const normContactB = normalizeForSubstringCheck(txB.contactName);
    const normEntityA = normalizeForSubstringCheck(txA.entityName);

    if (
        (normContactA !== normEntityB &&
            (normContactA.includes(normEntityB) || normEntityB.includes(normContactA))) ||
        (normContactB !== normEntityA &&
            (normContactB.includes(normEntityA) || normEntityA.includes(normContactB)))
    ) {
        return { score: 0.09, reason: 'Substring counterparty name match' };
    }

    // Priority 4: Fuzzy match (Levenshtein similarity >= 0.80)
    const simAtoB = stringSimilarity(txA.contactName, txB.entityName);
    const simBtoA = stringSimilarity(txB.contactName, txA.entityName);

    if (simAtoB >= 0.80 || simBtoA >= 0.80) {
        const bestSim = Math.max(simAtoB, simBtoA);
        return { score: 0.08, reason: `Fuzzy counterparty match (similarity: ${bestSim.toFixed(2)})` };
    }

    // No match
    return { score: 0.00, reason: '' };
}

// ============================================================
// Match Type Classification
// ============================================================

function classifyMatch(confidenceScore: number): 'exact' | 'fuzzy' {
    return confidenceScore >= 0.95 ? 'exact' : 'fuzzy';
}

// ============================================================
// Public API
// ============================================================

/**
 * Score a candidate pair across all 4 dimensions.
 * Pure function — no async, no I/O, no side effects.
 *
 * @param txA - First transaction
 * @param txB - Second transaction
 * @param contactMappings - Confirmed counterparty mappings
 * @returns Scored MatchCandidate
 */
export function scoreCandidate(
    txA: Transaction,
    txB: Transaction,
    contactMappings: ContactMapping[]
): MatchCandidate {
    const amount = scoreAmount(txA, txB);
    const date = scoreDate(txA, txB);
    const type = scoreType(txA, txB);
    const counterparty = scoreCounterparty(txA, txB, contactMappings);

    // Sum and round to 4 decimal places
    const confidenceScore = Math.round(
        (amount.score + date.score + type.score + counterparty.score) * 10000
    ) / 10000;

    // Build reasons array — only non-empty reasons
    const reasons: string[] = [];
    if (amount.reason) reasons.push(amount.reason);
    if (date.reason) reasons.push(date.reason);
    if (type.reason) reasons.push(type.reason);
    if (counterparty.reason) reasons.push(counterparty.reason);

    return {
        transactionA: txA,
        transactionB: txB,
        amountScore: amount.score,
        dateScore: date.score,
        typeScore: type.score,
        counterpartyScore: counterparty.score,
        confidenceScore,
        matchType: classifyMatch(confidenceScore),
        amountDifference: amount.difference,
        daysDifference: date.daysDiff,
        reasons,
        isCrossCurrency: amount.crossCurrency,
        llmReasoning: null,
    };
}
