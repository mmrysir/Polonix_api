import uuid

from sqlalchemy import Column, DateTime, Enum, String, func
from sqlalchemy.orm import relationship

from ..database import Base


def _uuid():
    return str(uuid.uuid4())


class UserRole:
    USER = "USER"
    SUPPORT = "SUPPORT"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


class AccountStatus:
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    wallet_address = Column(String(255), unique=True, nullable=True)
    role = Column(String(20), default=UserRole.USER, nullable=False)
    status = Column(String(20), default=AccountStatus.PENDING_APPROVAL, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    wallets = relationship("Wallet", back_populates="user", cascade="all, delete-orphan")