"""add owner_id for tenant isolation (Phase 2)

Stamps a Supabase user id (the JWT `sub` claim) onto every row a customer owns, so
a single user only ever sees their own entities / transactions / matches. The
backend writes via a service connection (which bypasses Supabase RLS so it can run
cross-entity matching within ONE owner), and the dashboard reads the three
customer-facing tables directly through Supabase — so the real per-user guard is
the RLS policy `owner_id = auth.uid()` on those tables (applied separately,
out-of-band, since it is a production-data change).

owner_id is nullable: existing rows predate isolation and are backfilled / left
null (visible only to the service connection, never to an anon/user session once
RLS is on). New rows are stamped at connect, ingest, and detection.

Revision ID: 0005_add_owner_id
Revises: 0004_add_match_decisions
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_owner_id"
down_revision: Union[str, None] = "0004_add_match_decisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that carry an owner. oauth_tokens is the root of ownership (stamped at
# connect); entities/transactions/intercompany_transactions inherit it. The first
# three are read directly by the dashboard and therefore need RLS.
_TABLES = (
    "oauth_tokens",
    "entities",
    "transactions",
    "intercompany_transactions",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("owner_id", sa.String(255), nullable=True))
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_owner_id", table_name=table)
        op.drop_column(table, "owner_id")
