from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..models.ledger import LedgerEntry
from ..models.wallet import Wallet


class LedgerService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_wallet(self, user_id: str, wallet_type: str, asset: str) -> Wallet:
        w = self.db.query(Wallet).filter_by(user_id=user_id, type=wallet_type, asset=asset).first()
        if not w:
            w = Wallet(user_id=user_id, type=wallet_type, asset=asset)
            self.db.add(w)
            self.db.commit()
            self.db.refresh(w)
        return w

    def get_wallet(self, user_id: str, wallet_type: str, asset: str) -> Optional[Wallet]:
        return self.db.query(Wallet).filter_by(user_id=user_id, type=wallet_type, asset=asset).first()

    def record_entry(self, *, transaction_id: str, user_id: str, wallet_id: str, asset: str,
                     amount: Decimal, entry_type: str, idempotency_key: str, reference_id: str = None) -> Optional[LedgerEntry]:
        existing = self.db.query(LedgerEntry).filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing
        entry = LedgerEntry(
            transaction_id=transaction_id,
            user_id=user_id,
            wallet_id=wallet_id,
            asset=asset,
            amount=amount,
            type=entry_type,
            idempotency_key=idempotency_key,
            reference_id=reference_id,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def transfer(self, user_id: str, from_type: str, to_type: str, asset: str, amount: Decimal, idempotency_key: str):
        existing = self.db.query(LedgerEntry).filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return {"idempotent": True}
        from_w = self.get_wallet(user_id, from_type, asset)
        to_w = self.get_wallet(user_id, to_type, asset)
        if not from_w or not to_w:
            raise ValueError("wallet_not_found")
        if from_w.available_balance < amount:
            raise ValueError("insufficient_balance")
        import uuid
        txn_id = str(uuid.uuid4())
        from_w.available_balance = from_w.available_balance - amount
        to_w.available_balance = to_w.available_balance + amount
        self.record_entry(transaction_id=txn_id, user_id=user_id, wallet_id=from_w.id, asset=asset,
                          amount=-amount, entry_type="INTERNAL_TRANSFER", idempotency_key=idempotency_key)
        self.record_entry(transaction_id=txn_id, user_id=user_id, wallet_id=to_w.id, asset=asset,
                          amount=amount, entry_type="INTERNAL_TRANSFER", idempotency_key=f"{idempotency_key}:credit")
        self.db.commit()
        return {"idempotent": False, "transaction_id": txn_id}