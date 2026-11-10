from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models.wallet import Wallet

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get("/wallets")
def get_wallets(user_id: str = Query(None), user=Depends(get_current_user), db: Session = Depends(get_db)):
    uid = user_id or user.id
    if uid != user.id and user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="forbidden")
    wallets = db.query(Wallet).filter(Wallet.user_id == uid).all()
    return [
        {
            "id": w.id,
            "type": w.type,
            "asset": w.asset,
            "available": str(w.available_balance),
            "reserved": str(w.reserved_balance),
            "total": str(w.available_balance + w.reserved_balance),
        }
        for w in wallets
    ]