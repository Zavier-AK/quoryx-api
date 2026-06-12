import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.transaction import OAuthToken
from app.services.oauth_service import oauth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# In production, store state tokens server-side (e.g. Redis) keyed to a session.
# This in-memory dict is sufficient for single-process development only.
_pending_states: dict[str, dict] = {}


@router.get("/xero/login")
def xero_login(entity_name: Optional[str] = Query(None)):
    """
    Redirect the user to Xero's authorization page to begin OAuth 2.0.
    Pass entity_name to label which organisation is connecting (informational only).
    """
    url, state = oauth_service.get_xero_authorization_url()
    _pending_states[state] = {"provider": "xero", "entity_name": entity_name}
    logger.info("Initiating Xero OAuth flow. entity_name=%s", entity_name)
    return RedirectResponse(url=url)


@router.get("/xero/callback")
async def xero_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Handle the Xero OAuth callback:
    - Validate state token
    - Exchange authorization code for access + refresh tokens
    - Upsert the token keyed on tenant_id (supports multiple entities)
    - Auto-sync the connected entity into the entities table
    """
    state_data = _pending_states.pop(state, None)
    if not state_data or state_data.get("provider") != "xero":
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    try:
        token_data = await oauth_service.exchange_xero_code(code)
    except Exception as exc:
        logger.error("Xero token exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Xero OAuth failed: {exc}")

    tenant_id = token_data["tenant_id"]

    # Upsert keyed on tenant_id + provider so each Xero org gets its own row
    existing = (
        db.query(OAuthToken)
        .filter(OAuthToken.tenant_id == tenant_id, OAuthToken.provider == "xero")
        .first()
    )
    if existing:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data["refresh_token"]
        existing.expires_at = token_data["expires_at"]
        db.commit()
        db.refresh(existing)
        token = existing
    else:
        token = OAuthToken(
            user_id=tenant_id,  # tenant_id as user_id gives a unique, meaningful value
            provider="xero",
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=token_data["expires_at"],
            tenant_id=tenant_id,
        )
        db.add(token)
        db.commit()
        db.refresh(token)

    logger.info(
        "Xero OAuth connected. token_id=%s tenant_id=%s entity_name=%s",
        token.id,
        tenant_id,
        state_data.get("entity_name"),
    )

    # Auto-sync the entity — import here to avoid circular dependency
    from app.api.entities import sync_entity_from_token  # noqa: PLC0415

    try:
        entity_result = await sync_entity_from_token(token, db)
    except Exception as exc:
        logger.warning("Entity auto-sync failed after OAuth (token saved): %s", exc)
        entity_result = None

    return {
        "status": "connected",
        "provider": "xero",
        "token_id": str(token.id),
        "tenant_id": token.tenant_id,
        "entity": entity_result,
    }


@router.get("/quickbooks/login")
def quickbooks_login():
    """Redirect the user to QuickBooks' authorization page to begin OAuth 2.0."""
    url, state = oauth_service.get_quickbooks_authorization_url()
    _pending_states[state] = {"provider": "quickbooks"}
    logger.info("Initiating QuickBooks OAuth flow, redirecting to authorization URL")
    return RedirectResponse(url=url)


@router.get("/quickbooks/callback")
async def quickbooks_callback(
    code: str = Query(...),
    state: str = Query(...),
    realmId: str = Query(...),
    db: Session = Depends(get_db),
):
    """Handle the QuickBooks OAuth callback and store tokens."""
    state_data = _pending_states.pop(state, None)
    if not state_data or state_data.get("provider") != "quickbooks":
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    try:
        token_data = await oauth_service.exchange_quickbooks_code(code, realmId)
    except Exception as exc:
        logger.error("QuickBooks token exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"QuickBooks OAuth failed: {exc}")

    existing = (
        db.query(OAuthToken)
        .filter(
            OAuthToken.user_id == "default_user",
            OAuthToken.provider == "quickbooks",
        )
        .first()
    )
    if existing:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data["refresh_token"]
        existing.expires_at = token_data["expires_at"]
        existing.tenant_id = token_data.get("realm_id")
        db.commit()
        db.refresh(existing)
        token = existing
    else:
        token = OAuthToken(
            user_id="default_user",
            provider="quickbooks",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_at=token_data["expires_at"],
            tenant_id=token_data.get("realm_id"),
        )
        db.add(token)
        db.commit()
        db.refresh(token)

    logger.info("QuickBooks OAuth connected successfully. token_id=%s", token.id)
    return {
        "status": "connected",
        "provider": "quickbooks",
        "token_id": str(token.id),
    }


@router.get("/economic/login")
def economic_login(entity_name: Optional[str] = Query(None)):
    """
    Redirect the user to the app's E-conomic Installation URL to grant access.
    E-conomic returns the permanent grant token to our callback as ?token=xxx.
    """
    url, state = oauth_service.get_economic_install_url()
    _pending_states[state] = {"provider": "economic", "entity_name": entity_name}
    logger.info("Initiating E-conomic connect flow. entity_name=%s", entity_name)
    return RedirectResponse(url=url)


@router.get("/economic/callback")
async def economic_callback(
    token: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Handle the E-conomic connect callback:
    - Validate state token
    - Resolve the agreement number via GET /self (E-conomic's tenant identity)
    - Upsert the OAuthToken keyed on tenant_id (supports multiple agreements)
    - Auto-sync the connected entity into the entities table

    The grant token is permanent: there is no code exchange, refresh, or expiry.
    """
    state_data = _pending_states.pop(state, None)
    if not state_data or state_data.get("provider") != "economic":
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    # Identify the agreement this grant token belongs to. Import here to avoid a
    # circular import at module load (economic router imports from auth indirectly).
    from app.api.economic import fetch_economic_self  # noqa: PLC0415

    try:
        self_data = await fetch_economic_self(token)
    except Exception as exc:
        logger.error("E-conomic /self lookup failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"E-conomic connect failed: {exc}")

    tenant_id = str(self_data.get("agreementNumber") or "")
    if not tenant_id:
        raise HTTPException(
            status_code=502, detail="E-conomic /self did not return an agreementNumber"
        )

    # Upsert keyed on tenant_id + provider so each agreement gets its own row.
    existing = (
        db.query(OAuthToken)
        .filter(OAuthToken.tenant_id == tenant_id, OAuthToken.provider == "economic")
        .first()
    )
    if existing:
        existing.access_token = token
        existing.refresh_token = None
        existing.expires_at = None
        db.commit()
        db.refresh(existing)
        oauth_token = existing
    else:
        oauth_token = OAuthToken(
            user_id=tenant_id,
            provider="economic",
            access_token=token,
            refresh_token=None,
            expires_at=None,
            tenant_id=tenant_id,
        )
        db.add(oauth_token)
        db.commit()
        db.refresh(oauth_token)

    logger.info(
        "E-conomic connected. token_id=%s tenant_id=%s entity_name=%s",
        oauth_token.id,
        tenant_id,
        state_data.get("entity_name"),
    )

    # Auto-sync the entity — import here to avoid circular dependency
    from app.api.entities import sync_economic_entity_from_token  # noqa: PLC0415

    try:
        entity_result = await sync_economic_entity_from_token(oauth_token, db, self_data)
    except Exception as exc:
        logger.warning("Entity auto-sync failed after E-conomic connect (token saved): %s", exc)
        entity_result = None

    return {
        "status": "connected",
        "provider": "economic",
        "token_id": str(oauth_token.id),
        "tenant_id": oauth_token.tenant_id,
        "entity": entity_result,
    }
