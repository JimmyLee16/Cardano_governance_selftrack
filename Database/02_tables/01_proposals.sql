-- Table: proposals (cốt lõi - lưu danh sách proposals on-chain)
-- Phụ thuộc: 01_extensions/01_enable_uuid_extension.sql

CREATE TABLE IF NOT EXISTS public.proposals (
    proposal_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title                TEXT NOT NULL,
    status               VARCHAR(50) NOT NULL DEFAULT 'pending',
    proposed_epoch       INTEGER NOT NULL,
    expiration           TIMESTAMP WITH TIME ZONE,
    activities_table_name VARCHAR(100) NOT NULL,
    abstract             TEXT,
    author_name          TEXT,
    epoch_no             INTEGER,
    description          TEXT,
    budget_requested     NUMERIC,
    data_fetched_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);