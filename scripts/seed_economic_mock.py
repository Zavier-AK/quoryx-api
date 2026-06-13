"""
Seed mock E-conomic data into the database for offline testing.

Runs the real E-conomic field mappers (app/api/economic.py) over fixture payloads
in data/economic-mock.json, so you can exercise the full ingestion -> detection ->
scoring pipeline WITHOUT a live e-conomic dev account.

Usage:
    python scripts/seed_economic_mock.py            # seed (idempotent upserts)
    python scripts/seed_economic_mock.py --reset    # drop + recreate tables first

After seeding, test the rest of the pipeline:
    uvicorn app.main:app --reload
    curl -X POST localhost:8000/api/reconciliation/run     # detects the IC pair
    curl localhost:8000/api/reconciliation/pairs           # inspect the pair
    npx ts-node scripts/run-integration.ts                 # score it with the engine
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Ensure the repo root is importable when run as `python scripts/seed_economic_mock.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.database import Base, SessionLocal, engine  # noqa: E402
from app.models.entity import Entity  # noqa: E402
from app.models.transaction import OAuthToken  # noqa: E402
from app.api.economic import (  # noqa: E402
    _map_economic_invoice,
    _map_economic_supplier_invoice,
    _upsert_transaction,
)

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "economic-mock.json"


def _upsert_entity(db, spec: dict) -> Entity:
    entity = db.query(Entity).filter(Entity.tenant_id == spec["tenant_id"]).first()
    if entity:
        entity.org_name = spec["org_name"]
        entity.currency = spec["currency"]
        entity.country_code = spec.get("country_code")
    else:
        entity = Entity(
            tenant_id=spec["tenant_id"],
            org_name=spec["org_name"],
            currency=spec["currency"],
            country_code=spec.get("country_code"),
            connected_at=datetime.utcnow(),
        )
        db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def _upsert_mock_token(db, tenant_id: str) -> OAuthToken:
    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.tenant_id == tenant_id, OAuthToken.provider == "economic")
        .first()
    )
    if not token:
        token = OAuthToken(
            user_id=tenant_id,
            provider="economic",
            access_token=f"mock-grant-token-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
        )
        db.add(token)
        db.commit()
        db.refresh(token)
    return token


def main() -> None:
    reset = "--reset" in sys.argv
    if reset:
        print("Dropping and recreating all tables...")
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    spec = json.loads(FIXTURE.read_text())
    db = SessionLocal()
    total_sales = total_supplier = 0
    try:
        for ent_spec in spec["entities"]:
            entity = _upsert_entity(db, ent_spec)
            token = _upsert_mock_token(db, entity.tenant_id)

            for item in ent_spec.get("sales_invoices", []):
                _upsert_transaction(db, _map_economic_invoice(item, entity, token))
                total_sales += 1
            for item in ent_spec.get("supplier_invoices", []):
                _upsert_transaction(
                    db, _map_economic_supplier_invoice(item, entity, token)
                )
                total_supplier += 1

            db.commit()
            print(f"  seeded {entity.org_name} (tenant={entity.tenant_id})")
    finally:
        db.close()

    print(
        f"\nDone. Seeded {total_sales} sales (RECEIVE) + {total_supplier} supplier "
        f"(SPEND) transactions across {len(spec['entities'])} E-conomic entities."
    )
    print("Designed intercompany pair shares reference IC-2026-01 (Holdco sale <-> Subco bill).")
    print("\nNext: POST /api/reconciliation/run, then GET /api/reconciliation/pairs")


if __name__ == "__main__":
    main()
