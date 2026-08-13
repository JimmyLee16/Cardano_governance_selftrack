-- Table: proposals (core - stores the on-chain proposals list)
-- Depends on: 01_extensions/01_enable_uuid_extension.sql

CREATE TABLE IF NOT EXISTS public.proposals (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    proposal_id                 VARCHAR(255) NOT NULL UNIQUE,
    title                       TEXT NOT NULL,
    abstract                    TEXT,
    first_reference_uri         TEXT,
    author_name                 TEXT,
    proposal_index              VARCHAR(50),
    proposal_tx_hash            VARCHAR(255),
    proposed_epoch              INTEGER,
    expiration                  VARCHAR(50),
    proposal_type               VARCHAR(100),
    epoch_no                    INTEGER,
    status                      VARCHAR(50) DEFAULT 'active',
    description                 TEXT,
    budget_requested            NUMERIC,
    voting_start_date           DATE,
    voting_end_date             DATE,
    implementation_start_date   DATE,
    implementation_end_date     DATE,
    documentation_urls          TEXT,
    discussion_urls             TEXT,
    data_fetched_at             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at                  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at                  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    activities_table_created    BOOLEAN DEFAULT FALSE,
    activities_table_name       VARCHAR(100),
    abstract_summary            TEXT,
    slug                        VARCHAR(255)
);

-- Unique index on slug (for friendly URLs)
CREATE UNIQUE INDEX IF NOT EXISTS idx_proposals_slug
    ON public.proposals (slug) WHERE slug IS NOT NULL;
