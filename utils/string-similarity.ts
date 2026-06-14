// ============================================================
// Quoryx Matching Engine — String Similarity
// Levenshtein distance implementation from scratch. No external libs.
// ============================================================

/**
 * Common legal suffixes to strip before comparison.
 * Removing these improves matching accuracy for company names.
 */
const LEGAL_SUFFIXES = [
    'ltd', 'llc', 'inc', 'corp', 'limited', 'corporation',
    'pty', 'plc', 'gmbh', 'ag', 'sa', 'srl',
];

/**
 * Normalize a string for comparison:
 * - Trim whitespace
 * - Lowercase
 * - Remove common legal suffixes
 */
function normalize(str: string): string {
    let result = str.trim().toLowerCase();

    // Remove legal suffixes anywhere in the string (word-boundary match, optional trailing dot)
    for (const suffix of LEGAL_SUFFIXES) {
        const pattern = new RegExp(`\\b${suffix}\\.?\\b`, 'gi');
        result = result.replace(pattern, '');
    }

    // Collapse multiple spaces and trim
    result = result.replace(/\s+/g, ' ').trim();

    return result;
}

/**
 * Compute the Levenshtein (edit) distance between two strings.
 * Uses the classic dynamic-programming matrix approach.
 *
 * @param str1 - First string (raw, will be normalized)
 * @param str2 - Second string (raw, will be normalized)
 * @returns The minimum number of single-character edits (insertions, deletions, substitutions)
 */
export function levenshteinDistance(str1: string, str2: string): number {
    const a = normalize(str1);
    const b = normalize(str2);

    // Fast-path: identical after normalization
    if (a === b) return 0;

    const m = a.length;
    const n = b.length;

    // Edge cases: one or both strings empty
    if (m === 0) return n;
    if (n === 0) return m;

    // Build distance matrix — only need two rows at a time
    let prevRow = new Array<number>(n + 1);
    let currRow = new Array<number>(n + 1);

    // Initialize first row: distance from empty string to b[0..j]
    for (let j = 0; j <= n; j++) {
        prevRow[j] = j;
    }

    for (let i = 1; i <= m; i++) {
        currRow[0] = i;

        for (let j = 1; j <= n; j++) {
            const cost = a[i - 1] === b[j - 1] ? 0 : 1;

            currRow[j] = Math.min(
                prevRow[j]! + 1,        // deletion
                currRow[j - 1]! + 1,    // insertion
                prevRow[j - 1]! + cost  // substitution
            );
        }

        // Swap rows
        [prevRow, currRow] = [currRow, prevRow];
    }

    return prevRow[n]!;
}

/**
 * Compute token-based overlap similarity.
 * Measures how many tokens from the shorter string appear in the longer string.
 * Effective for company names where one may be a superset of the other
 * (e.g. "ABC Corp USA" vs "ABC Corp" → "abc usa" vs "abc").
 */
function tokenOverlap(a: string, b: string): number {
    const tokensA = a.split(/\s+/).filter(t => t.length > 0);
    const tokensB = b.split(/\s+/).filter(t => t.length > 0);

    if (tokensA.length === 0 && tokensB.length === 0) return 1.0;
    if (tokensA.length === 0 || tokensB.length === 0) return 0.0;

    // Count matches from the shorter set against the longer set
    const [shorter, longer] = tokensA.length <= tokensB.length
        ? [tokensA, tokensB] : [tokensB, tokensA];

    let matches = 0;
    for (const token of shorter) {
        if (longer.includes(token)) {
            matches++;
        }
    }

    return matches / shorter.length;
}

/**
 * Compute string similarity as a ratio between 0.0 and 1.0.
 * Uses the maximum of two metrics:
 * 1. Levenshtein distance normalized by the longer string length
 * 2. Token overlap — fraction of shorter string's tokens found in longer string
 *
 * Inputs are normalized before comparison:
 * - Trimmed and lowercased
 * - Common legal suffixes (Ltd, LLC, Inc, Corp, Limited) are stripped
 *
 * @param str1 - First string
 * @param str2 - Second string
 * @returns Similarity ratio: 1.0 = identical, 0.0 = completely different
 */
export function stringSimilarity(str1: string, str2: string): number {
    const a = normalize(str1);
    const b = normalize(str2);

    // Both empty after normalization → identical
    if (a.length === 0 && b.length === 0) return 1.0;

    // One empty → no similarity
    if (a.length === 0 || b.length === 0) return 0.0;

    // Metric 1: Levenshtein-based similarity
    const distance = levenshteinDistance(str1, str2);
    const maxLen = Math.max(a.length, b.length);
    const levenshteinSim = 1.0 - distance / maxLen;

    // Metric 2: Token overlap similarity
    const tokenSim = tokenOverlap(a, b);

    return Math.max(levenshteinSim, tokenSim);
}

