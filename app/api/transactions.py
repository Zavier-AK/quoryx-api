import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.auth import require_service_key, require_user, require_user_or_service
from app.core.ratelimit import EXPENSIVE_LIMIT, limiter
from app.models.database import get_db
from app.models.transaction import OAuthToken, ReconciliationStatus, Transaction
from app.services.oauth_service import oauth_service
from app.services.reconciliation_service import reconciliation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])

XERO_INVOICES_URL = "https://api.xero.com/api.xro/2.0/Invoices"


class TransactionCreate(BaseModel):
    token_id: UUID
    external_id: str
    provider: str
    amount: Decimal
    currency: str = "USD"
    description: Optional[str] = None
    transaction_date: datetime


class TransactionResponse(BaseModel):
    id: UUID
    token_id: UUID
    entity_id: Optional[UUID]
    external_id: str
    provider: str
    amount: Decimal
    currency: str
    description: Optional[str]
    transaction_date: datetime
    status: str
    contact_name: Optional[str]
    account_code: Optional[str]
    transaction_type: Optional[str]
    reference: Optional[str]
    matched_transaction_id: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/fetch", dependencies=[Depends(require_user_or_service)])
@limiter.limit(EXPENSIVE_LIMIT)
async def fetch_xero_invoices(request: Request, db: Session = Depends(get_db)):
    """
    Fetch invoices from the Xero API.
    Retrieves the stored OAuth token for default_user, refreshes it if expired,
    then calls the Xero Invoices endpoint and returns the raw invoice data.
    """
    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == "default_user", OAuthToken.provider == "xero")
        .first()
    )
    if not token:
        raise HTTPException(
            status_code=404,
            detail="No Xero connection found. Visit /api/auth/xero/login to connect.",
        )

    try:
        access_token = await oauth_service.get_valid_xero_access_token(token, db)
    except Exception as exc:
        logger.error("Xero token refresh failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to refresh Xero access token: {exc}",
        )

    logger.info(
        "Fetching Xero invoices. tenant_id=%s", token.tenant_id
    )
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                XERO_INVOICES_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "xero-tenant-id": token.tenant_id,
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Xero API returned error. status=%s body=%s",
            exc.response.status_code,
            exc.response.text,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Xero API error {exc.response.status_code}: {exc.response.text}",
        )
    except httpx.RequestError as exc:
        logger.error("Xero API request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Xero API request failed")

    logger.info("Xero invoices fetched successfully. tenant_id=%s", token.tenant_id)
    return resp.json()


@router.post(
    "/",
    response_model=TransactionResponse,
    status_code=201,
    dependencies=[Depends(require_service_key)],
)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    """Ingest a transaction and attempt immediate reconciliation."""
    transaction = Transaction(**payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    reconciliation_service.reconcile(transaction, db)
    db.refresh(transaction)

    return transaction


@router.get(
    "/",
    response_model=list[TransactionResponse],
    dependencies=[Depends(require_user)],
)
def list_transactions(
    entity_id: Optional[UUID] = None,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List transactions with optional filtering by entity_id, status, or provider."""
    query = db.query(Transaction)
    if entity_id:
        query = query.filter(Transaction.entity_id == entity_id)
    if status:
        query = query.filter(Transaction.status == status)
    if provider:
        query = query.filter(Transaction.provider == provider)
    return query.order_by(Transaction.transaction_date.desc()).all()


@router.get(
    "/{transaction_id}",
    response_model=TransactionResponse,
    dependencies=[Depends(require_user)],
)
def get_transaction(transaction_id: UUID, db: Session = Depends(get_db)):
    """Fetch a single transaction by ID."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@router.post(
    "/{transaction_id}/reconcile",
    response_model=TransactionResponse,
    dependencies=[Depends(require_service_key)],
)
def reconcile_transaction(transaction_id: UUID, db: Session = Depends(get_db)):
    """Manually trigger reconciliation for a transaction."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if transaction.status == ReconciliationStatus.MATCHED:
        raise HTTPException(status_code=409, detail="Transaction already matched")

    reconciliation_service.reconcile(transaction, db)
    db.refresh(transaction)
    return transaction
