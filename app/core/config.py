from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me"
    APP_DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./quoryx.db"

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


settings = Settings()
