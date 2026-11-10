from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from decimal import Decimal

from .models.user import User
from .models.wallet import Wallet

bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer), db: Session = Depends(get_db)):
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    return user


def require_approved(user: User = Depends(get_current_user)):
    if user.status != "APPROVED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account_not_approved")
    return user


# Alias used by spec
require_approved_user = require_approved


def require_admin(user: User = Depends(get_current_user)):
    if user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return user


def ensure_wallet(db, user_id: str, wtype: str, asset: str = "USDT", seed: float = 10000.0):
    w = db.query(Wallet).filter_by(user_id=user_id, type=wtype, asset=asset).first()
    if not w:
        w = Wallet(user_id=user_id, type=wtype, asset=asset, available_balance=Decimal(str(seed)), reserved_balance=Decimal("0"))
        db.add(w)
        db.commit()
        db.refresh(w)
    return w