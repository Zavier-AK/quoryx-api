import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import require_service_key, require_user_or_service
from app.core.ratelimit import EXPENSIVE_LIMIT, limiter
from app.models.database import get_db
from app.models.entity import Entity
from app.models.transaction import OAuthToken, ReconciliationStatus, Transaction
from app.services.oauth_service import (
    ECONOMIC_APP_BASE,
    ECONOMIC_REST_BASE,
    oauth_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/economic", tags=["economic"])

# Max page size the e-conomic REST API allows.
ECONOMIC_PAGE_SIZE = 1000


def _parse_economic_date(date_str: str) -> datetime:
    """
    Parse e-conomic's ISO date string (YYYY-MM-DD) into a naive datetime.
    Never raises: an empty or malformed value falls back to now() with a warning.
    """
    if not date_str:
        return datetime.utcnow()
    try:
        # fromisoformat handles both "2022-06-02" and full timestamps.
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except (ValueError, TypeError):
        logger.warning("Unparseable e-conomic date %r — using now()", date_str)
        return datetime.utcnow()


def _to_decimal(value) -> Decimal:
    """
    Parse a money value to Decimal, treating None/blank as 0 (never raises).

    dict.get(key, 0) only defaults on a MISSING key; the API can return the key
    present with an explicit null, which would make Decimal(str(None)) raise.
    """
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        logger.warning("Unparseable e-conomic amount %r — using 0", value)
        return Decimal("0")


async def _economic_get(
    path: str, grant_token: str, base: str = ECONOMIC_REST_BASE
) -> dict:
    """
    Authenticated GET against an e-conomic API host.

    Unlike Xero there is no token refresh — the grant token is permanent, so the
    two static headers are sent as-is.
    """
    url = f"{base}/{path.lstrip('/')}"
    logger.info("E-conomic API GET %s", url)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, headers=oauth_service.economic_headers(grant_token)
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "E-conomic API error. status=%s body=%s",
            exc.response.status_code,
            exc.response.text,
        )
        raise HTTPException(
            status_code=502,
            detail="Upstream provider error",
        )
    except httpx.RequestError as exc:
        logger.error("E-conomic API request error: %s", exc)
        raise HTTPException(
            status_code=502, detail="Failed to reach the accounting provider"
        )
    return resp.json()


async def fetch_economic_self(grant_token: str) -> dict:
    """Return the /self payload for a grant token (company + agreement info)."""
    return await _economic_get("self", grant_token)


async def _get_stored_token(
    db: Session, entity_id: Optional[UUID] = None
) -> OAuthToken:
    """
    Return an E-conomic OAuthToken.
    If entity_id is provided, look up the token for that specific entity.
    Otherwise return the first available E-conomic token.
    """
    if entity_id:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        token = (
            db.query(OAuthToken)
            .filter(
                OAuthToken.tenant_id == entity.tenant_id,
                OAuthToken.provider == "economic",
            )
            .first()
        )
    else:
        token = (
            db.query(OAuthToken).filter(OAuthToken.provider == "economic").first()
        )

    if not token:
        raise HTTPException(
            status_code=404,
            detail="No E-conomic connection found. Visit /api/auth/economic/login to connect.",
        )
    return token


# ---------------------------------------------------------------------------
# Read endpoints (debugging / inspection)
# ---------------------------------------------------------------------------


@router.get("/self", dependencies=[Depends(require_user_or_service)])
async def get_self(db: Session = Depends(get_db)):
    """Return company/agreement details for the connected E-conomic agreement."""
    token = await _get_stored_token(db)
    return await fetch_economic_self(token.access_token)


@router.get("/invoices/booked", dependencies=[Depends(require_user_or_service)])
async def get_booked_invoices(db: Session = Depends(get_db)):
    """Return the first page of booked sales invoices (for inspection)."""
    token = await _get_stored_token(db)
    return await _economic_get(
        f"invoices/booked?pagesize=20&skippages=0", token.access_token
    )


# ---------------------------------------------------------------------------
# Provider-specific field mappers
#
# The shared `transactions` columns are the contract. `transaction_type` is the
# canonical cross-provider DIRECTION field, which each provider fills from its
# own native concept: e-conomic sales invoice -> RECEIVE, supplier invoice -> SPEND.
# ---------------------------------------------------------------------------


def _map_economic_invoice(item: dict, entity: Entity, token: OAuthToken) -> dict:
    """Map a booked SALES invoice (AR) to Transaction fields. Direction = RECEIVE."""
    number = item.get("bookedInvoiceNumber")
    recipient = item.get("recipient") or {}
    references = item.get("references") or {}
    return dict(
        token_id=token.id,
        entity_id=entity.id,
        owner_id=entity.owner_id,
        external_id=f"econ-sales-{number}",
        provider="economic",
        amount=_to_decimal(item.get("grossAmount")),
        currency=item.get("currency") or entity.currency,
        description=(item.get("notes") or {}).get("heading"),
        transaction_date=_parse_economic_date(item.get("date", "")),
        contact_name=recipient.get("name"),
        account_code=None,
        transaction_type="RECEIVE",
        reference=str(references.get("other") or number or ""),
        raw_payload=json.dumps(item),
        updated_at=datetime.utcnow(),
    )


def _map_economic_supplier_invoice(
    item: dict, entity: Entity, token: OAuthToken
) -> dict:
    """Map a booked SUPPLIER invoice (AP) to Transaction fields. Direction = SPEND."""
    number = item.get("supplierInvoiceNumber") or item.get("number")
    supplier = item.get("supplier") or {}
    return dict(
        token_id=token.id,
        entity_id=entity.id,
        owner_id=entity.owner_id,
        external_id=f"econ-supplier-{number}",
        provider="economic",
        amount=_to_decimal(item.get("grossAmount", item.get("amount"))),
        currency=item.get("currency") or entity.currency,
        description=item.get("text") or item.get("description"),
        transaction_date=_parse_economic_date(item.get("date", "")),
        contact_name=supplier.get("name"),
        account_code=None,
        transaction_type="SPEND",
        reference=str(item.get("reference") or number or ""),
        raw_payload=json.dumps(item),
        updated_at=datetime.utcnow(),
    )


def _upsert_transaction(db: Session, fields: dict) -> str:
    """Insert or update a Transaction keyed on (external_id, provider). Returns action."""
    existing = (
        db.query(Transaction)
        .filter(
            Transaction.external_id == fields["external_id"],
            Transaction.provider == "economic",
        )
        .first()
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        return "updated"
    db.add(Transaction(status=ReconciliationStatus.PENDING, **fields))
    return "created"


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


async def _ingest_sales_invoices(entity: Entity, token: OAuthToken, db: Session) -> int:
    """Page through all booked sales invoices and upsert them. Returns total seen."""
    total = 0
    skip = 0
    while True:
        data = await _economic_get(
            f"invoices/booked?pagesize={ECONOMIC_PAGE_SIZE}&skippages={skip}",
            token.access_token,
        )
        collection = data.get("collection") or []
        if not collection:
            break
        for item in collection:
            _upsert_transaction(db, _map_economic_invoice(item, entity, token))
        total += len(collection)
        if len(collection) < ECONOMIC_PAGE_SIZE:
            break
        skip += 1
    return total


async def _ingest_supplier_invoices(
    entity: Entity, token: OAuthToken, db: Session
) -> Optional[int]:
    """
    Page through booked supplier invoices (AP) and upsert them.

    Supplier invoices live on the companion OpenAPI host and are not part of the
    classic REST surface. If that endpoint is unreachable for this agreement we
    degrade gracefully: log a warning and return None so sales-side ingest still
    succeeds.
    """
    total = 0
    skip = 0
    try:
        while True:
            data = await _economic_get(
                f"supplierinvoices/booked?pagesize={ECONOMIC_PAGE_SIZE}&skippages={skip}",
                token.access_token,
                base=ECONOMIC_APP_BASE,
            )
            collection = data.get("collection") or data.get("items") or []
            if not collection:
                break
            for item in collection:
                _upsert_transaction(
                    db, _map_economic_supplier_invoice(item, entity, token)
                )
            total += len(collection)
            if len(collection) < ECONOMIC_PAGE_SIZE:
                break
            skip += 1
    except HTTPException as exc:
        logger.warning(
            "Supplier-invoice ingest skipped for entity=%s (endpoint unavailable): %s",
            entity.org_name,
            exc.detail,
        )
        return None
    return total


async def _ingest_for_entity(entity: Entity, token: OAuthToken, db: Session) -> dict:
    """Ingest sales (RECEIVE) and supplier (SPEND) invoices for one entity."""
    sales = await _ingest_sales_invoices(entity, token, db)
    supplier = await _ingest_supplier_invoices(entity, token, db)
    db.commit()
    logger.info(
        "E-conomic ingest complete. entity=%s sales=%d supplier=%s",
        entity.org_name,
        sales,
        supplier,
    )
    return {
        "entity": entity.org_name,
        "entity_id": str(entity.id),
        "sales_invoices": sales,
        "supplier_invoices": supplier,
    }


@router.post("/ingest", dependencies=[Depends(require_user_or_service)])
@limiter.limit(EXPENSIVE_LIMIT)
async def ingest_transactions(
    request: Request,
    entity_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Pull booked sales + supplier invoices from E-conomic and upsert them into the
    transactions table.

    - With ?entity_id=<uuid>: ingest only for that entity.
    - Without entity_id: ingest for ALL connected E-conomic entities.
    """
    if entity_id:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        token = (
            db.query(OAuthToken)
            .filter(
                OAuthToken.tenant_id == entity.tenant_id,
                OAuthToken.provider == "economic",
            )
            .first()
        )
        if not token:
            raise HTTPException(
                status_code=404,
                detail=f"No E-conomic token for entity '{entity.org_name}'. Reconnect at /api/auth/economic/login.",
            )
        return await _ingest_for_entity(entity, token, db)

    entities = db.query(Entity).all()
    economic_tokens = {
        t.tenant_id: t
        for t in db.query(OAuthToken).filter(OAuthToken.provider == "economic").all()
    }
    if not economic_tokens:
        raise HTTPException(
            status_code=404,
            detail="No E-conomic connections found. Visit /api/auth/economic/login to connect.",
        )

    results = []
    for entity in entities:
        token = economic_tokens.get(entity.tenant_id)
        if not token:
            continue  # entity belongs to a different provider
        try:
            results.append(await _ingest_for_entity(entity, token, db))
        except HTTPException as exc:
            results.append(
                {"entity": entity.org_name, "entity_id": str(entity.id), "error": exc.detail}
            )

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No E-conomic entities found. Connect via /api/auth/economic/login first.",
        )
    return results[0] if len(results) == 1 else results
