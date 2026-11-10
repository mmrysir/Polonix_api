import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_approved
from ..models.trading import FuturesPosition, OptionsContract, ConversionQuote, OPTIONS_PAYOUT
from ..models.user import User
from ..schemas.trading import FuturesOrder, OptionsContractRequest, ConvertQuoteRequest

router = APIRouter(prefix="/api/v1/trading", tags=["trading"])

MAX_LEVERAGE = 200


@router.post("/futures/order")
def futures_order(body: FuturesOrder, user: User = Depends(require_approved), db: Session = Depends(get_db)):
    if body.leverage > MAX_LEVERAGE or body.leverage < 1:
        raise HTTPException(status_code=400, detail="leverage_out_of_range")
    entry_price = Decimal("91450.00")
    notional = Decimal(str(body.margin_usdt)) * body.leverage
    liq = entry_price * (Decimal("1") - (Decimal("1") / (body.leverage * Decimal("2")))) if body.side.upper() == "LONG" else entry_price * (Decimal("1") + (Decimal("1") / (body.leverage * Decimal("2"))))
    pos = FuturesPosition(
        user_id=user.id,
        symbol=body.symbol,
        side=body.side.upper(),
        leverage=body.leverage,
        margin_usdt=Decimal(str(body.margin_usdt)),
        notional_position_usdt=notional,
        entry_price=entry_price,
        liquidation_price=liq,
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return {"id": pos.id, "leverage": pos.leverage, "liquidation_price": str(pos.liquidation_price)}


@router.post("/options/contract")
def options_contract(body: OptionsContractRequest, user: User = Depends(require_approved), db: Session = Depends(get_db)):
    rate = OPTIONS_PAYOUT.get(body.duration)
    if rate is None:
        raise HTTPException(status_code=400, detail="invalid_duration")
    entry_price = Decimal("91450.00")
    fee = Decimal(str(body.stake_amount)) * Decimal("0.0095")
    duration_seconds = {"30s": 30, "60s": 60, "120s": 120, "5m": 300, "15m": 900}[body.duration]
    contract = OptionsContract(
        user_id=user.id,
        asset=body.asset,
        direction=body.direction.upper(),
        duration=body.duration,
        stake_amount=Decimal(str(body.stake_amount)),
        fee_amount=fee,
        entry_price=entry_price,
        target_payout_rate=Decimal(str(rate)),
        expires_at=datetime.utcnow() + timedelta(seconds=duration_seconds),
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return {"id": contract.id, "duration": contract.duration, "target_payout_rate": str(contract.target_payout_rate),
            "expires_at": contract.expires_at.isoformat()}


@router.post("/convert/quote")
def convert_quote(body: ConvertQuoteRequest, db: Session = Depends(get_db)):
    from decimal import Decimal
    rate = Decimal("1.0")
    if body.from_asset == "BTC" and body.to_asset == "USDT":
        rate = Decimal("91450.0")
    elif body.from_asset == "USDT" and body.to_asset == "BTC":
        rate = Decimal("1") / Decimal("91450.0")
    else:
        rate = Decimal("1.0")
    est = Decimal(str(body.from_amount)) * rate
    fee_rate = Decimal("0.0095")
    fee = est * fee_rate
    net = est - fee
    fast_assets = {"BTC", "ETH", "SOL", "USDT", "USDC", "TRX"}
    if body.from_asset in fast_assets and body.to_asset in fast_assets:
        target = "<= 5 seconds"
    else:
        target = "15-20 minutes"
    import uuid
    q = ConversionQuote(
        user_id=body.user_id,
        from_asset=body.from_asset,
        to_asset=body.to_asset,
        from_amount=Decimal(str(body.from_amount)),
        exchange_rate=rate,
        estimated_received=net,
        execution_target_time=target,
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return {
        "quote_id": q.id,
        "from": body.from_asset,
        "to": body.to_asset,
        "rate": str(rate),
        "estimated_received": str(net),
        "fee": str(fee),
        "execution_target_time": target,
        "expires_at": q.expires_at.isoformat(),
    }