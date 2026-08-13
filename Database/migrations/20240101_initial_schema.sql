-- 📄 new_repo\Database\migrations\20240101_initial_schema.sql
-- Initial schema migration for Cardano Governance

-- ============================================================
-- Enable UUID extension
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Core tables
-- ============================================================

-- 1. proposals
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

-- Indexes
CREATE INDEX idx_proposals_status ON public.proposals(status);
CREATE INDEX idx_proposals_proposed_epoch ON public.proposals(proposed_epoch DESC);
CREATE INDEX idx_proposals_epoch_no ON public.proposals(epoch_no DESC);

-- 2. proposal_voting_summary
CREATE TABLE IF NOT EXISTS public.proposal_voting_summary (
    proposal_id          UUID PRIMARY KEY REFERENCES public.proposals(proposal_id),
    epoch_no             INTEGER NOT NULL,
    drep_yes_votes_cast              BIGINT DEFAULT 0,
    drep_active_yes_vote_power       NUMERIC DEFAULT 0,
    drep_yes_vote_power              NUMERIC DEFAULT 0,
    drep_yes_pct                     NUMERIC DEFAULT 0,
    drep_no_votes_cast               BIGINT DEFAULT 0,
    drep_active_no_vote_power        NUMERIC DEFAULT 0,
    drep_no_vote_power               NUMERIC DEFAULT 0,
    drep_no_pct                      NUMERIC DEFAULT 0,
    drep_abstain_votes_cast          BIGINT DEFAULT 0,
    drep_active_abstain_vote_power   NUMERIC DEFAULT 0,
    drep_always_abstain_vote_power   NUMERIC DEFAULT 0,
    drep_always_no_confidence_vote_power NUMERIC DEFAULT 0,
    pool_yes_votes_cast              BIGINT DEFAULT 0,
    pool_active_yes_vote_power       NUMERIC DEFAULT 0,
    pool_yes_vote_power              NUMERIC DEFAULT 0,
    pool_yes_pct                     NUMERIC DEFAULT 0,
    pool_no_votes_cast               BIGINT DEFAULT 0,
    pool_active_no_vote_power        NUMERIC DEFAULT 0,
    pool_no_vote_power               NUMERIC DEFAULT 0,
    pool_no_pct                      NUMERIC DEFAULT 0,
    pool_abstain_votes_cast          BIGINT DEFAULT 0,
    pool_active_abstain_vote_power   NUMERIC DEFAULT 0,
    committee_yes_votes_cast         BIGINT DEFAULT 0,
    committee_yes_pct                NUMERIC DEFAULT 0,
    committee_no_votes_cast          BIGINT DEFAULT 0,
    committee_no_pct                 NUMERIC DEFAULT 0,
    committee_abstain_votes_cast     BIGINT DEFAULT 0,
    data_fetched_at                  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at                       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at                       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- Triggers & Functions
-- ============================================================

-- Function: Create ga_* table for a new proposal
CREATE OR REPLACE FUNCTION public.trg_create_proposal_activities_table()
RETURNS TRIGGER AS $$
DECLARE
    md5_prefix TEXT;
    sanitized_title TEXT;
    table_name TEXT;
BEGIN
    md5_prefix := encode(digest(NEW.title, 'md5'), 'hex')[:10];
    sanitized_title := lower(regexp_replace(NEW.title, '[^a-z0-9]', '', 'g'));
    if length(sanitized_title) > 30 then
        sanitized_title := left(sanitized_title, 30);
    end if;

    table_name := 'ga_' || md5_prefix || '_' || sanitized_title;

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            block_time TIMESTAMP WITH TIME ZONE NULL,
            voter_role VARCHAR(50) NULL,
            voter_id VARCHAR(255) NULL,
            vote VARCHAR(50) NULL,
            meta_url TEXT NULL,
            comment TEXT NULL,
            processed_at TIMESTAMP WITH TIME ZONE NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )', table_name
    );

    EXECUTE format(
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_%I_voter_block_time ON %I (voter_id, block_time)',
        table_name, table_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%I_voter ON %I (voter_id)',
        table_name, table_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%I_role ON %I (voter_role)',
        table_name, table_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%I_block_time ON %I (block_time DESC)',
        table_name, table_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%I_vote ON %I (vote)',
        table_name, table_name
    );

    UPDATE public.proposals
    SET activities_table_name = table_name
    WHERE proposal_id = NEW.proposal_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: Runs after each INSERT INTO proposals
CREATE TRIGGER trg_create_proposal_activities_table
    AFTER INSERT ON public.proposals
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_create_proposal_activities_table();

-- Function: Create an entry in proposal_voting_summary
CREATE OR REPLACE FUNCTION public.trg_create_proposal_summary_entry()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.proposal_voting_summary (
        proposal_id, epoch_no,
        drep_yes_votes_cast, drep_no_votes_cast,
        drep_active_yes_vote_power, drep_active_no_vote_power,
        pool_yes_votes_cast, pool_no_votes_cast,
        committee_yes_votes_cast, committee_no_votes_cast,
        data_fetched_at
    )
    SELECT
        NEW.proposal_id,
        NEW.epoch_no,
        0, 0, 0, 0,
        0, 0,
        0, 0,
        NOW()
    WHERE NOT EXISTS (
        SELECT 1 FROM public.proposal_voting_summary
        WHERE proposal_id = NEW.proposal_id
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: Runs after each INSERT INTO proposals
CREATE TRIGGER trg_create_proposal_summary_entry
    AFTER INSERT ON public.proposals
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_create_proposal_summary_entry();