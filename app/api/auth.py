import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import require_user
from app.core.config import settings
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


async def _connect_economic(
    grant_token: str,
    db: Session,
    entity_name: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict:
    """
    Resolve an E-conomic grant token to its agreement, upsert the OAuthToken, and
    sync the entity. Shared by the redirect callback and the manual-paste endpoint.
    The grant token is permanent — no code exchange, refresh, or expiry.

    owner_id is the Supabase user id (JWT `sub`) of the connecting user; it is
    stamped onto the token and entity so tenant isolation holds downstream. The
    redirect callback has no authenticated user, so it passes None (the manual
    /connect endpoint, which is what the dashboard uses, always supplies it).
    """
    # Imports here to avoid a circular import at module load.
    from app.api.economic import fetch_economic_self  # noqa: PLC0415
    from app.api.entities import sync_economic_entity_from_token  # noqa: PLC0415

    try:
        self_data = await fetch_economic_self(grant_token)
    except Exception as exc:
        logger.error("E-conomic /self lookup failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Could not verify the agreement token with E-conomic",
        )

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
        existing.access_token = grant_token
        existing.refresh_token = None
        existing.expires_at = None
        if owner_id:
            existing.owner_id = owner_id
        db.commit()
        db.refresh(existing)
        oauth_token = existing
    else:
        oauth_token = OAuthToken(
            user_id=tenant_id,
            owner_id=owner_id,
            provider="economic",
            access_token=grant_token,
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
        entity_name,
    )

    try:
        entity_result = await sync_economic_entity_from_token(oauth_token, db, self_data)
    except Exception as exc:
        logger.warning(
            "Entity auto-sync failed after E-conomic connect (token saved): %s", exc
        )
        entity_result = None

    return {
        "status": "connected",
        "provider": "economic",
        "token_id": str(oauth_token.id),
        "tenant_id": oauth_token.tenant_id,
        "entity": entity_result,
    }


@router.get("/economic/callback")
async def economic_callback(
    token: str = Query(...),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Redirect callback from e-conomic's install flow.

    e-conomic appends ?token=<grant> to our redirectUrl. When the flow is started
    from our own /economic/login we also round-trip a `state` token (CSRF + the
    entity label); but when a customer installs straight from e-conomic's app list
    there is no state to return, so it is optional here. If a state IS present it
    must be valid.

    This path has no authenticated dashboard user, so owner_id is not stamped here
    (the entity is claimed to an owner via the dashboard connect, or backfilled).

    On success the browser is redirected back into the dashboard (rather than left
    on a raw-JSON page); failures redirect with an ?error= flag.
    """
    entity_name = None
    if state is not None:
        state_data = _pending_states.pop(state, None)
        if not state_data or state_data.get("provider") != "economic":
            return RedirectResponse(
                url=f"{settings.FRONTEND_BASE_URL}/entities?error=invalid_state"
            )
        entity_name = state_data.get("entity_name")
    else:
        logger.info(
            "E-conomic callback without state (installed from the e-conomic app list)"
        )

    try:
        await _connect_economic(token, db, entity_name)
    except HTTPException as exc:
        logger.warning("E-conomic connect failed in callback: %s", exc.detail)
        return RedirectResponse(
            url=f"{settings.FRONTEND_BASE_URL}/entities?error=connect_failed"
        )
    return RedirectResponse(url=f"{settings.FRONTEND_BASE_URL}/entities?connected=economic")


class EconomicConnectRequest(BaseModel):
    token: str
    entity_name: Optional[str] = None


@router.post("/economic/connect")
async def economic_connect(
    body: EconomicConnectRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user),
):
    """
    Manual connect: the customer pastes their E-conomic agreement grant token
    (the "Connect agreement token" popup). Verifies it via /self and saves it.

    The connection (and everything ingested from it) is owned by the authenticated
    Supabase user — claims["sub"] — so it stays isolated to them.
    """
    token = body.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Agreement token is required")
    return await _connect_economic(
        token, db, body.entity_name, owner_id=claims.get("sub")
    )
