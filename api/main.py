import asyncio

import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .models import *  # noqa: register models
from .routers import auth, admin, portfolio, trading, transfers, spot, futures, options, convert

Base.metadata.create_all(bind=engine)


async def _settle_worker():
    from .database import SessionLocal
    from .models.trading import OptionsContract
    from .models.wallet import Wallet
    from .models.ledger import LedgerEntry, LedgerEntryType
    from decimal import Decimal
    from datetime import datetime
    import uuid as _uuid

    prices = {"BTC": "91450", "ETH": "3340", "SOL": "214"}
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                for asset, fallback in prices.items():
                    try:
                        r = await client.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT")
                        prices[asset] = r.json()["price"]
                    except Exception:
                        pass
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                expired = db.query(OptionsContract).filter(
                    OptionsContract.status == "ACTIVE",
                    OptionsContract.expires_at <= now,
                ).all()
                for c in expired:
                    mp = Decimal(str(prices.get(c.asset, "0")))
                    is_win = (c.direction == "CALL" and mp > c.entry_price) or (c.direction == "PUT" and mp < c.entry_price)
                    c.expiry_price = mp
                    wallet = db.query(Wallet).filter_by(user_id=c.user_id, type="OPTIONS", asset="USDT").first()
                    total_cost = c.stake_amount + c.fee_amount
                    if wallet:
                        wallet.reserved_balance = (wallet.reserved_balance or 0) - total_cost
                    if is_win:
                        c.status = "WON"
                        payout = c.stake_amount * (Decimal("1") + c.target_payout_rate)
                        if wallet:
                            wallet.available_balance = (wallet.available_balance or 0) + payout
                        c.payout_amount = payout
                    else:
                        c.status = "LOST"
                        c.payout_amount = Decimal("0")
                    ledger = LedgerEntry(
                        id=str(_uuid.uuid4()),
                        transaction_id=str(_uuid.uuid4()),
                        user_id=c.user_id,
                        wallet_id=wallet.id if wallet else None,
                        asset="USDT",
                        amount=c.payout_amount if is_win else Decimal("0"),
                        type=LedgerEntryType.OPTIONS_PAYOUT,
                        idempotency_key=f"OPTIONS-SETTLE-{c.id}",
                        reference_id=c.id,
                    )
                    db.add(ledger)
                if expired:
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            print("settle worker error:", e)
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_settle_worker())
    yield
    task.cancel()


app = FastAPI(title="Polonix API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(portfolio.router)
app.include_router(trading.router)
app.include_router(transfers.router)
app.include_router(spot.router, prefix="/api/v1")
app.include_router(futures.router, prefix="/api/v1")
app.include_router(options.router, prefix="/api/v1")
app.include_router(convert.router, prefix="/api/v1")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "polonix-api"}