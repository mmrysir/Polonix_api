import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models.user import User, AccountStatus
from ..models.wallet import Wallet
from ..models.ledger import LedgerEntry, LedgerEntryType
from ..models.support import AuditLog
from ..schemas.admin import ApprovalAction, BalanceAdjustment

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users")
def list_users(admin=Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "wallet_address": u.wallet_address,
            "role": u.role,
            "status": u.status,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users/approval")
def approval_action(body: ApprovalAction, admin=Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    action = body.action.upper()
    if action == "APPROVE":
        user.status = AccountStatus.APPROVED
    elif action == "REJECT":
        user.status = AccountStatus.REJECTED
    elif action == "SUSPEND":
        user.status = AccountStatus.SUSPENDED
    else:
        raise HTTPException(status_code=400, detail="invalid_action")
    db.add(AuditLog(actor_id=admin.id, action=f"SET_STATUS_{action}", target_id=user.id, details=body.action))
    db.commit()
    db.refresh(user)
    return {"id": user.id, "status": user.status}


@router.post("/ledger/adjust-balance")
def adjust_balance(body: BalanceAdjustment, admin=Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    wallet = db.query(Wallet).filter_by(user_id=body.user_id, type=body.wallet_type, asset=body.asset).first()
    if not wallet:
        wallet = Wallet(user_id=body.user_id, type=body.wallet_type, asset=body.asset)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    txn_id = str(uuid.uuid4())
    wallet.available_balance = wallet.available_balance + Decimal(str(body.amount))
    entry = LedgerEntry(
        transaction_id=txn_id,
        user_id=body.user_id,
        wallet_id=wallet.id,
        asset=body.asset,
        amount=Decimal(str(body.amount)),
        type=LedgerEntryType.BALANCE_ADJUSTMENT,
        idempotency_key=body.idempotency_key,
        reference_id=body.reason,
    )
    db.add(entry)
    db.add(AuditLog(actor_id=admin.id, action="BALANCE_ADJUSTMENT", target_id=body.user_id, details=body.reason))
    db.commit()
    return {"transaction_id": txn_id, "new_balance": str(wallet.available_balance)}