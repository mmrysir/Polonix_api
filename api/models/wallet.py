import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, func, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class WalletType:
    FUNDING = "FUNDING"
    SPOT = "SPOT"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(20), nullable=False)
    asset = Column(String(20), nullable=False)
    available_balance = Column(Numeric(36, 18), default=0, nullable=False)
    reserved_balance = Column(Numeric(36, 18), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="wallets")

    __table_args__ = (
        CheckConstraint("available_balance >= 0", name="ck_wallet_available_nonneg"),
        CheckConstraint("reserved_balance >= 0", name="ck_wallet_reserved_nonneg"),
        UniqueConstraint("user_id", "type", "asset", name="uq_user_wallet_asset"),
    )