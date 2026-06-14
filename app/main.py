import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.ratelimit import limiter
from app.api import health, auth, transactions, xero, economic, entities, reconciliation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="Quoryx",
    description="Intercompany reconciliation platform",
    version="0.1.0",
    docs_url="/docs" if settings.APP_DEBUG else None,
    redoc_url="/redoc" if settings.APP_DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://carbon-copy-cat.lovable.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting: SlowAPIMiddleware enforces the default per-IP limit on every
# route; expensive routes layer a tighter @limiter.limit(...) on top.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

API_PREFIX = "/api"

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(transactions.router, prefix=API_PREFIX)
app.include_router(xero.router, prefix=API_PREFIX)
app.include_router(economic.router, prefix=API_PREFIX)
app.include_router(entities.router, prefix=API_PREFIX)
app.include_router(reconciliation.router, prefix=API_PREFIX)
