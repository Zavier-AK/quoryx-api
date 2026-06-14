import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import require_service_key, require_user, require_user_or_service
from app.core.ratelimit import EXPENSIVE_LIMIT, limiter
from app.models.database import get_db
from app.models.entity import Entity, IntercompanyTransaction
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

ALLOWED_STATUSES = {"matched", "reconciled"}


# ---------------------------------------------------------------------------
# POST /detect
# ---------------------------------------------------------------------------

@router.post("/detect", dependencies=[Depends(require_service_key)])
def detect_intercompany(db: Session = Depends(get_db)):
    """
    Scan all transactions across all entities, group by reference, and flag
    SPEND/RECEIVE pairs with matching amount and currency as intercompany candidates.

    Matching rules:
      - Same reference number
      - Different entities
      - One side SPEND, other side RECEIVE
      - Identical amount and currency

    Writes each new pair to intercompany_transactions with status='unmatched'.
    Idempotent: re-running skips pairs that already exist.
    """
    all_txns = (
        db.query(Transaction)
        .filter(
            Transaction.entity_id.isnot(None),
            Transaction.transaction_type.isnot(None),
        )
        .all()
    )

    pairs_created = 0
    pairs_skipped = 0
    pairs = []
    # Track pairs created in this run so the exact and relaxed passes don't
    # double-create, and so each transaction is only paired once.
    seen_keys: set = set()
    consumed: set = set()

    def _try_create_pair(spend, receive, ref, rule: str) -> None:
        nonlocal pairs_created, pairs_skipped
        key = (spend.external_id, receive.external_id)
        if key in seen_keys:
            return
        if spend.external_id in consumed or receive.external_id in consumed:
            return

        existing = (
            db.query(IntercompanyTransaction)
            .filter(
                IntercompanyTransaction.source_transaction_id == spend.external_id,
                IntercompanyTransaction.target_transaction_id == receive.external_id,
            )
            .first()
        )
        seen_keys.add(key)
        if existing:
            pairs_skipped += 1
            consumed.update({spend.external_id, receive.external_id})
            return

        db.add(
            IntercompanyTransaction(
                source_entity_id=spend.entity_id,
                target_entity_id=receive.entity_id,
                amount=spend.amount,
                currency=spend.currency,
                description=spend.description or receive.description,
                transaction_date=spend.transaction_date,
                status="unmatched",
                source_transaction_id=spend.external_id,
                target_transaction_id=receive.external_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        pairs.append(
            {
                "reference": ref,
                "rule": rule,
                "amount": str(spend.amount),
                "currency": spend.currency,
                "description": spend.description,
                "source_transaction_id": spend.external_id,
                "target_transaction_id": receive.external_id,
            }
        )
        consumed.update({spend.external_id, receive.external_id})
        pairs_created += 1

    # --- Pass 1: exact-reference fast path (same provider or cross-provider) ---
    by_ref: dict = defaultdict(list)
    for t in all_txns:
        if t.reference:
            by_ref[t.reference].append(t)

    for ref, txns in by_ref.items():
        if len({t.entity_id for t in txns}) < 2:
            continue
        spends = [t for t in txns if t.transaction_type == "SPEND"]
        receives = [t for t in txns if t.transaction_type == "RECEIVE"]
        for spend in spends:
            for receive in receives:
                if spend.entity_id == receive.entity_id:
                    continue
                if spend.amount != receive.amount or spend.currency != receive.currency:
                    continue
                _try_create_pair(spend, receive, ref, rule="exact_reference")

    # --- Pass 2: relaxed cross-provider candidates ---
    # Different providers issue independent reference schemes, so genuine
    # intercompany pairs rarely share a reference. Generate candidates on
    # direction + currency + amount-within-tolerance + date-window and let the
    # TypeScript scoring engine assign final confidence.
    AMOUNT_TOLERANCE = 0.02  # 2%, mirrors the scorer's amount dimension
    DATE_WINDOW = timedelta(days=30)  # mirrors the scorer's date dimension

    spends_all = [t for t in all_txns if t.transaction_type == "SPEND"]
    receives_all = [t for t in all_txns if t.transaction_type == "RECEIVE"]

    for spend in spends_all:
        if spend.external_id in consumed:
            continue
        for receive in receives_all:
            if receive.external_id in consumed:
                continue
            if spend.entity_id == receive.entity_id:
                continue
            if spend.currency != receive.currency:
                continue
            if spend.provider == receive.provider:
                continue  # same-provider handled by the exact-reference pass
            if not spend.amount or not receive.amount:
                continue
            amt_diff = abs(float(spend.amount) - float(receive.amount))
            if amt_diff / float(spend.amount) > AMOUNT_TOLERANCE:
                continue
            if abs(spend.transaction_date - receive.transaction_date) > DATE_WINDOW:
                continue
            _try_create_pair(
                spend, receive, ref=spend.reference, rule="relaxed_cross_provider"
            )

    db.commit()
    logger.info(
        "Intercompany detection complete. pairs_created=%d pairs_skipped=%d",
        pairs_created,
        pairs_skipped,
    )
    return {"pairs_created": pairs_created, "pairs_skipped": pairs_skipped, "pairs": pairs}


# ---------------------------------------------------------------------------
# GET /pairs
# ---------------------------------------------------------------------------

def _pair_to_dict(pair: IntercompanyTransaction, db: Session) -> dict:
    """Serialize one IntercompanyTransaction with entity names and reference."""
    source_entity = db.get(Entity, pair.source_entity_id)
    target_entity = db.get(Entity, pair.target_entity_id)

    # Look up the reference from the source transaction
    source_txn = (
        db.query(Transaction)
        .filter(Transaction.external_id == pair.source_transaction_id)
        .first()
    )

    return {
        "id": str(pair.id),
        "status": pair.status,
        "reference": source_txn.reference if source_txn else None,
        "source_entity_id": str(pair.source_entity_id),
        "source_entity_name": source_entity.org_name if source_entity else None,
        "target_entity_id": str(pair.target_entity_id),
        "target_entity_name": target_entity.org_name if target_entity else None,
        "amount": str(pair.amount),
        "currency": pair.currency,
        "description": pair.description,
        "transaction_date": pair.transaction_date.isoformat() if pair.transaction_date else None,
        "source_transaction_id": pair.source_transaction_id,
        "target_transaction_id": pair.target_transaction_id,
        "confidence_score": pair.confidence_score,
        "match_type": pair.match_type,
        "amount_difference": pair.amount_difference,
        "days_difference": pair.days_difference,
        "match_reasons": pair.match_reasons,
        "llm_reasoning": pair.llm_reasoning,
        "review_required": pair.review_required,
        "reviewed_at": pair.reviewed_at.isoformat() if pair.reviewed_at else None,
        "reviewed_by": pair.reviewed_by,
        "created_at": pair.created_at.isoformat() if pair.created_at else None,
        "updated_at": pair.updated_at.isoformat() if pair.updated_at else None,
    }


@router.get("/pairs", dependencies=[Depends(require_user)])
def list_pairs(
    status: str = None,
    db: Session = Depends(get_db),
):
    """
    Return all intercompany transaction pairs with entity names, amounts and status.
    Optionally filter by ?status=unmatched|matched|reconciled.
    """
    query = db.query(IntercompanyTransaction)
    if status:
        query = query.filter(IntercompanyTransaction.status == status)
    pairs = query.order_by(IntercompanyTransaction.created_at.desc()).all()
    return [_pair_to_dict(p, db) for p in pairs]


# ---------------------------------------------------------------------------
# PATCH /pairs/{id}/status
# ---------------------------------------------------------------------------

class ScorerUpdate(BaseModel):
    status: Literal["matched", "review_required", "unmatched"]
    confidence_score: Optional[float] = None
    match_type: Optional[str] = None
    amount_difference: Optional[float] = None
    days_difference: Optional[int] = None
    match_reasons: Optional[str] = None
    llm_reasoning: Optional[str] = None
    review_required: Optional[bool] = None


@router.patch("/pairs/{pair_id}/status", dependencies=[Depends(require_user_or_service)])
def update_pair_status(
    pair_id: UUID,
    body: ScorerUpdate,
    db: Session = Depends(get_db),
):
    """
    Update scorer results for an intercompany pair.
    Accepts status plus optional scorer metadata fields.
    All provided fields are written; omitted fields are left unchanged.
    """
    pair = db.get(IntercompanyTransaction, pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")

    previous_status = pair.status
    pair.status = body.status

    if body.confidence_score is not None:
        pair.confidence_score = body.confidence_score
    if body.match_type is not None:
        pair.match_type = body.match_type
    if body.amount_difference is not None:
        pair.amount_difference = body.amount_difference
    if body.days_difference is not None:
        pair.days_difference = body.days_difference
    if body.match_reasons is not None:
        pair.match_reasons = body.match_reasons
    if body.llm_reasoning is not None:
        pair.llm_reasoning = body.llm_reasoning
    if body.review_required is not None:
        pair.review_required = body.review_required

    pair.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(pair)

    logger.info("Pair %s updated %s → %s", pair_id, previous_status, body.status)
    return _pair_to_dict(pair, db)


# ---------------------------------------------------------------------------
# GET /summary
# ---------------------------------------------------------------------------

@router.get("/summary", dependencies=[Depends(require_user)])
def reconciliation_summary(db: Session = Depends(get_db)):
    """
    Return reconciliation counts broken down by status (global) and per entity.
    Each entity row counts pairs where it appears as source OR target.
    """
    all_pairs = db.query(IntercompanyTransaction).all()
    all_entities = {e.id: e for e in db.query(Entity).all()}

    statuses = ("unmatched", "matched", "reconciled")

    # Global totals
    global_counts: dict = {s: 0 for s in statuses}
    for p in all_pairs:
        if p.status in global_counts:
            global_counts[p.status] += 1

    # Per-entity: count pairs where entity is source OR target
    entity_counts: dict = defaultdict(lambda: {s: 0 for s in statuses})
    for p in all_pairs:
        if p.status in statuses:
            entity_counts[p.source_entity_id][p.status] += 1
            entity_counts[p.target_entity_id][p.status] += 1

    by_entity = []
    for entity_id, counts in entity_counts.items():
        entity = all_entities.get(entity_id)
        by_entity.append(
            {
                "entity_id": str(entity_id),
                "entity_name": entity.org_name if entity else str(entity_id),
                "total": sum(counts.values()),
                **counts,
            }
        )
    by_entity.sort(key=lambda x: x["entity_name"])

    return {
        "total_pairs": len(all_pairs),
        "by_status": global_counts,
        "by_entity": by_entity,
    }


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------

@router.post("/run", dependencies=[Depends(require_user_or_service)])
@limiter.limit(EXPENSIVE_LIMIT)
def run_reconciliation(request: Request, db: Session = Depends(get_db)):
    """
    Trigger a full reconciliation run.
    Runs the same detection logic as /detect and returns a pair summary.
    """
    return detect_intercompany(db)
