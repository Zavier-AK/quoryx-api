import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_state_token

logger = logging.getLogger(__name__)

XERO_AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"
XERO_SCOPES = "accounting.transactions.read accounting.contacts.read accounting.settings.read offline_access"

QB_AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"
QB_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QB_SCOPES = "com.intuit.quickbooks.accounting"

# E-conomic authenticates with two static header tokens and has no token
# refresh/expiry. ECONOMIC_REST_BASE serves sales invoices and /self;
# ECONOMIC_APP_BASE is the companion OpenAPI host (e.g. supplier invoices).
ECONOMIC_REST_BASE = "https://restapi.e-conomic.com"
ECONOMIC_APP_BASE = "https://apis.e-conomic.com"

# Refresh the token this many seconds before it actually expires
TOKEN_REFRESH_BUFFER_SECONDS = 300


class OAuthService:
    def get_xero_authorization_url(self) -> tuple[str, str]:
        """Return (authorization_url, state) for starting the Xero OAuth flow."""
        state = generate_state_token()
        client = AsyncOAuth2Client(
            client_id=settings.XERO_CLIENT_ID,
            redirect_uri=settings.XERO_REDIRECT_URI,
            scope=XERO_SCOPES,
        )
        url, _ = client.create_authorization_url(XERO_AUTHORIZE_URL, state=state)
        return url, state

    def get_quickbooks_authorization_url(self) -> tuple[str, str]:
        """Return (authorization_url, state) for starting the QuickBooks OAuth flow."""
        state = generate_state_token()
        client = AsyncOAuth2Client(
            client_id=settings.QB_CLIENT_ID,
            redirect_uri=settings.QB_REDIRECT_URI,
            scope=QB_SCOPES,
        )
        url, _ = client.create_authorization_url(QB_AUTHORIZE_URL, state=state)
        return url, state

    async def exchange_xero_code(self, code: str) -> dict:
        """Exchange an authorization code for Xero tokens and fetch the tenant ID."""
        async with AsyncOAuth2Client(
            client_id=settings.XERO_CLIENT_ID,
            client_secret=settings.XERO_CLIENT_SECRET,
            redirect_uri=settings.XERO_REDIRECT_URI,
        ) as client:
            token = await client.fetch_token(XERO_TOKEN_URL, code=code)

        access_token = token["access_token"]
        refresh_token = token.get("refresh_token")
        expires_at_ts = token.get("expires_at")

        tenant_id = await self._fetch_xero_tenant_id(access_token)
        logger.info("Xero OAuth token exchange successful. tenant_id=%s", tenant_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": (
                datetime.utcfromtimestamp(expires_at_ts) if expires_at_ts else None
            ),
            "tenant_id": tenant_id,
        }

    async def _fetch_xero_tenant_id(self, access_token: str) -> Optional[str]:
        """Call the Xero connections API and return the first connected tenant ID."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                XERO_CONNECTIONS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            connections = resp.json()
            if connections:
                return connections[0]["tenantId"]
        return None

    def is_token_expired(self, token_record) -> bool:
        """Return True if the token is expired or within the refresh buffer window."""
        if token_record.expires_at is None:
            return False
        threshold = datetime.utcnow() + timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS)
        return token_record.expires_at <= threshold

    async def refresh_xero_token(self, token_record, db: Session) -> str:
        """
        Use the stored refresh_token to obtain a new Xero access_token.
        Updates the database record in place and returns the new access_token.
        """
        logger.info(
            "Refreshing Xero access token. token_id=%s", token_record.id
        )
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                XERO_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token_record.refresh_token,
                },
                auth=(settings.XERO_CLIENT_ID, settings.XERO_CLIENT_SECRET),
            )
            resp.raise_for_status()
            new_token = resp.json()

        token_record.access_token = new_token["access_token"]
        if new_token.get("refresh_token"):
            token_record.refresh_token = new_token["refresh_token"]
        expires_in = new_token.get("expires_in", 1800)
        token_record.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        token_record.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(token_record)

        logger.info(
            "Xero token refreshed successfully. token_id=%s", token_record.id
        )
        return token_record.access_token

    async def get_valid_xero_access_token(self, token_record, db: Session) -> str:
        """Return a valid Xero access token, refreshing it automatically if expired."""
        if self.is_token_expired(token_record):
            return await self.refresh_xero_token(token_record, db)
        return token_record.access_token

    async def exchange_quickbooks_code(self, code: str, realm_id: str) -> dict:
        """Exchange an authorization code for QuickBooks tokens."""
        async with AsyncOAuth2Client(
            client_id=settings.QB_CLIENT_ID,
            client_secret=settings.QB_CLIENT_SECRET,
            redirect_uri=settings.QB_REDIRECT_URI,
        ) as client:
            token = await client.fetch_token(QB_TOKEN_URL, code=code)

        expires_at_ts = token.get("expires_at")
        return {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "expires_at": (
                datetime.utcfromtimestamp(expires_at_ts) if expires_at_ts else None
            ),
            "realm_id": realm_id,
        }

    # ------------------------------------------------------------------
    # E-conomic — static header tokens, no OAuth2 exchange or refresh
    # ------------------------------------------------------------------

    def get_economic_install_url(self) -> tuple[str, str]:
        """
        Return (installation_url, state) for starting the E-conomic connect flow.

        The customer is sent to our app's Installation URL. After granting access,
        E-conomic redirects to our ECONOMIC_REDIRECT_URI with the grant token as
        ?token=xxx. We thread `state` through redirectUrl for CSRF protection.
        """
        state = generate_state_token()
        sep = "&" if "?" in settings.ECONOMIC_INSTALLATION_URL else "?"
        redirect = f"{settings.ECONOMIC_REDIRECT_URI}?state={state}"
        url = (
            f"{settings.ECONOMIC_INSTALLATION_URL}{sep}"
            f"redirectUrl={quote(redirect, safe='')}"
        )
        return url, state

    def economic_headers(self, grant_token: str) -> dict:
        """Return the two static auth headers every E-conomic request needs."""
        return {
            "X-AppSecretToken": settings.ECONOMIC_APP_SECRET_TOKEN,
            "X-AgreementGrantToken": grant_token,
            "Accept": "application/json",
        }


oauth_service = OAuthService()
