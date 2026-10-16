-- Finkow — Supabase schema (Phase 1: virtual-money sandbox)
-- Apply in the Supabase SQL editor. RLS policies are intentionally minimal for
-- the scaffold; harden before any real-money phase.

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email text unique,
    created_at timestamptz not null default now()
);

create table if not exists sandbox_accounts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users (id) on delete cascade,
    -- exact money: numeric, never float
    cash numeric(20, 2) not null default 100000.00,
    initial_cash numeric(20, 2) not null default 100000.00,
    created_at timestamptz not null default now()
);

create table if not exists positions (
    account_id uuid not null references sandbox_accounts (id) on delete cascade,
    symbol text not null,
    qty numeric(28, 8) not null check (qty > 0),
    avg_cost numeric(20, 8) not null check (avg_cost >= 0),
    updated_at timestamptz not null default now(),
    primary key (account_id, symbol)
);

create table if not exists transactions (
    id uuid primary key default gen_random_uuid(),
    account_id uuid not null references sandbox_accounts (id) on delete cascade,
    symbol text not null,
    side text not null check (side in ('buy', 'sell')),
    qty numeric(28, 8) not null check (qty > 0),
    price numeric(20, 8) not null check (price >= 0),
    cash_delta numeric(20, 2) not null,
    realized_pnl numeric(20, 2),
    created_at timestamptz not null default now()
);
create index if not exists transactions_account_idx on transactions (account_id, created_at desc);

create table if not exists portfolio_snapshots (
    id uuid primary key default gen_random_uuid(),
    account_id uuid not null references sandbox_accounts (id) on delete cascade,
    total_value numeric(20, 2) not null,
    cash numeric(20, 2) not null,
    created_at timestamptz not null default now()
);
create index if not exists snapshots_account_idx on portfolio_snapshots (account_id, created_at desc);
