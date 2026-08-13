-- Table: drep_delegators (current delegation snapshot per epoch)
-- Depends on: 01_extensions/01_enable_uuid_extension.sql, 02_tables/03_drep_list.sql

CREATE TABLE IF NOT EXISTS public.drep_delegators (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drep_id               VARCHAR(255) NOT NULL,
    stake_address         VARCHAR(255) NOT NULL,
    stake_address_hex     VARCHAR(255) NOT NULL,
    script_hash           VARCHAR(255),
    epoch_no              INTEGER NOT NULL,
    amount_lovelace       BIGINT NOT NULL,
    amount_ada            NUMERIC,
    is_current            BOOLEAN DEFAULT TRUE,
    delegation_type       VARCHAR(50) DEFAULT 'regular',
    first_seen_epoch      INTEGER,
    last_seen_epoch       INTEGER,
    delegation_count      INTEGER DEFAULT 1,
    is_whale              BOOLEAN DEFAULT FALSE,
    is_exchange           BOOLEAN DEFAULT FALSE,
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Unique constraint: 1 delegation per (drep_id, stake_address, epoch_no)
CREATE UNIQUE INDEX IF NOT EXISTS uq_drep_delegators_drep_stake_epoch
    ON public.drep_delegators (drep_id, stake_address, epoch_no);
