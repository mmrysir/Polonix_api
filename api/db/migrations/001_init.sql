-- Polonix Web3 Trading Platform - PostgreSQL Schema
-- (provided in master spec)

CREATE TYPE user_role AS ENUM ('USER', 'SUPPORT', 'OPERATOR', 'ADMIN');
CREATE TYPE account_status AS ENUM ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'SUSPENDED');
CREATE TYPE wallet_type AS ENUM ('FUNDING', 'SPOT', 'FUTURES', 'OPTIONS');
CREATE TYPE ledger_entry_type AS ENUM (
    'DEPOSIT', 'WITHDRAWAL', 'INTERNAL_TRANSFER',
    'CONVERSION_DEBIT', 'CONVERSION_CREDIT',
    'SPOT_TRADE', 'FUTURES_MARGIN', 'FUTURES_PNL',
    'OPTIONS_STAKE', 'OPTIONS_PAYOUT',
    'PLATFORM_FEE', 'BALANCE_ADJUSTMENT'
);
CREATE TYPE options_duration AS ENUM ('30s', '60s', '120s', '5m', '15m');
CREATE TYPE order_side AS ENUM ('BUY', 'SELL', 'LONG', 'SHORT');
CREATE TYPE order_type AS ENUM ('MARKET', 'LIMIT');
CREATE TYPE order_status AS ENUM ('NEW', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED', 'REJECTED');
CREATE TYPE contract_status AS ENUM ('ACTIVE', 'WON', 'LOST', 'EXPIRED', 'SETTLED');

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    wallet_address VARCHAR(255) UNIQUE,
    role user_role NOT NULL DEFAULT 'USER',
    status account_status NOT NULL DEFAULT 'PENDING_APPROVAL',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wallets (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type wallet_type NOT NULL,
    asset VARCHAR(20) NOT NULL,
    available_balance NUMERIC(36, 18) NOT NULL DEFAULT 0 CHECK (available_balance >= 0),
    reserved_balance NUMERIC(36, 18) NOT NULL DEFAULT 0 CHECK (reserved_balance >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_wallet_asset UNIQUE (user_id, type, asset)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id VARCHAR(36) PRIMARY KEY,
    transaction_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    wallet_id VARCHAR(36) NOT NULL REFERENCES wallets(id),
    asset VARCHAR(20) NOT NULL,
    amount NUMERIC(36, 18) NOT NULL,
    type ledger_entry_type NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL UNIQUE,
    reference_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    symbol VARCHAR(20) NOT NULL,
    wallet_type wallet_type NOT NULL,
    side order_side NOT NULL,
    type order_type NOT NULL,
    price NUMERIC(36, 18),
    quantity NUMERIC(36, 18) NOT NULL,
    filled_quantity NUMERIC(36, 18) DEFAULT 0,
    status order_status NOT NULL DEFAULT 'NEW',
    fee_paid NUMERIC(36, 18) DEFAULT 0,
    idempotency_key VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS futures_positions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    symbol VARCHAR(20) NOT NULL,
    side order_side NOT NULL,
    leverage INT NOT NULL CHECK (leverage >= 1 AND leverage <= 200),
    margin_usdt NUMERIC(36, 18) NOT NULL CHECK (margin_usdt > 0),
    notional_position_usdt NUMERIC(36, 18) NOT NULL,
    entry_price NUMERIC(36, 18) NOT NULL,
    liquidation_price NUMERIC(36, 18) NOT NULL,
    unrealized_pnl NUMERIC(36, 18) DEFAULT 0,
    is_open BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS options_contracts (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    asset VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    duration options_duration NOT NULL,
    stake_amount NUMERIC(36, 18) NOT NULL CHECK (stake_amount > 0),
    fee_amount NUMERIC(36, 18) NOT NULL,
    entry_price NUMERIC(36, 18) NOT NULL,
    expiry_price NUMERIC(36, 18),
    target_payout_rate NUMERIC(5, 4) NOT NULL,
    payout_amount NUMERIC(36, 18) DEFAULT 0,
    status contract_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS conversion_quotes (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    from_asset VARCHAR(20) NOT NULL,
    to_asset VARCHAR(20) NOT NULL,
    from_amount NUMERIC(36, 18) NOT NULL,
    exchange_rate NUMERIC(36, 18) NOT NULL,
    estimated_received NUMERIC(36, 18) NOT NULL,
    platform_fee_rate NUMERIC(5, 4) DEFAULT 0.0095,
    execution_target_time VARCHAR(50) NOT NULL,
    is_executed BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    subject VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'OPEN',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_messages (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    sender_id VARCHAR(36) NOT NULL REFERENCES users(id),
    message TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    actor_id VARCHAR(36) NOT NULL,
    action VARCHAR(255) NOT NULL,
    target_id VARCHAR(36),
    details TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_wallets_user ON wallets(user_id, type);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger_entries(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_idempotency ON ledger_entries(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_futures_user ON futures_positions(user_id, is_open);
CREATE INDEX IF NOT EXISTS idx_options_user ON options_contracts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_quotes_expires ON conversion_quotes(expires_at, is_executed);