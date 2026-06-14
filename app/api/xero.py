import json
import logging
import re
from datetime import datetime, timezone
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
from app.services.oauth_service import oauth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xero", tags=["xero"])

XERO_API_BASE = "https://api.xero.com/api.xro/2.0"


def _normalize_xero_type(raw_type: Optional[str]) -> Optional[str]:
    """
    Collapse Xero BankTransaction types to a canonical direction.

    Xero emits RECEIVE, SPEND and compound variants (RECEIVE-OVERPAYMENT,
    SPEND-PREPAYMENT, SPEND-TRANSFER, ...). Detection and the matching engine key
    on RECEIVE/SPEND, so store the canonical direction rather than the raw variant.
    """
    if not raw_type:
        return raw_type
    t = raw_type.upper()
    if t.startswith("RECEIVE"):
        return "RECEIVE"
    if t.startswith("SPEND"):
        return "SPEND"
    return raw_type


def _to_decimal(value) -> Decimal:
    """Parse a money value to Decimal, treating None/blank as 0 (never raises)."""
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _parse_xero_date(date_str: str) -> datetime:
    """Parse Xero's /Date(milliseconds+offset)/ format into a naive UTC datetime."""
    m = re.search(r"/Date\((\d+)", date_str or "")
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).replace(
            tzinfo=None
        )
    return datetime.utcnow()


async def _get_stored_token(
    db: Session, entity_id: Optional[UUID] = None
) -> OAuthToken:
    """
    Return a Xero OAuthToken.
    If entity_id is provided, look up the token for that specific entity.
    Otherwise return the first available Xero token (backward-compatible).
    """
    if entity_id:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        token = (
            db.query(OAuthToken)
            .filter(
                OAuthToken.tenant_id == entity.tenant_id,
                OAuthToken.provider == "xero",
            )
            .first()
        )
    else:
        token = db.query(OAuthToken).filter(OAuthToken.provider == "xero").first()

    if not token:
        raise HTTPException(
            status_code=404,
            detail="No Xero connection found. Visit /api/auth/xero/login to connect.",
        )
    return token


async def _xero_get(path: str, token: OAuthToken, db: Session) -> dict:
    """
    Authenticated GET against the Xero API.
    Refreshes the access token automatically if it is expired.
    """
    try:
        access_token = await oauth_service.get_valid_xero_access_token(token, db)
    except Exception as exc:
        logger.error("Xero token refresh failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Upstream provider error"
        )

    url = f"{XERO_API_BASE}/{path}"
    logger.info("Xero API GET %s tenant_id=%s", url, token.tenant_id)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Xero-tenant-id": token.tenant_id,
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Xero API error. status=%s body=%s",
            exc.response.status_code,
            exc.response.text,
        )
        raise HTTPException(
            status_code=502,
            detail="Upstream provider error",
        )
    except httpx.RequestError as exc:
        logger.error("Xero API request error: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to reach the accounting provider")

    return resp.json()


@router.get("/organisation", dependencies=[Depends(require_user_or_service)])
async def get_organisation(db: Session = Depends(get_db)):
    """Return details of the connected Xero organisation."""
    token = await _get_stored_token(db)
    return await _xero_get("Organisation", token, db)


@router.get("/accounts", dependencies=[Depends(require_user_or_service)])
async def get_accounts(db: Session = Depends(get_db)):
    """Return the chart of accounts for the connected Xero organisation."""
    token = await _get_stored_token(db)
    return await _xero_get("Accounts", token, db)


@router.get("/transactions", dependencies=[Depends(require_user_or_service)])
async def get_bank_transactions(db: Session = Depends(get_db)):
    """Return bank transactions for the connected Xero organisation."""
    token = await _get_stored_token(db)
    return await _xero_get("BankTransactions", token, db)


async def _ingest_for_entity(
    entity: Entity, token: OAuthToken, db: Session
) -> dict:
    """Pull BankTransactions for one entity and upsert into the transactions table."""
    data = await _xero_get("BankTransactions?statuses=AUTHORISED,DRAFT", token, db)
    bank_transactions = data.get("BankTransactions", [])

    created = 0
    updated = 0

    for xt in bank_transactions:
        xero_id = xt.get("BankTransactionID", "")
        if not xero_id:
            continue

        line_items = xt.get("LineItems") or []
        first_line = line_items[0] if line_items else {}

        fields = dict(
            entity_id=entity.id,
            transaction_date=_parse_xero_date(xt.get("Date", "")),
            amount=_to_decimal(xt.get("Total")),
            currency=xt.get("CurrencyCode") or entity.currency,
            description=first_line.get("Description"),
            contact_name=(xt.get("Contact") or {}).get("Name"),
            account_code=(xt.get("BankAccount") or {}).get("Code"),
            transaction_type=_normalize_xero_type(xt.get("Type")),
            reference=xt.get("Reference"),
            raw_payload=json.dumps(xt),
            updated_at=datetime.utcnow(),
        )

        existing = (
            db.query(Transaction)
            .filter(
                Transaction.external_id == xero_id,
                Transaction.provider == "xero",
            )
            .first()
        )

        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(
                Transaction(
                    token_id=token.id,
                    external_id=xero_id,
                    provider="xero",
                    status=ReconciliationStatus.PENDING,
                    **fields,
                )
            )
            created += 1

    db.commit()
    logger.info(
        "Xero ingest complete. entity=%s created=%d updated=%d",
        entity.org_name,
        created,
        updated,
    )
    return {
        "entity": entity.org_name,
        "entity_id": str(entity.id),
        "created": created,
        "updated": updated,
        "total": len(bank_transactions),
    }


@router.post("/ingest", dependencies=[Depends(require_user_or_service)])
@limiter.limit(EXPENSIVE_LIMIT)
async def ingest_transactions(
    request: Request,
    entity_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Pull BankTransactions from Xero and upsert them into the transactions table.

    - With ?entity_id=<uuid>: ingest only for that entity.
    - Without entity_id: ingest for ALL connected entities.

    Returns a summary (or list of summaries) of created vs updated counts.
    """
    if entity_id:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        token = (
            db.query(OAuthToken)
            .filter(
                OAuthToken.tenant_id == entity.tenant_id,
                OAuthToken.provider == "xero",
            )
            .first()
        )
        if not token:
            raise HTTPException(
                status_code=404,
                detail=f"No Xero token for entity '{entity.org_name}'. Re-authorise at /api/auth/xero/login.",
            )
        return await _ingest_for_entity(entity, token, db)

    # No entity_id — ingest for all connected entities
    entities = db.query(Entity).all()
    if not entities:
        raise HTTPException(
            status_code=404,
            detail="No entities found. Run POST /api/entities/sync first.",
        )

    results = []
    for entity in entities:
        token = (
            db.query(OAuthToken)
            .filter(
                OAuthToken.tenant_id == entity.tenant_id,
                OAuthToken.provider == "xero",
            )
            .first()
        )
        if not token:
            results.append(
                {"entity": entity.org_name, "entity_id": str(entity.id), "error": "No Xero token found"}
            )
            continue
        try:
            result = await _ingest_for_entity(entity, token, db)
            results.append(result)
        except HTTPException as exc:
            results.append(
                {"entity": entity.org_name, "entity_id": str(entity.id), "error": exc.detail}
            )

    # Return a single object when there is only one entity (backward-compatible)
    return results[0] if len(results) == 1 else results
