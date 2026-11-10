from pydantic import BaseModel


class FuturesOrder(BaseModel):
    symbol: str
    side: str  # LONG or SHORT
    leverage: int
    margin_usdt: float
    idempotency_key: str


class OptionsContractRequest(BaseModel):
    asset: str
    direction: str  # CALL or PUT
    duration: str  # 30s, 60s, 120s, 5m, 15m
    stake_amount: float
    idempotency_key: str


class ConvertQuoteRequest(BaseModel):
    from_asset: str
    to_asset: str
    from_amount: float
    user_id: str