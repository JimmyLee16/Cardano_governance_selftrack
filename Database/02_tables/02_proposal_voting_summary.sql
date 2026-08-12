-- Table: proposal_voting_summary (tổng hợp vote theo proposal)
-- Phụ thuộc: 01_extensions/01_enable_uuid_extension.sql, 02_tables/01_proposals.sql

CREATE TABLE IF NOT EXISTS public.proposal_voting_summary (
    proposal_id          UUID PRIMARY KEY REFERENCES public.proposals(proposal_id),
    epoch_no             INTEGER NOT NULL,
    -- DRep votes
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
    -- Pool votes
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
    -- Committee votes
    committee_yes_votes_cast         BIGINT DEFAULT 0,
    committee_yes_pct                NUMERIC DEFAULT 0,
    committee_no_votes_cast          BIGINT DEFAULT 0,
    committee_no_pct                 NUMERIC DEFAULT 0,
    committee_abstain_votes_cast     BIGINT DEFAULT 0,
    -- Timestamps
    data_fetched_at                  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at                       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at                       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);