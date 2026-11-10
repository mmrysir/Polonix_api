from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_approved
from ..models.user import User
from ..models.wallet import Wallet, WalletType
from ..models.trading import Order, OrderSide, OrderType, OrderStatus
from ..models.ledger import LedgerEntry, LedgerEntryType
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal as _D


router = APIRouter(prefix="/trading/spot", tags=["Spot Trading Engine"])


class SpotOrderCreateRequest(BaseModel):
    symbol: str = Field(..., example="BTC/USDT")
    side: str = Field(..., example="BUY")
    order_type: str = Field(..., example="LIMIT")
    price: Decimal = Field(..., example=92450.00)
    quantity: Decimal = Field(..., example=0.05)

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def _dec(cls, v):
        return _D(str(v))

class SpotOrderResponse(BaseModel):
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: Decimal
    quantity: Decimal
    status: str
    reserved_asset: str
    reserved_amount: Decimal


def get_current_approved_user(user=Depends(require_approved)):
    return user


@router.post("/orders", response_model=SpotOrderResponse)
def place_spot_order(
    req: SpotOrderCreateRequest,
    user: User = Depends(get_current_approved_user),
    db: Session = Depends(get_db),
):
    symbol_clean = req.symbol.upper()
    if "/" not in symbol_clean:
        raise HTTPException(status_code=400, detail="Invalid symbol format. Use BASE/QUOTE.")
    base_asset, quote_asset = symbol_clean.split("/")

    side_upper = req.side.upper()
    type_upper = req.order_type.upper()
    side_enum = OrderSide.BUY if side_upper == "BUY" else OrderSide.SELL
    type_enum = OrderType.LIMIT if type_upper == "LIMIT" else OrderType.MARKET

    if side_enum == OrderSide.BUY:
        required_asset = quote_asset
        required_amount = req.price * req.quantity
    else:
        required_asset = base_asset
        required_amount = req.quantity

    from ..deps import ensure_wallet
    wallet = ensure_wallet(db, user.id, WalletType.SPOT, required_asset)
    if (wallet.available_balance or 0) < required_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient available {required_asset} balance. Required: {required_amount}, Available: {wallet.available_balance if wallet else 0}",
        )

    # Atomic reservation
    wallet.available_balance = wallet.available_balance - required_amount
    wallet.reserved_balance = (wallet.reserved_balance or 0) + required_amount

    import uuid as _uuid
    order_id = str(_uuid.uuid4())
    order = Order(
        id=order_id,
        user_id=user.id,
        symbol=symbol_clean,
        wallet_type=WalletType.SPOT,
        side=side_enum,
        type=type_enum,
        price=req.price,
        quantity=req.quantity,
        filled_quantity=Decimal("0"),
        status=OrderStatus.OPEN if hasattr(OrderStatus, "OPEN") else "OPEN",
        fee_paid=Decimal("0"),
        idempotency_key=str(_uuid.uuid4()),
    )
    db.add(order)

    ledger_entry = LedgerEntry(
        id=str(_uuid.uuid4()),
        transaction_id=str(_uuid.uuid4()),
        user_id=user.id,
        wallet_id=wallet.id,
        asset=required_asset,
        amount=-required_amount,
        type=LedgerEntryType.SPOT_TRADE,
        idempotency_key=f"SPOT-RESERVE-{order_id}",
        reference_id=order_id,
    )
    db.add(ledger_entry)
    db.commit()
    db.refresh(order)

    return SpotOrderResponse(
        order_id=order.id,
        symbol=order.symbol,
        side=str(order.side),
        order_type=str(order.type),
        price=req.price,
        quantity=req.quantity,
        status=str(order.status),
        reserved_asset=required_asset,
        reserved_amount=required_amount,
    )


@router.get("/orders/active")
def get_active_spot_orders(user: User = Depends(get_current_approved_user), db: Session = Depends(get_db)):
    orders = db.query(Order).filter_by(user_id=user.id, status="OPEN").all()
    return [
        {
            "id": o.id,
            "symbol": o.symbol,
            "side": str(o.side),
            "type": str(o.type),
            "price": str(o.price),
            "quantity": str(o.quantity),
            "filled_quantity": str(o.filled_quantity),
            "status": str(o.status),
        }
        for o in orders
    ]


@router.post("/orders/{order_id}/cancel")
def cancel_spot_order(order_id: str, user: User = Depends(get_current_approved_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter_by(id=order_id, user_id=user.id).first()
    if not order or str(order.status) != "OPEN":
        raise HTTPException(status_code=404, detail="Active order not found or already completed/cancelled.")

    base_asset, quote_asset = order.symbol.split("/")
    required_asset = quote_asset if str(order.side).upper() == "BUY" else base_asset
    filled = order.filled_quantity or Decimal("0")
    released_amount = (order.price * (order.quantity - filled)) if str(order.side).upper() == "BUY" else (order.quantity - filled)
    released_amount = _D(str(released_amount)).quantize(_D("0.000000000000000001"))

    order.status = "CANCELLED"

    wallet = db.query(Wallet).filter_by(user_id=user.id, type=WalletType.SPOT, asset=required_asset).first()
    if wallet:
        if released_amount > (wallet.reserved_balance or 0):
            released_amount = wallet.reserved_balance or _D("0")
        wallet.reserved_balance = (wallet.reserved_balance or 0) - released_amount
        wallet.available_balance = (wallet.available_balance or 0) + released_amount

    import uuid as _uuid
    reversal_entry = LedgerEntry(
        id=str(_uuid.uuid4()),
        transaction_id=str(_uuid.uuid4()),
        user_id=user.id,
        wallet_id=wallet.id if wallet else None,
        asset=required_asset,
        amount=released_amount,
        type=LedgerEntryType.SPOT_TRADE,
        idempotency_key=f"SPOT-CANCEL-REFUND-{order_id}",
        reference_id=order_id,
    )
    db.add(reversal_entry)
    db.commit()
    return {"message": "Order cancelled successfully and funds released", "order_id": order_id}