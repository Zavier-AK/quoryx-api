import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_service_key, require_user
from app.models.database import get_db
from app.models.entity import Entity
from app.models.transaction import OAuthToken
from app.services.oauth_service import oauth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entities", tags=["entities"])

XERO_ORGANISATION_URL = "https://api.xero.com/api.xro/2.0/Organisation"


async def sync_entity_from_token(token: OAuthToken, db: Session) -> dict:
    """
    Pull the Xero Organisation for a single token and upsert it into the entities
    table. Returns the action ("created" / "updated") and the entity dict.
    Raises HTTPException on Xero API errors.
    """
    try:
        access_token = await oauth_service.get_valid_xero_access_token(token, db)
    except Exception as exc:
        logger.error("Token refresh failed for tenant_id=%s: %s", token.tenant_id, exc)
        raise HTTPException(status_code=502, detail="Upstream provider error")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                XERO_ORGANISATION_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Xero-tenant-id": token.tenant_id,
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Xero Organisation API error. status=%s body=%s",
            exc.response.status_code,
            exc.response.text,
        )
        raise HTTPException(
            status_code=502,
            detail="Upstream provider error",
        )
    except httpx.RequestError as exc:
        logger.error("Xero Organisation API request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to reach the accounting provider")

    orgs = resp.json().get("Organisations", [])
    if not orgs:
        raise HTTPException(
            status_code=502, detail="No organisation data returned from Xero"
        )

    org = orgs[0]
    org_name = org.get("Name", "")
    currency = org.get("BaseCurrency", "")
    country_code = org.get("CountryCode", "")

    entity = db.query(Entity).filter(Entity.tenant_id == token.tenant_id).first()
    if entity:
        entity.org_name = org_name
        entity.currency = currency
        entity.country_code = country_code
        db.commit()
        db.refresh(entity)
        action = "updated"
    else:
        entity = Entity(
            tenant_id=token.tenant_id,
            org_name=org_name,
            currency=currency,
            country_code=country_code,
            connected_at=datetime.utcnow(),
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        action = "created"

    logger.info("Entity %s: %s (tenant_id=%s)", action, org_name, token.tenant_id)
    return {
        "action": action,
        "entity": {
            "id": str(entity.id),
            "tenant_id": entity.tenant_id,
            "org_name": entity.org_name,
            "currency": entity.currency,
            "country_code": entity.country_code,
            "connected_at": (
                entity.connected_at.isoformat() if entity.connected_at else None
            ),
        },
    }


async def sync_economic_entity_from_token(
    token: OAuthToken, db: Session, self_data: Optional[dict] = None
) -> dict:
    """
    Upsert the E-conomic agreement behind `token` into the entities table using
    the /self payload. Mirrors sync_entity_from_token but for E-conomic's format
    (no Xero-style tenant header; the grant token IS the agreement identity).
    """
    # Import here to avoid a circular import at module load.
    from app.api.economic import fetch_economic_self  # noqa: PLC0415

    if self_data is None:
        self_data = await fetch_economic_self(token.access_token)

    company = self_data.get("company") or {}
    settings_blk = self_data.get("settings") or {}

    org_name = company.get("name") or f"Agreement {token.tenant_id}"
    currency = settings_blk.get("baseCurrency") or "DKK"
    # /self returns a full country name (e.g. "Denmark"); column is String(3).
    country = (company.get("country") or "")[:3].upper() or None

    entity = db.query(Entity).filter(Entity.tenant_id == token.tenant_id).first()
    if entity:
        entity.org_name = org_name
        entity.currency = currency
        entity.country_code = country
        db.commit()
        db.refresh(entity)
        action = "updated"
    else:
        entity = Entity(
            tenant_id=token.tenant_id,
            org_name=org_name,
            currency=currency,
            country_code=country,
            connected_at=datetime.utcnow(),
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        action = "created"

    logger.info(
        "E-conomic entity %s: %s (tenant_id=%s)", action, org_name, token.tenant_id
    )
    return {
        "action": action,
        "entity": {
            "id": str(entity.id),
            "tenant_id": entity.tenant_id,
            "org_name": entity.org_name,
            "currency": entity.currency,
            "country_code": entity.country_code,
            "connected_at": (
                entity.connected_at.isoformat() if entity.connected_at else None
            ),
        },
    }


@router.post("/sync", dependencies=[Depends(require_service_key)])
async def sync_entities(db: Session = Depends(get_db)):
    """
    Sync all connected Xero organisations into the entities table.
    Iterates every stored Xero token and upserts the corresponding entity.
    """
    tokens = db.query(OAuthToken).filter(OAuthToken.provider == "xero").all()
    if not tokens:
        raise HTTPException(
            status_code=404,
            detail="No Xero connections found. Visit /api/auth/xero/login to connect.",
        )

    results = []
    for token in tokens:
        try:
            result = await sync_entity_from_token(token, db)
            results.append(result)
        except HTTPException as exc:
            results.append(
                {"error": exc.detail, "tenant_id": token.tenant_id}
            )

    # Return a single object (not a list) when there is only one entity,
    # preserving the existing API contract.
    return results[0] if len(results) == 1 else results


@router.get("/", dependencies=[Depends(require_user)])
def list_entities(db: Session = Depends(get_db)):
    """List all connected Xero organisations."""
    entities = db.query(Entity).order_by(Entity.connected_at.desc()).all()
    return [
        {
            "id": str(e.id),
            "tenant_id": e.tenant_id,
            "org_name": e.org_name,
            "currency": e.currency,
            "country_code": e.country_code,
            "connected_at": e.connected_at.isoformat() if e.connected_at else None,
        }
        for e in entities
    ]
