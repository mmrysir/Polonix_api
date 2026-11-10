"""auth tables

Revision ID: 001_auth_tables
Revises:
Create Date: 2026-11-09
"""

from alembic import op

revision = "001_auth_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY,
        email VARCHAR(255) UNIQUE,
        password_hash VARCHAR(255),
        wallet_address VARCHAR(255) UNIQUE,
        role VARCHAR(20) NOT NULL DEFAULT 'USER',
        status VARCHAR(20) NOT NULL DEFAULT 'PENDING_APPROVAL',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        type VARCHAR(20) NOT NULL,
        asset VARCHAR(20) NOT NULL,
        available_balance NUMERIC(36, 18) NOT NULL DEFAULT 0 CHECK (available_balance >= 0),
        reserved_balance NUMERIC(36, 18) NOT NULL DEFAULT 0 CHECK (reserved_balance >= 0),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_user_wallet_asset UNIQUE (user_id, type, asset)
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS ledger_entries (
        id VARCHAR(36) PRIMARY KEY,
        transaction_id VARCHAR(36) NOT NULL,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id),
        wallet_id VARCHAR(36) NOT NULL REFERENCES wallets(id),
        asset VARCHAR(20) NOT NULL,
        amount NUMERIC(36, 18) NOT NULL,
        type VARCHAR(30) NOT NULL,
        idempotency_key VARCHAR(255) NOT NULL UNIQUE,
        reference_id VARCHAR(255),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id VARCHAR(36) PRIMARY KEY,
        actor_id VARCHAR(36) NOT NULL,
        action VARCHAR(255) NOT NULL,
        target_id VARCHAR(36),
        details TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS audit_logs;")
    op.execute("DROP TABLE IF EXISTS ledger_entries;")
    op.execute("DROP TABLE IF EXISTS wallets;")
    op.execute("DROP TABLE IF EXISTS users;")