// ============================================================
// Quoryx Matching Engine — Intercompany Detection
// Filters transactions to identify intercompany activity.
// Pure function: no async, no I/O, no side effects.
// ============================================================

import { Transaction, EntityGroup, ContactMapping } from '../data/types';
import { stringSimilarity } from '../utils/string-similarity';

/**
 * Detect which transactions are intercompany by checking each
 * transaction's contact against other entities in the same group.
 *
 * Returns a NEW array — original transactions are never mutated.
 *
 * Detection runs 4 checks in strict priority order (stops at first match):
 * 1. ContactMapping lookup
 * 2. Exact name match
 * 3. Substring match
 * 4. Fuzzy match (stringSimilarity >= 0.80)
 *
 * @param transactions - All transactions to evaluate
 * @param entityGroup - The entity group containing all related entities
 * @param contactMappings - Confirmed counterparty mappings
 * @returns New array with isIntercompany set correctly on each transaction
 */
export function detectIntercompany(
    transactions: Transaction[],
    entityGroup: EntityGroup,
    contactMappings: ContactMapping[]
): Transaction[] {
    // Guard: single-entity group — no intercompany pairs possible
    if (entityGroup.entities.length <= 1) {
        return transactions.map(tx => ({ ...tx, isIntercompany: false }));
    }

    // Build set of entity IDs in this group for membership checks
    const groupEntityIds = new Set(entityGroup.entities.map(e => e.id));

    return transactions.map(tx => {
        const copy = { ...tx };

        // Guard: empty or whitespace-only contactName
        if (!tx.contactName || tx.contactName.trim() === '') {
            copy.isIntercompany = false;
            return copy;
        }

        // Other entities in the group (excluding the transaction's own entity)
        const otherEntities = entityGroup.entities.filter(e => e.id !== tx.entityId);

        // --- Check 1: ContactMapping lookup ---
        for (const mapping of contactMappings) {
            if (
                mapping.contactId === tx.contactId &&
                mapping.mapsToEntityId !== tx.entityId &&
                groupEntityIds.has(mapping.mapsToEntityId)
            ) {
                copy.isIntercompany = true;
                return copy;
            }
        }

        // --- Check 2: Exact name match ---
        const contactNameLower = tx.contactName.toLowerCase().trim();
        for (const entity of otherEntities) {
            if (contactNameLower === entity.name.toLowerCase().trim()) {
                copy.isIntercompany = true;
                return copy;
            }
        }

        // --- Check 3: Substring match ---
        const contactNameLowerSub = tx.contactName.toLowerCase();
        for (const entity of otherEntities) {
            const entityNameLower = entity.name.toLowerCase();
            if (
                contactNameLowerSub.includes(entityNameLower) ||
                entityNameLower.includes(contactNameLowerSub)
            ) {
                copy.isIntercompany = true;
                return copy;
            }
        }

        // --- Check 4: Fuzzy match (stringSimilarity >= 0.80) ---
        for (const entity of otherEntities) {
            if (stringSimilarity(tx.contactName, entity.name) >= 0.80) {
                copy.isIntercompany = true;
                return copy;
            }
        }

        // No match — not intercompany
        copy.isIntercompany = false;
        return copy;
    });
}
