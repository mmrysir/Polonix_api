import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, func

from ..database import Base


class LedgerEntryType:
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
    CONVERSION_DEBIT = "CONVERSION_DEBIT"
    CONVERSION_CREDIT = "CONVERSION_CREDIT"
    SPOT_TRADE = "SPOT_TRADE"
    FUTURES_MARGIN = "FUTURES_MARGIN"
    FUTURES_PNL = "FUTURES_PNL"
    OPTIONS_STAKE = "OPTIONS_STAKE"
    OPTIONS_PAYOUT = "OPTIONS_PAYOUT"
    PLATFORM_FEE = "PLATFORM_FEE"
    BALANCE_ADJUSTMENT = "BALANCE_ADJUSTMENT"


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id = Column(String(36), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    wallet_id = Column(String(36), ForeignKey("wallets.id"), nullable=False)
    asset = Column(String(20), nullable=False)
    amount = Column(Numeric(36, 18), nullable=False)
    type = Column(String(30), nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    reference_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())