from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_approved
from ..models.user import User
from ..models.wallet import Wallet, WalletType
from ..models.trading import FuturesPosition, OrderSide
from ..models.ledger import LedgerEntry, LedgerEntryType
from pydantic import BaseModel, Field

router = APIRouter(prefix="/trading/futures", tags=["Futures 200x Trading"])

MAX_LEVERAGE = 200


class OpenFuturesPositionRequest(BaseModel):
    symbol: str = Field(..., example="BTC/USDT")
    side: str = Field(..., example="LONG")
    leverage: int = Field(..., ge=1, le=200, example=50)
    margin: Decimal = Field(..., gt=0, example=100.00)
    entry_price: Decimal = Field(..., example=92450.00)


@router.post("/positions/open")
def open_futures_position(
    req: OpenFuturesPositionRequest,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
):
    from ..deps import ensure_wallet
    wallet = ensure_wallet(db, user.id, WalletType.FUTURES, "USDT")
    if (wallet.available_balance or 0) < req.margin:
        raise HTTPException(status_code=400, detail="Insufficient available USDT margin in Futures wallet.")

    wallet.available_balance = (wallet.available_balance or 0) - req.margin
    wallet.reserved_balance = (wallet.reserved_balance or 0) + req.margin

    leverage_dec = Decimal(str(req.leverage))
    if req.side.upper() == "LONG":
        liq_price = req.entry_price * (Decimal("1") - (Decimal("1") / leverage_dec))
    else:
        liq_price = req.entry_price * (Decimal("1") + (Decimal("1") / leverage_dec))

    import uuid as _uuid
    position_id = str(_uuid.uuid4())
    position = FuturesPosition(
        id=position_id,
        user_id=user.id,
        symbol=req.symbol,
        side="LONG" if req.side.upper() == "LONG" else "SHORT",
        leverage=req.leverage,
        margin_usdt=req.margin,
        notional_position_usdt=req.margin * leverage_dec,
        entry_price=req.entry_price,
        liquidation_price=liq_price,
        is_open=True,
        unrealized_pnl=Decimal("0"),
    )
    db.add(position)

    ledger = LedgerEntry(
        id=str(_uuid.uuid4()),
        transaction_id=str(_uuid.uuid4()),
        user_id=user.id,
        wallet_id=wallet.id,
        asset="USDT",
        amount=-req.margin,
        type=LedgerEntryType.FUTURES_MARGIN,
        idempotency_key=f"FUTURES-LOCK-{position_id}",
        reference_id=position_id,
    )
    db.add(ledger)
    db.commit()
    db.refresh(position)
    return {"message": "Position opened successfully", "position_id": position_id, "liquidation_price": str(liq_price)}


@router.get("/positions")
def list_futures_positions(user: User = Depends(require_approved), db: Session = Depends(get_db)):
    positions = db.query(FuturesPosition).filter_by(user_id=user.id, is_open=True).all()
    return [
        {
            "id": p.id,
            "symbol": p.symbol,
            "side": p.side,
            "leverage": p.leverage,
            "margin_usdt": str(p.margin_usdt),
            "notional_position_usdt": str(p.notional_position_usdt),
            "entry_price": str(p.entry_price),
            "liquidation_price": str(p.liquidation_price),
            "unrealized_pnl": str(p.unrealized_pnl or 0),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in positions
    ]


@router.post("/positions/{position_id}/close")
def close_futures_position(
    position_id: str,
    mark_price: Decimal,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
):
    position = db.query(FuturesPosition).filter_by(id=position_id, user_id=user.id, is_open=True).first()
    if not position:
        raise HTTPException(status_code=404, detail="Open position not found.")

    position_size = position.notional_position_usdt / position.entry_price
    if position.side == "LONG":
        pnl = (mark_price - position.entry_price) * position_size
    else:
        pnl = (position.entry_price - mark_price) * position_size

    position.is_open = False
    position.unrealized_pnl = pnl

    wallet = db.query(Wallet).filter_by(user_id=position.user_id, type=WalletType.FUTURES, asset="USDT").first()
    if wallet:
        wallet.reserved_balance = (wallet.reserved_balance or 0) - position.margin_usdt
        wallet.available_balance = (wallet.available_balance or 0) + (position.margin_usdt + pnl)

    import uuid as _uuid
    ledger = LedgerEntry(
        id=str(_uuid.uuid4()),
        transaction_id=str(_uuid.uuid4()),
        user_id=position.user_id,
        wallet_id=wallet.id if wallet else None,
        asset="USDT",
        amount=position.margin_usdt + pnl,
        type=LedgerEntryType.FUTURES_PNL,
        idempotency_key=f"FUTURES-CLOSE-{position_id}",
        reference_id=position_id,
    )
    db.add(ledger)
    db.commit()
    return {"message": "Position closed", "pnl": str(pnl), "payout": str(position.margin_usdt + pnl)}