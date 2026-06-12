// ============================================================
// Quoryx Matching Engine — LLM Fallback Matcher
// Async function: calls Claude API for ambiguous pairs.
// Caches results so the same pair is never evaluated twice.
// ============================================================

import Anthropic from '@anthropic-ai/sdk';
import { Transaction, LLMEvaluation } from '../data/types';

/**
 * Create a fresh LLM evaluation cache.
 * Engine.ts instantiates one cache per matching run.
 */
export function buildLLMCache(): Map<string, LLMEvaluation> {
    return new Map<string, LLMEvaluation>();
}

/**
 * Format a Date as YYYY-MM-DD for the LLM prompt.
 */
function formatDate(date: Date): string {
    return date.toISOString().slice(0, 10);
}

/**
 * Safely parse the LLM response text into an LLMEvaluation.
 * Strips accidental markdown fences before parsing.
 */
function parseResponse(text: string): LLMEvaluation {
    // Strip markdown fences if present
    let cleaned = text.trim();
    if (cleaned.startsWith('```')) {
        cleaned = cleaned.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
    }

    const parsed = JSON.parse(cleaned);

    return {
        isMatch: Boolean(parsed.isMatch),
        confidence: Number(parsed.confidence),
        reasoning: String(parsed.reasoning),
    };
}

/**
 * Build the system + user prompt for the LLM evaluation.
 */
function buildPrompt(txA: Transaction, txB: Transaction): string {
    return [
        'You are a chartered accountant reviewing intercompany transactions for a group close.',
        'Determine if these two transactions are the same intercompany event recorded from both sides.',
        '',
        'Transaction A:',
        `  Entity: ${txA.entityName}`,
        `  Type: ${txA.sourceType}`,
        `  Date: ${formatDate(txA.date)}`,
        `  Amount: ${txA.currency} ${txA.amount.toFixed(2)}`,
        `  Description: ${txA.description}`,
        `  Reference: ${txA.reference}`,
        `  Contact: ${txA.contactName}`,
        '',
        'Transaction B:',
        `  Entity: ${txB.entityName}`,
        `  Type: ${txB.sourceType}`,
        `  Date: ${formatDate(txB.date)}`,
        `  Amount: ${txB.currency} ${txB.amount.toFixed(2)}`,
        `  Description: ${txB.description}`,
        `  Reference: ${txB.reference}`,
        `  Contact: ${txB.contactName}`,
        '',
        'Respond with ONLY a JSON object. No markdown. No explanation outside the JSON.',
        '',
        'Required shape:',
        '{',
        '  "isMatch": boolean,',
        '  "confidence": number,  // 0.0 to 1.0',
        '  "reasoning": string    // plain English, shown to accountant in UI',
        '}',
    ].join('\n');
}

/**
 * Evaluate an ambiguous transaction pair using Claude.
 *
 * - Checks cache first — same pair is never evaluated twice.
 * - Builds a dynamic prompt from transaction fields.
 * - Parses the JSON response safely with fallback.
 * - Never throws — always returns a valid LLMEvaluation.
 *
 * @param txA - First transaction
 * @param txB - Second transaction
 * @param cache - Session-scoped evaluation cache
 * @returns LLMEvaluation result (from cache or fresh API call)
 */
export async function evaluateWithLLM(
    txA: Transaction,
    txB: Transaction,
    cache: Map<string, LLMEvaluation>
): Promise<LLMEvaluation> {
    // Deterministic pair key — order-independent
    const pairId = [txA.id, txB.id].sort().join('::');

    // Cache hit → return immediately
    const cached = cache.get(pairId);
    if (cached) {
        return cached;
    }

    // Fallback for failed evaluations
    const fallback: LLMEvaluation = {
        isMatch: false,
        confidence: 0,
        reasoning: 'LLM response could not be parsed — manual review required.',
    };

    try {
        const client = new Anthropic();

        const message = await client.messages.create({
            model: 'claude-sonnet-4-20250514',
            max_tokens: 500,
            messages: [
                {
                    role: 'user',
                    content: buildPrompt(txA, txB),
                },
            ],
        });

        // Extract text from the first content block
        const block = message.content[0];
        if (!block || block.type !== 'text') {
            cache.set(pairId, fallback);
            return fallback;
        }

        const result = parseResponse(block.text);
        cache.set(pairId, result);
        return result;
    } catch {
        cache.set(pairId, fallback);
        return fallback;
    }
}
