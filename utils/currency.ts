// ============================================================
// Quoryx Matching Engine — Currency Utilities
// Phase 2 stub. For MVP, only detects cross-currency pairs.
// ============================================================

/**
 * Check if two transactions use different currencies.
 * When currencies differ, the amount dimension cannot be scored
 * and the pair requires manual review.
 *
 * FX conversion is planned for Phase 2.
 *
 * @param currencyA - ISO 4217 currency code (e.g. 'USD')
 * @param currencyB - ISO 4217 currency code (e.g. 'GBP')
 * @returns true if the currencies are different
 */
export function isCrossCurrency(currencyA: string, currencyB: string): boolean {
    const a = currencyA.trim().toUpperCase();
    const b = currencyB.trim().toUpperCase();

    if (a !== b) {
        console.log(
            `Cross-currency pair detected (${a}/${b}) — manual review required. FX conversion coming in Phase 2.`
        );
        return true;
    }

    return false;
}
