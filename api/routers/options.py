from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_approved
from ..models.user import User
from ..models.wallet import Wallet, WalletType
from ..models.trading import OptionsContract
from ..models.ledger import LedgerEntry, LedgerEntryType
from pydantic import BaseModel, Field

router = APIRouter(prefix="/trading/options", tags=["Binary Options Engine"])

PAYOUT_RATES = {
    "30s": Decimal("0.85"),
    "60s": Decimal("0.88"),
    "120s": Decimal("0.90"),
    "5m": Decimal("0.92"),
    "15m": Decimal("0.95"),
}

DURATION_SECONDS = {
    "30s": 30,
    "60s": 60,
    "120s": 120,
    "5m": 300,
    "15m": 900,
}


class CreateOptionsContractRequest(BaseModel):
    symbol: str = Field(..., example="BTC/USDT")
    direction: str = Field(..., example="CALL")  # CALL or PUT
    duration: str = Field(..., example="120s")
    stake_amount: Decimal = Field(..., gt=0, example=100.00)
    entry_price: Decimal = Field(..., example=92450.00)


@router.post("/contracts/create")
def create_options_contract(
    body: CreateOptionsContractRequest,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
):
    if body.duration not in PAYOUT_RATES:
        raise HTTPException(status_code=400, detail="Invalid options duration key.")

    from ..deps import ensure_wallet
    wallet = ensure_wallet(db, user.id, WalletType.OPTIONS, "USDT")
    fee = body.stake_amount * Decimal("0.0095")
    total_cost = body.stake_amount + fee
    if not wallet or (wallet.available_balance or 0) < total_cost:
        raise HTTPException(status_code=400, detail="Insufficient USDT in Options wallet.")

    wallet.available_balance = (wallet.available_balance or 0) - total_cost
    wallet.reserved_balance = (wallet.reserved_balance or 0) + total_cost

    import uuid as _uuid
    contract_id = str(_uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(seconds=DURATION_SECONDS[body.duration])
    contract = OptionsContract(
        id=contract_id,
        user_id=user.id,
        asset=body.symbol.split("/")[0],
        direction=body.direction.upper(),
        duration=body.duration,
        stake_amount=body.stake_amount,
        fee_amount=fee,
        entry_price=body.entry_price,
        target_payout_rate=PAYOUT_RATES[body.duration],
        status="ACTIVE",
        expires_at=expires_at,
    )
    db.add(contract)

    ledger = LedgerEntry(
        id=str(_uuid.uuid4()),
        transaction_id=str(_uuid.uuid4()),
        user_id=user.id,
        wallet_id=wallet.id,
        asset="USDT",
        amount=-total_cost,
        type=LedgerEntryType.OPTIONS_STAKE,
        idempotency_key=f"OPTIONS-STAKE-{contract_id}",
        reference_id=contract_id,
    )
    db.add(ledger)
    db.commit()
    db.refresh(contract)
    target_payout = body.stake_amount * (Decimal("1") + PAYOUT_RATES[body.duration])
    return {
        "contract_id": contract_id,
        "expires_at": expires_at.isoformat(),
        "target_payout": str(target_payout),
        "fee": str(fee),
    }


@router.get("/contracts/active")
def list_active_options(user: User = Depends(require_approved), db: Session = Depends(get_db)):
    contracts = db.query(OptionsContract).filter_by(user_id=user.id, status="ACTIVE").all()
    return [
        {
            "id": c.id,
            "asset": c.asset,
            "direction": c.direction,
            "duration": c.duration,
            "stake_amount": str(c.stake_amount),
            "entry_price": str(c.entry_price),
            "target_payout_rate": str(c.target_payout_rate),
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "status": c.status,
        }
        for c in contracts
    ]


@router.post("/settle")
def settle_expired_options(
    current_market_price: Decimal,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
):
    # Settle for the user's active expired contracts using provided mark price
    results = settle_expired_for_asset(db, None, current_market_price) if False else []
    # Fallback: settle all of this user's expired contracts with the given price
    now = datetime.utcnow()
    expired = db.query(OptionsContract).filter(
        OptionsContract.user_id == user.id,
        OptionsContract.status == "ACTIVE",
        OptionsContract.expires_at <= now,
    ).all()
    results = []
    for c in expired:
        is_win = (c.direction == "CALL" and current_market_price > c.entry_price) or \
                 (c.direction == "PUT" and current_market_price < c.entry_price)
        c.expiry_price = current_market_price
        wallet = db.query(Wallet).filter_by(user_id=c.user_id, type=WalletType.OPTIONS, asset="USDT").first()
        total_cost = c.stake_amount + c.fee_amount
        if wallet:
            wallet.reserved_balance = (wallet.reserved_balance or 0) - total_cost
        if is_win:
            c.status = "WON"
            payout = c.stake_amount * (Decimal("1") + c.target_payout_rate)
            if wallet:
                wallet.available_balance = (wallet.available_balance or 0) + payout
            c.payout_amount = payout
        else:
            c.status = "LOST"
            c.payout_amount = Decimal("0")
        import uuid as _uuid
        ledger = LedgerEntry(
            id=str(_uuid.uuid4()),
            transaction_id=str(_uuid.uuid4()),
            user_id=c.user_id,
            wallet_id=wallet.id if wallet else None,
            asset="USDT",
            amount=c.payout_amount if is_win else Decimal("0"),
            type=LedgerEntryType.OPTIONS_PAYOUT,
            idempotency_key=f"OPTIONS-SETTLE-{c.id}",
            reference_id=c.id,
        )
        db.add(ledger)
        results.append({"contract_id": c.id, "status": c.status, "payout": str(c.payout_amount)})
    if expired:
        db.commit()
    return {"settled": len(results), "results": results}