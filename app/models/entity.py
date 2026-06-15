from datetime import datetime
import uuid
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import relationship

from app.models.database import Base


class IntercompanyStatus(str, enum.Enum):
    UNMATCHED = "unmatched"
    MATCHED = "matched"
    RECONCILED = "reconciled"
    REVIEW_REQUIRED = "review_required"


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Supabase user id (JWT `sub`) that owns this entity — the tenant-isolation key.
    owner_id = Column(String(255), nullable=True, index=True)
    tenant_id = Column(String(255), nullable=False, unique=True)
    org_name = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False)
    country_code = Column(String(3), nullable=True)
    connected_at = Column(DateTime, default=datetime.utcnow)

    source_transactions = relationship(
        "IntercompanyTransaction",
        foreign_keys="IntercompanyTransaction.source_entity_id",
        back_populates="source_entity",
    )
    target_transactions = relationship(
        "IntercompanyTransaction",
        foreign_keys="IntercompanyTransaction.target_entity_id",
        back_populates="target_entity",
    )


class IntercompanyTransaction(Base):
    __tablename__ = "intercompany_transactions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Owner (Supabase `sub`) — both sides of a pair share one owner; matching never
    # crosses owners.
    owner_id = Column(String(255), nullable=True, index=True)
    source_entity_id = Column(
        Uuid(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    target_entity_id = Column(
        Uuid(as_uuid=True), ForeignKey("entities.id"), nullable=True
    )
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    description = Column(String(500), nullable=True)
    transaction_date = Column(DateTime, nullable=False)
    status = Column(
        Enum(IntercompanyStatus),
        nullable=False,
        default=IntercompanyStatus.UNMATCHED,
    )
    source_transaction_id = Column(String(255), nullable=True)
    target_transaction_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Scorer columns
    confidence_score = Column(Float, nullable=True)
    match_type = Column(String(20), nullable=True)
    amount_difference = Column(Float, nullable=True)
    days_difference = Column(Integer, nullable=True)
    match_reasons = Column(Text, nullable=True)
    llm_reasoning = Column(Text, nullable=True)
    review_required = Column(Boolean, nullable=True, default=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String(255), nullable=True)

    source_entity = relationship(
        "Entity",
        foreign_keys=[source_entity_id],
        back_populates="source_transactions",
    )
    target_entity = relationship(
        "Entity",
        foreign_keys=[target_entity_id],
        back_populates="target_transactions",
    )
