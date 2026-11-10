from pydantic import BaseModel


class ApprovalAction(BaseModel):
    user_id: str
    action: str  # APPROVE, REJECT, SUSPEND


class BalanceAdjustment(BaseModel):
    user_id: str
    wallet_type: str
    asset: str
    amount: float
    reason: str
    idempotency_key: str