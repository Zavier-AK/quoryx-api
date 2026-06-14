from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.auth import require_service_key
from app.models.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    """Basic liveness check."""
    return {"status": "ok"}


@router.get("/health/db", dependencies=[Depends(require_service_key)])
def db_health_check(db: Session = Depends(get_db)):
    """Readiness check: verifies database connectivity."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
