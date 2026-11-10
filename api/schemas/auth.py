from pydantic import BaseModel


class SIWELogin(BaseModel):
    message: str
    signature: str
    wallet_address: str = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    status: str
    role: str = "USER"
    email: str = None
    wallet_address: str = None