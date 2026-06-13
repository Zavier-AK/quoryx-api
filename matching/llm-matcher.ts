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

// Current Sonnet. The previous pin (claude-sonnet-4-20250514) retires 2026-06-15.
const LLM_MODEL = 'claude-sonnet-4-6';

// Output schema enforced server-side via structured outputs, so the response is
// guaranteed to be valid JSON in this shape — no markdown-fence stripping needed.
const RESPONSE_SCHEMA = {
    type: 'object',
    properties: {
        isMatch: { type: 'boolean' },
        confidence: { type: 'number' }, // 0.0–1.0; clamped in code (schema can't bound numbers)
        reasoning: { type: 'string' }, // plain English, shown to the accountant in the UI
    },
    required: ['isMatch', 'confidence', 'reasoning'],
    additionalProperties: false,
} as const;

// Stable instruction block — identical on every call, so it sits in the cacheable
// system prefix (volatile per-pair data goes in the user turn). Caching activates
// once this prefix exceeds Sonnet's ~2048-token minimum — e.g. when confirmed-match
// few-shot examples are added here — so the structure is forward-looking.
const SYSTEM_PROMPT =
    'You are a chartered accountant reviewing intercompany transactions for a group close. ' +
    'You are given two transactions recorded in different entities. Decide whether they are the ' +
    'same intercompany event seen from both sides (one entity\'s sale is the other\'s purchase). ' +
    'Weigh amount, date proximity, direction (invoice vs bill), and counterparty against normal ' +
    'SMB timing and FX differences. Return your verdict, a 0.0–1.0 confidence, and a one-line ' +
    'plain-English reason an accountant can act on.';

/**
 * Coerce the structured-output JSON into an LLMEvaluation, clamping confidence.
 */
function parseResponse(text: string): LLMEvaluation {
    const parsed = JSON.parse(text);
    const confidence = Number(parsed.confidence);
    return {
        isMatch: Boolean(parsed.isMatch),
        confidence: Number.isFinite(confidence) ? Math.max(0, Math.min(1, confidence)) : 0,
        reasoning: String(parsed.reasoning ?? ''),
    };
}

/**
 * Build the per-pair user message — only the volatile transaction data.
 */
function buildUserMessage(txA: Transaction, txB: Transaction): string {
    return [
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
            model: LLM_MODEL,
            max_tokens: 500,
            // Stable prefix → cacheable system block; volatile data → user turn.
            system: [
                {
                    type: 'text',
                    text: SYSTEM_PROMPT,
                    cache_control: { type: 'ephemeral' },
                },
            ],
            // Structured outputs: response is guaranteed to match RESPONSE_SCHEMA.
            output_config: {
                format: { type: 'json_schema', schema: RESPONSE_SCHEMA },
            },
            messages: [
                {
                    role: 'user',
                    content: buildUserMessage(txA, txB),
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
    } catch (err) {
        // Never throw — but surface the cause so a silent prod failure (e.g. an
        // API rejection of the request shape) is visible in logs, not invisible.
        console.warn(`LLM evaluation failed for pair ${pairId}:`, err);
        cache.set(pairId, fallback);
        return fallback;
    }
}
