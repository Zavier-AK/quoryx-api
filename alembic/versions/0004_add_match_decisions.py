"""add match_decisions — feedback capture for future ML training

Every human decision in the review queue (approve / reject / correct) is recorded
here as ONE labeled example: the engine's feature snapshot at decision time plus the
human verdict (the label). This table is the training dataset that later unlocks a
feature classifier (and, much later, any fine-tuning) — without it there is no
labeled data to learn from. Populate it from the PATCH /pairs/{id}/status handler.

Revision ID: 0004_add_match_decisions
Revises: 0003_add_review_required_status
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_match_decisions"
down_revision: Union[str, None] = "0003_add_review_required_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "match_decisions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        # Which pair was reviewed.
        sa.Column(
            "pair_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("intercompany_transactions.id"),
            nullable=False,
        ),
        sa.Column("source_transaction_id", sa.String(255), nullable=True),
        sa.Column("target_transaction_id", sa.String(255), nullable=True),
        # --- The LABEL: the human verdict ---
        sa.Column("decision", sa.String(20), nullable=False),  # approved | rejected | corrected
        # If corrected, the transaction the reviewer matched it to instead.
        sa.Column("correct_target_transaction_id", sa.String(255), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # --- Prediction snapshot: what the engine said when the human decided ---
        sa.Column("predicted_confidence", sa.Float(), nullable=True),
        sa.Column("predicted_match_type", sa.String(20), nullable=True),
        # --- FEATURE snapshot: the scorer's per-dimension outputs = the X for training ---
        sa.Column("amount_score", sa.Float(), nullable=True),
        sa.Column("date_score", sa.Float(), nullable=True),
        sa.Column("type_score", sa.Float(), nullable=True),
        sa.Column("counterparty_score", sa.Float(), nullable=True),
        sa.Column("amount_difference", sa.Float(), nullable=True),
        sa.Column("days_difference", sa.Integer(), nullable=True),
        sa.Column("is_cross_currency", sa.Boolean(), nullable=True),
        sa.Column("same_provider", sa.Boolean(), nullable=True),
        sa.Column(
            "decided_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_match_decisions_pair_id", "match_decisions", ["pair_id"])
    op.create_index("ix_match_decisions_decision", "match_decisions", ["decision"])


def downgrade() -> None:
    op.drop_index("ix_match_decisions_decision", table_name="match_decisions")
    op.drop_index("ix_match_decisions_pair_id", table_name="match_decisions")
    op.drop_table("match_decisions")
