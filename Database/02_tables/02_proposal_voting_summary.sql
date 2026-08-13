-- Table: proposal_voting_summary (vote aggregation per proposal)
-- Depends on: 01_extensions/01_enable_uuid_extension.sql, 02_tables/01_proposals.sql

CREATE TABLE IF NOT EXISTS public.proposal_voting_summary (
    id                                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    proposal_id                                 VARCHAR(255),
    proposal_type                               TEXT,
    epoch_no                                    INTEGER,
    -- DRep votes
    drep_yes_votes_cast                         BIGINT DEFAULT 0,
    drep_active_yes_vote_power                  TEXT,
    drep_yes_vote_power                         TEXT,
    drep_yes_pct                                TEXT,
    drep_no_votes_cast                          BIGINT DEFAULT 0,
    drep_active_no_vote_power                   TEXT,
    drep_no_vote_power                          TEXT,
    drep_no_pct                                 TEXT,
    drep_abstain_votes_cast                     BIGINT DEFAULT 0,
    drep_active_abstain_vote_power              TEXT,
    drep_abstain_vote_power                     TEXT,
    drep_always_abstain_vote_power              TEXT,
    drep_always_no_confidence_vote_power        TEXT,
    -- Pool votes
    pool_yes_votes_cast                         BIGINT DEFAULT 0,
    pool_active_yes_vote_power                  TEXT,
    pool_yes_vote_power                         TEXT,
    pool_yes_pct                                TEXT,
    pool_no_votes_cast                          BIGINT DEFAULT 0,
    pool_active_no_vote_power                   TEXT,
    pool_no_vote_power                          TEXT,
    pool_no_pct                                 TEXT,
    pool_abstain_votes_cast                     BIGINT DEFAULT 0,
    pool_active_abstain_vote_power              TEXT,
    pool_passive_always_abstain_votes_assigned  TEXT,
    pool_passive_always_abstain_vote_power      TEXT,
    pool_passive_always_no_confidence_votes_assigned TEXT,
    pool_passive_always_no_confidence_vote_power TEXT,
    -- Committee votes
    committee_yes_votes_cast                    BIGINT DEFAULT 0,
    committee_yes_pct                           TEXT,
    committee_no_votes_cast                     BIGINT DEFAULT 0,
    committee_no_pct                            TEXT,
    committee_abstain_votes_cast                BIGINT DEFAULT 0,
    -- Timestamps
    data_fetched_at                             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at                                  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at                                  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Unique on proposal_id (one summary row per proposal)
CREATE UNIQUE INDEX IF NOT EXISTS pvs_proposal_id_key
    ON public.proposal_voting_summary (proposal_id) WHERE proposal_id IS NOT NULL;
