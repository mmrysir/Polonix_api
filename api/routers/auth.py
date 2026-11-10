import time
import uuid
from datetime import datetime, timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, Depends, HTTPException, Query
from jose import jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from decimal import Decimal

from ..models.user import User, AccountStatus
from ..models.wallet import Wallet
from ..schemas.auth import SIWELogin, TokenResponse


class EmailLogin(BaseModel):
    email: str
    password: str


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# In-memory nonce store: address -> (nonce, expiry). Use Redis in production.
_nonce_store: dict[str, tuple[str, float]] = {}


def _create_token(user: User) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user.id, "role": user.role, "status": user.status, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@router.get("/nonce")
def get_nonce(address: str = Query(...)):
    nonce = str(uuid.uuid4()).replace("-", "")
    _nonce_store[address.lower()] = (nonce, time.time() + 300)
    return {"nonce": nonce, "address": address}


@router.post("/siwe")
def siwe_login(body: SIWELogin, db: Session = Depends(get_db)):
    address = getattr(body, "wallet_address", None)
    if not address:
        for token in body.message.split():
            if token.startswith("0x") and len(token) >= 40:
                address = token.strip().rstrip(",")
                break
    if not address:
        raise HTTPException(status_code=400, detail="address_not_found")

    # Verify nonce (one-time use)
    entry = _nonce_store.get(address.lower())
    if not entry or entry[0] not in body.message:
        raise HTTPException(status_code=400, detail="invalid_or_missing_nonce")
    if time.time() > entry[1]:
        raise HTTPException(status_code=400, detail="nonce_expired")
    del _nonce_store[address.lower()]

    # Verify Ethereum signature (EIP-191 personal_sign)
    try:
        message = encode_defunct(text=body.message)
        recovered = Account.recover_message(message, signature=body.signature)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_signature")
    if recovered.lower() != address.lower():
        raise HTTPException(status_code=400, detail="signature_mismatch")

    user = db.query(User).filter(User.wallet_address == address).first()
    if not user:
        admin_list = [w.strip().lower() for w in settings.admin_wallets.split(",") if w.strip()]
        is_admin = address.lower() in admin_list
        user = User(
            wallet_address=address,
            email=f"{address}@wallet.local",
            role="ADMIN" if is_admin else "USER",
            status=AccountStatus.APPROVED if is_admin else AccountStatus.PENDING_APPROVAL,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        # Seed demo wallets with balances for testing
        if not is_admin:
            for wtype in ("FUNDING", "SPOT", "FUTURES", "OPTIONS"):
                db.add(Wallet(user_id=user.id, type=wtype, asset="USDT", available_balance=Decimal("10000"), reserved_balance=Decimal("0")))
            db.commit()

    return {
        "access_token": _create_token(user),
        "token_type": "bearer",
        "user_id": user.id,
        "status": user.status,
        "role": user.role,
        "email": user.email,
        "wallet_address": user.wallet_address,
    }


@router.post("/login")
def email_login(body: EmailLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        user = User(email=body.email, status=AccountStatus.PENDING_APPROVAL)
        db.add(user)
        db.commit()
        db.refresh(user)
        for wtype in ("FUNDING", "SPOT", "FUTURES", "OPTIONS"):
            db.add(Wallet(user_id=user.id, type=wtype, asset="USDT", available_balance=Decimal("10000"), reserved_balance=Decimal("0")))
        db.commit()
    return {
        "access_token": _create_token(user),
        "token_type": "bearer",
        "user_id": user.id,
        "status": user.status,
        "role": user.role,
        "email": user.email,
        "wallet_address": user.wallet_address,
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "wallet_address": user.wallet_address,
            "role": user.role, "status": user.status}