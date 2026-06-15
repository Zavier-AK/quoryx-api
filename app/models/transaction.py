from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import relationship
import uuid
import enum

from app.core.crypto import EncryptedString
from app.models.database import Base


class ReconciliationStatus(str, enum.Enum):
    PENDING = "pending"
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    DISPUTED = "disputed"


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, default="default_user")
    # Supabase user id (JWT `sub`) that owns this connection — root of ownership;
    # entities/transactions stamped from here.
    owner_id = Column(String(255), nullable=True, index=True)
    provider = Column(String(50), nullable=False)  # "xero" or "quickbooks"
    access_token = Column(EncryptedString, nullable=False)
    refresh_token = Column(EncryptedString, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    tenant_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="token")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Owner (Supabase `sub`), inherited from the entity/token this row belongs to.
    owner_id = Column(String(255), nullable=True, index=True)
    token_id = Column(Uuid(as_uuid=True), ForeignKey("oauth_tokens.id"), nullable=False)
    entity_id = Column(Uuid(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    external_id = Column(String(255), nullable=False)  # Xero BankTransactionID
    provider = Column(String(50), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    description = Column(String(500), nullable=True)
    transaction_date = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default=ReconciliationStatus.PENDING)
    contact_name = Column(String(255), nullable=True)
    account_code = Column(String(50), nullable=True)
    transaction_type = Column(String(50), nullable=True)
    reference = Column(String(255), nullable=True)
    raw_payload = Column(Text, nullable=True)
    matched_transaction_id = Column(
        Uuid(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    token = relationship("OAuthToken", back_populates="transactions")
    entity = relationship("Entity", foreign_keys=[entity_id])
    matched_transaction = relationship("Transaction", remote_side=[id])
