from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_approved
from ..models.user import User
from ..models.wallet import Wallet, WalletType
from ..models.trading import ConversionQuote
from ..models.ledger import LedgerEntry, LedgerEntryType
from pydantic import BaseModel, Field

router = APIRouter(prefix="/trading/convert", tags=["Universal Conversion Engine"])

FAST_ASSETS = {"BTC", "ETH", "SOL", "USDT", "USDC", "TRX"}


class ConvertQuoteRequest(BaseModel):
    from_asset: str
    to_asset: str
    from_amount: Decimal = Field(..., gt=0)
    user_id: str = None


class ExecuteQuoteRequest(BaseModel):
    pass


@router.post("/quote")
def create_convert_quote(body: ConvertQuoteRequest, db: Session = Depends(get_db), user: User = Depends(require_approved)):
    from_asset = body.from_asset.upper()
    to_asset = body.to_asset.upper()
    uid = body.user_id or user.id

    # Simple rate table (production: fetch from price oracle)
    rates = {
        ("BTC", "USDT"): Decimal("91450.0"),
        ("USDT", "BTC"): Decimal("1") / Decimal("91450.0"),
        ("ETH", "USDT"): Decimal("3340.5"),
        ("USDT", "ETH"): Decimal("1") / Decimal("3340.5"),
        ("SOL", "USDT"): Decimal("214.1"),
        ("USDT", "SOL"): Decimal("1") / Decimal("214.1"),
    }
    rate = rates.get((from_asset, to_asset), Decimal("1.0"))
    est = Decimal(str(body.from_amount)) * rate
    fee_rate = Decimal("0.0095")
    fee = est * fee_rate
    net = est - fee

    if from_asset in FAST_ASSETS and to_asset in FAST_ASSETS:
        target = "<= 5 seconds"
    else:
        target = "15-20 minutes"

    import uuid as _uuid
    q = ConversionQuote(
        id=str(_uuid.uuid4()),
        user_id=uid,
        from_asset=from_asset,
        to_asset=to_asset,
        from_amount=Decimal(str(body.from_amount)),
        exchange_rate=rate,
        estimated_received=net,
        platform_fee_rate=fee_rate,
        execution_target_time=target,
        is_executed=False,
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return {
        "quote_id": q.id,
        "from": from_asset,
        "to": to_asset,
        "rate": str(rate),
        "estimated_received": str(net),
        "fee": str(fee),
        "execution_target_time": target,
        "expires_at": q.expires_at.isoformat(),
    }


@router.post("/execute/{quote_id}")
def execute_conversion_quote(quote_id: str, db: Session = Depends(get_db), user: User = Depends(require_approved)):
    quote = db.query(ConversionQuote).filter_by(id=quote_id, is_executed=False).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Valid unexecuted quote not found.")
    if quote.user_id != user.id and user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="forbidden")
    if datetime.utcnow() > quote.expires_at:
        raise HTTPException(status_code=400, detail="Conversion quote has expired. Please request a new quote.")

    from ..deps import ensure_wallet
    src_wallet = ensure_wallet(db, quote.user_id, WalletType.SPOT, quote.from_asset)
    dst_wallet = db.query(Wallet).filter_by(user_id=quote.user_id, asset=quote.to_asset, type=WalletType.SPOT).first()

    if not src_wallet or (src_wallet.available_balance or 0) < quote.from_amount:
        raise HTTPException(status_code=400, detail=f"Insufficient {quote.from_asset} balance to complete swap.")

    src_wallet.available_balance = (src_wallet.available_balance or 0) - quote.from_amount
    if not dst_wallet:
        import uuid as _uuid
        dst_wallet = Wallet(id=str(_uuid.uuid4()), user_id=quote.user_id, asset=quote.to_asset, type=WalletType.SPOT, available_balance=Decimal("0"))
        db.add(dst_wallet)
    dst_wallet.available_balance = (dst_wallet.available_balance or 0) + quote.estimated_received
    quote.is_executed = True

    import uuid as _uuid
    tx_group = str(_uuid.uuid4())
    debit_entry = LedgerEntry(
        id=str(_uuid.uuid4()),
        transaction_id=tx_group,
        user_id=quote.user_id,
        wallet_id=src_wallet.id,
        asset=quote.from_asset,
        amount=-quote.from_amount,
        type=LedgerEntryType.CONVERSION_DEBIT,
        idempotency_key=f"CONV-DEBIT-{quote.id}",
        reference_id=quote.id,
    )
    credit_entry = LedgerEntry(
        id=str(_uuid.uuid4()),
        transaction_id=tx_group,
        user_id=quote.user_id,
        wallet_id=dst_wallet.id,
        asset=quote.to_asset,
        amount=quote.estimated_received,
        type=LedgerEntryType.CONVERSION_CREDIT,
        idempotency_key=f"CONV-CREDIT-{quote.id}",
        reference_id=quote.id,
    )
    db.add(debit_entry)
    db.add(credit_entry)
    db.commit()

    return {
        "status": "success",
        "swapped_from": f"{quote.from_amount} {quote.from_asset}",
        "received_to": f"{quote.estimated_received} {quote.to_asset}",
        "execution_time": datetime.utcnow().isoformat(),
    }