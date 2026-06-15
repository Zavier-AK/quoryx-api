import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me"
    # Secure by default: /docs and /redoc are only exposed when explicitly enabled.
    APP_DEBUG: bool = False

    DATABASE_URL: str = "sqlite:///./quoryx.db"

    # --- API security (Phase 1) ---
    # Master switch for the auth layer. Lets prod deploy the code, set the secrets
    # and update callers, then flip auth on without a redeploy gap.
    AUTH_ENABLED: bool = True
    # Shared secret for machine-to-machine callers (e.g. run-integration.ts) sent
    # as the X-API-Key header.
    SERVICE_API_KEY: str = ""
    # Supabase project JWT secret (HS256) used to verify frontend bearer tokens.
    SUPABASE_JWT_SECRET: str = ""

    # --- Secrets at rest (Phase 3) ---
    # urlsafe-base64 Fernet key used to encrypt OAuth tokens at rest. When empty,
    # encryption no-ops and legacy plaintext tokens pass through unchanged.
    TOKEN_ENCRYPTION_KEY: str = ""

    # Where OAuth/connect redirect callbacks send the browser after finishing, so
    # the user lands back in the dashboard instead of on a raw-JSON page.
    FRONTEND_BASE_URL: str = "https://carbon-copy-cat.lovable.app"

    # Used by the TypeScript engine / integration scripts, but declared here so a
    # shared .env containing them does not break the Python app on local boot.
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    XERO_CLIENT_ID: str = ""
    XERO_CLIENT_SECRET: str = ""
    XERO_REDIRECT_URI: str = "http://localhost:8000/api/auth/xero/callback"

    QB_CLIENT_ID: str = ""
    QB_CLIENT_SECRET: str = ""
    QB_REDIRECT_URI: str = "http://localhost:8000/api/auth/quickbooks/callback"
    QB_ENVIRONMENT: str = "sandbox"

    # E-conomic uses static header tokens, not OAuth2. The app secret token is
    # permanent and identifies our app; the per-customer grant token never expires.
    ECONOMIC_APP_SECRET_TOKEN: str = ""
    ECONOMIC_INSTALLATION_URL: str = ""
    ECONOMIC_REDIRECT_URI: str = "http://localhost:8000/api/auth/economic/callback"

    class Config:
        env_file = ".env"
        case_sensitive = True
        # Ignore any other keys present in a shared .env (e.g. keys for other
        # services / future integrations) instead of raising on startup.
        extra = "ignore"

    @model_validator(mode="after")
    def _validate_secure_by_default(self) -> "Settings":
        if self.APP_ENV == "production" and self.APP_SECRET_KEY in ("", "change-me"):
            raise ValueError(
                "APP_SECRET_KEY must be set to a non-default value when APP_ENV=production"
            )
        # The following are intentionally warn-only so existing production deploys
        # (AUTH_ENABLED=false, no TOKEN_ENCRYPTION_KEY) keep booting. Token
        # encryption already no-ops when TOKEN_ENCRYPTION_KEY is empty.
        if self.APP_ENV == "production" and not self.TOKEN_ENCRYPTION_KEY:
            logger.warning(
                "TOKEN_ENCRYPTION_KEY is not set in production; OAuth tokens are "
                "stored as plaintext."
            )
        if self.APP_ENV == "production" and not self.SERVICE_API_KEY:
            logger.warning(
                "SERVICE_API_KEY is not set in production."
            )
        return self


settings = Settings()
