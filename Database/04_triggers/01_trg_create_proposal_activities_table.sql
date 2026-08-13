-- Function & Trigger: Auto-create ga_* table for a new proposal
-- Runs BEFORE INSERT on proposals (sets activities_table_name + activities_table_created)
-- Depends on: 02_tables/01_proposals.sql

-- Function: Create ga_* table for a new proposal (based on proposal_id)
CREATE OR REPLACE FUNCTION public.create_proposal_activities_table()
RETURNS TRIGGER AS $$
DECLARE
    table_name TEXT;
    create_table_sql TEXT;
    index_sql TEXT;
    constraint_sql TEXT;
BEGIN
    table_name := 'ga_' || left(md5(NEW.proposal_id), 10) || '_' || left(regexp_replace(NEW.proposal_id, '[^a-zA-Z0-9]', '', 'g'), 40);

    create_table_sql := format(
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
    EXECUTE create_table_sql;

    BEGIN
        constraint_sql := format(
            'ALTER TABLE %I ADD CONSTRAINT uk_%s_voter_block_time UNIQUE (voter_id, block_time)',
            table_name, left(md5(NEW.proposal_id), 8)
        );
        EXECUTE constraint_sql;
    EXCEPTION
        WHEN duplicate_table THEN RAISE NOTICE 'Constraint already exists for table %', table_name;
        WHEN duplicate_object THEN RAISE NOTICE 'Constraint already exists for table %', table_name;
    END;

    index_sql := format(
        'CREATE INDEX IF NOT EXISTS idx_%s_voter_id ON %I(voter_id);
         CREATE INDEX IF NOT EXISTS idx_%s_voter_role ON %I(voter_role);
         CREATE INDEX IF NOT EXISTS idx_%s_block_time ON %I(block_time DESC);
         CREATE INDEX IF NOT EXISTS idx_%s_vote ON %I(vote);',
        left(md5(NEW.proposal_id), 8), table_name,
        left(md5(NEW.proposal_id), 8), table_name,
        left(md5(NEW.proposal_id), 8), table_name,
        left(md5(NEW.proposal_id), 8), table_name
    );
    EXECUTE index_sql;

    NEW.activities_table_name := table_name;
    NEW.activities_table_created := TRUE;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public';

-- Trigger: Runs before each INSERT INTO proposals
DROP TRIGGER IF EXISTS trg_create_proposal_activities_table ON public.proposals;
CREATE TRIGGER trg_create_proposal_activities_table
    BEFORE INSERT ON public.proposals
    FOR EACH ROW
    EXECUTE FUNCTION public.create_proposal_activities_table();
