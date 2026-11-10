import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, func

from ..database import Base


class OrderSide:
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType:
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus:
    NEW = "NEW"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class ContractStatus:
    ACTIVE = "ACTIVE"
    WON = "WON"
    LOST = "LOST"
    EXPIRED = "EXPIRED"
    SETTLED = "SETTLED"


class OptionsDuration:
    S30 = "30s"
    S60 = "60s"
    S120 = "120s"
    M5 = "5m"
    M15 = "15m"


OPTIONS_PAYOUT = {"30s": 0.20, "60s": 0.30, "120s": 0.50, "5m": 0.60, "15m": 0.70}


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    wallet_type = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    type = Column(String(10), nullable=False)
    price = Column(Numeric(36, 18), nullable=True)
    quantity = Column(Numeric(36, 18), nullable=False)
    filled_quantity = Column(Numeric(36, 18), default=0)
    status = Column(String(20), default=OrderStatus.NEW)
    fee_paid = Column(Numeric(36, 18), default=0)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FuturesPosition(Base):
    __tablename__ = "futures_positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    leverage = Column(Integer, nullable=False)
    margin_usdt = Column(Numeric(36, 18), nullable=False)
    notional_position_usdt = Column(Numeric(36, 18), nullable=False)
    entry_price = Column(Numeric(36, 18), nullable=False)
    liquidation_price = Column(Numeric(36, 18), nullable=False)
    unrealized_pnl = Column(Numeric(36, 18), default=0)
    is_open = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)


class OptionsContract(Base):
    __tablename__ = "options_contracts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    asset = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)
    duration = Column(String(10), nullable=False)
    stake_amount = Column(Numeric(36, 18), nullable=False)
    fee_amount = Column(Numeric(36, 18), nullable=False)
    entry_price = Column(Numeric(36, 18), nullable=False)
    expiry_price = Column(Numeric(36, 18), nullable=True)
    target_payout_rate = Column(Numeric(5, 4), nullable=False)
    payout_amount = Column(Numeric(36, 18), default=0)
    status = Column(String(20), default=ContractStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)


class ConversionQuote(Base):
    __tablename__ = "conversion_quotes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    from_asset = Column(String(20), nullable=False)
    to_asset = Column(String(20), nullable=False)
    from_amount = Column(Numeric(36, 18), nullable=False)
    exchange_rate = Column(Numeric(36, 18), nullable=False)
    estimated_received = Column(Numeric(36, 18), nullable=False)
    platform_fee_rate = Column(Numeric(5, 4), default=0.0095)
    execution_target_time = Column(String(50), nullable=False)
    is_executed = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())