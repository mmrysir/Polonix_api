from pydantic import BaseModel


class InternalTransfer(BaseModel):
    from_wallet: str
    to_wallet: str
    asset: str
    amount: float
    idempotency_key: str


class WithdrawalRequest(BaseModel):
    asset: str
    network: str
    destination_address: str
    amount: float
    idempotency_key: str