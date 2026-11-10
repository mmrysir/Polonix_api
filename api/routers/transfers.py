from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_approved
from ..models.user import User
from ..schemas.wallet import InternalTransfer
from ..services.ledger_service import LedgerService

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


@router.post("/internal")
def internal_transfer(body: InternalTransfer, user: User = Depends(require_approved), db: Session = Depends(get_db)):
    svc = LedgerService(db)
    try:
        result = svc.transfer(user.id, body.from_wallet.upper(), body.to_wallet.upper(), body.asset.upper(),
                              __import__("decimal").Decimal(str(body.amount)), body.idempotency_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result