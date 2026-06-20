"""
Quoryx Matching Engine — Python Scoring Port

Faithful Python port of matching/scorer.ts. Scores a candidate intercompany
pair across 4 dimensions. Pure functions: no I/O, no side effects.

The TypeScript engine works on normalized "invoice"/"bill" source types. In this
backend the Transaction.transaction_type values are the raw provider directions
"SPEND" and "RECEIVE", where (per data/db-normalizer.ts) RECEIVE -> invoice and
SPEND -> bill. The opposite-direction pair (SPEND<->RECEIVE) therefore mirrors the
scorer's "invoice <-> bill" rule.

Scoring dimensions (must match scorer.ts exactly):
  - Amount        max 0.40
  - Date          max 0.30
  - Type          max 0.20
  - Counterparty  max 0.10

Python 3.9 compatible: typing.Optional / typing.List / typing.Dict only,
no PEP-604 unions or builtin generics in import-time annotations.
"""

from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Counterparty normalization — substring check only (mirrors scorer.ts)
# ---------------------------------------------------------------------------

# Suffixes stripped before substring comparison so suffix-only differences
# (e.g. "Corp", "Group") defer to fuzzy matching instead of the substring tier.
COMPANY_SUFFIXES = {
    "ltd", "llc", "inc", "corp", "limited", "corporation",
    "pty", "plc", "gmbh", "ag", "sa", "srl", "group", "co", "company",
}


def _normalize_for_substring_check(name: str) -> str:
    """Strip a trailing company suffix from names with 3+ words.

    Only strips the last word to avoid over-normalizing short names
    (e.g. "Alpha Group" stays as-is because it has only 2 words).
    """
    result = (name or "").lower().strip()
    words = result.split()

    if len(words) >= 3:
        last_word = words[-1].rstrip(".")
        if last_word in COMPANY_SUFFIXES:
            words.pop()
            return " ".join(words)

    return result


def _is_cross_currency(currency_a: Optional[str], currency_b: Optional[str]) -> bool:
    """True if the two currency codes differ (case/whitespace-insensitive)."""
    a = (currency_a or "").strip().upper()
    b = (currency_b or "").strip().upper()
    return a != b


def _string_similarity(a: str, b: str) -> float:
    """Fuzzy similarity ratio in [0, 1] using difflib.SequenceMatcher.

    Compared case-insensitively/trimmed to mirror the spirit of the TS
    stringSimilarity (normalized Levenshtein) used in scorer.ts.
    """
    sa = (a or "").lower().strip()
    sb = (b or "").lower().strip()
    if not sa and not sb:
        return 1.0
    return SequenceMatcher(None, sa, sb).ratio()


def _to_float(value: Any) -> float:
    """Convert a Decimal/str/number to float carefully."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


# ---------------------------------------------------------------------------
# Dimension 1: Amount (max 0.40)
# ---------------------------------------------------------------------------

def _score_amount(
    amount_a: Any,
    amount_b: Any,
    currency_a: Optional[str],
    currency_b: Optional[str],
) -> Dict[str, Any]:
    a = _to_float(amount_a)
    b = _to_float(amount_b)
    difference = abs(a - b)

    # Cross-currency -> 0.00
    if _is_cross_currency(currency_a, currency_b):
        return {
            "score": 0.0,
            "difference": difference,
            "cross_currency": True,
            "reason": "",
        }

    # Guard against divide-by-zero (a == 0). If both are zero -> exact; else
    # fall through to the >2% bucket.
    if a == 0:
        if difference == 0:
            return {
                "score": 0.40,
                "difference": 0.0,
                "cross_currency": False,
                "reason": "Exact amount match (%s %.2f)" % ((currency_a or "").strip().upper(), a),
            }
        return {"score": 0.0, "difference": difference, "cross_currency": False, "reason": ""}

    percent_diff = (difference / a) * 100
    cur = (currency_a or "").strip().upper()

    if percent_diff == 0:
        score = 0.40
        reason = "Exact amount match (%s %.2f)" % (cur, a)
    elif percent_diff <= 0.5:
        score = 0.38
        reason = "Amount within 0.5%% — difference: %s %.2f" % (cur, difference)
    elif percent_diff <= 1.0:
        score = 0.35
        reason = "Amount within 1.0%% — difference: %s %.2f" % (cur, difference)
    elif percent_diff <= 2.0:
        score = 0.30
        reason = "Amount within 2.0%% — difference: %s %.2f" % (cur, difference)
    else:
        score = 0.0
        reason = ""

    return {
        "score": score,
        "difference": difference,
        "cross_currency": False,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Dimension 2: Date (max 0.30)
# ---------------------------------------------------------------------------

def _score_date(date_a: Optional[datetime], date_b: Optional[datetime]) -> Dict[str, Any]:
    if date_a is None or date_b is None:
        return {"score": 0.0, "days_diff": 0, "reason": ""}

    seconds = abs((date_a - date_b).total_seconds())
    # Mirror Math.round(ms / msPerDay) — round half-up to whole days.
    days_diff = int(seconds / 86400.0 + 0.5)

    if days_diff == 0:
        score = 0.30
        reason = "Same date"
    elif days_diff <= 7:
        score = 0.28
        reason = "Within 7 days (%d day%s apart)" % (days_diff, "" if days_diff == 1 else "s")
    elif days_diff <= 14:
        score = 0.25
        reason = "Within 14 days (%d days apart)" % days_diff
    elif days_diff <= 30:
        score = 0.20
        reason = "Within 30 days (%d days apart)" % days_diff
    else:
        score = 0.0
        reason = ""

    return {"score": score, "days_diff": days_diff, "reason": reason}


# ---------------------------------------------------------------------------
# Dimension 3: Transaction Type (max 0.20)
# ---------------------------------------------------------------------------

def _normalize_type(t: Optional[str]) -> str:
    """Map raw provider directions to the scorer's source-type vocabulary.

    RECEIVE -> invoice, SPEND -> bill (mirrors data/db-normalizer.ts). Values
    already in the normalized vocabulary pass through unchanged.
    """
    if not t:
        return ""
    raw = t.strip().lower()
    if raw == "receive":
        return "invoice"
    if raw == "spend":
        return "bill"
    return raw


def _score_type(type_a: Optional[str], type_b: Optional[str]) -> Dict[str, Any]:
    a = _normalize_type(type_a)
    b = _normalize_type(type_b)

    # Invoice <-> Bill (either order) — the opposite-direction pair.
    if (a == "invoice" and b == "bill") or (a == "bill" and b == "invoice"):
        return {"score": 0.20, "reason": "Invoice ↔ Bill pair"}

    # Journal <-> Journal
    if a == "journal" and b == "journal":
        return {"score": 0.15, "reason": "Journal ↔ Journal pair"}

    # Same direction or other
    return {"score": 0.0, "reason": ""}


# ---------------------------------------------------------------------------
# Dimension 4: Counterparty (max 0.10)
# ---------------------------------------------------------------------------

def _score_counterparty(
    contact_a: Optional[str],
    contact_b: Optional[str],
    entity_name_a: Optional[str],
    entity_name_b: Optional[str],
) -> Dict[str, Any]:
    """Match one side's contact_name against the OTHER side's entity NAME.

    ContactMapping lookups (priority 1 in scorer.ts) are not available in this
    inline detection path, so we start at the exact-name tier.
    Tiers: exact (0.10) > substring (0.09) > fuzzy >= 0.80 (0.08).
    """
    ca = (contact_a or "").lower().strip()
    cb = (contact_b or "").lower().strip()
    ena = (entity_name_a or "").lower().strip()
    enb = (entity_name_b or "").lower().strip()

    # Priority 2: Exact name match
    if (ca and ca == enb) or (cb and cb == ena):
        return {"score": 0.10, "reason": "Exact counterparty name match"}

    # Priority 3: Substring containment (suffix-normalized)
    norm_contact_a = _normalize_for_substring_check(contact_a or "")
    norm_entity_b = _normalize_for_substring_check(entity_name_b or "")
    norm_contact_b = _normalize_for_substring_check(contact_b or "")
    norm_entity_a = _normalize_for_substring_check(entity_name_a or "")

    a_side = (
        bool(norm_contact_a)
        and bool(norm_entity_b)
        and norm_contact_a != norm_entity_b
        and (norm_contact_a in norm_entity_b or norm_entity_b in norm_contact_a)
    )
    b_side = (
        bool(norm_contact_b)
        and bool(norm_entity_a)
        and norm_contact_b != norm_entity_a
        and (norm_contact_b in norm_entity_a or norm_entity_a in norm_contact_b)
    )
    if a_side or b_side:
        return {"score": 0.09, "reason": "Substring counterparty name match"}

    # Priority 4: Fuzzy match (similarity >= 0.80)
    sim_a_to_b = _string_similarity(contact_a or "", entity_name_b or "")
    sim_b_to_a = _string_similarity(contact_b or "", entity_name_a or "")
    if sim_a_to_b >= 0.80 or sim_b_to_a >= 0.80:
        best_sim = max(sim_a_to_b, sim_b_to_a)
        return {
            "score": 0.08,
            "reason": "Fuzzy counterparty match (similarity: %.2f)" % best_sim,
        }

    return {"score": 0.0, "reason": ""}


# ---------------------------------------------------------------------------
# Match type classification (mirrors scorer.ts classifyMatch)
# ---------------------------------------------------------------------------

def _classify_match(confidence_score: float) -> str:
    return "exact" if confidence_score >= 0.95 else "fuzzy"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_pair(
    spend: Any,
    receive: Any,
    spend_entity_name: Optional[str],
    receive_entity_name: Optional[str],
) -> Dict[str, Any]:
    """Score a SPEND/RECEIVE intercompany pair.

    `spend` and `receive` are SQLAlchemy Transaction objects (we read
    .amount, .currency, .transaction_date, .transaction_type, .contact_name).

    Returns a dict with:
      confidence_score (float 0..1), match_type (str), amount_difference (float),
      days_difference (int), match_reasons (List[str]), plus per-dimension scores
      (amount_score, date_score, type_score, counterparty_score) and
      is_cross_currency (bool).
    """
    amount = _score_amount(
        getattr(spend, "amount", None),
        getattr(receive, "amount", None),
        getattr(spend, "currency", None),
        getattr(receive, "currency", None),
    )
    date = _score_date(
        getattr(spend, "transaction_date", None),
        getattr(receive, "transaction_date", None),
    )
    type_ = _score_type(
        getattr(spend, "transaction_type", None),
        getattr(receive, "transaction_type", None),
    )
    counterparty = _score_counterparty(
        getattr(spend, "contact_name", None),
        getattr(receive, "contact_name", None),
        spend_entity_name,
        receive_entity_name,
    )

    raw = amount["score"] + date["score"] + type_["score"] + counterparty["score"]
    # Round to 4 decimals, mirroring Math.round(x * 10000) / 10000.
    confidence_score = round(raw + 1e-12, 4)

    reasons: List[str] = []
    for dim in (amount, date, type_, counterparty):
        if dim["reason"]:
            reasons.append(dim["reason"])

    return {
        "confidence_score": confidence_score,
        "match_type": _classify_match(confidence_score),
        "amount_difference": amount["difference"],
        "days_difference": date["days_diff"],
        "match_reasons": reasons,
        "is_cross_currency": amount["cross_currency"],
        "amount_score": amount["score"],
        "date_score": date["score"],
        "type_score": type_["score"],
        "counterparty_score": counterparty["score"],
    }
