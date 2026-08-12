-- Table: drep_delegators (Snapshot delegation hiện tại per epoch)
-- Phụ thuộc: 01_extensions/01_enable_uuid_extension.sql, 02_tables/03_drep_list.sql

CREATE TABLE IF NOT EXISTS public.drep_delegators (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drep_id               UUID NOT NULL REFERENCES public.drep_list(drep_id),
    stake_address         TEXT NOT NULL,
    stake_address_hex     BYTEA,
    script_hash           TEXT,
    amount_lovelace       BIGINT,
    epoch_no              INTEGER NOT NULL,
    timestamp             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    timestamp_epoch       INTEGER
);

-- Unique constraint: 1 delegation per (drep_id, stake_address, epoch_no)
CREATE UNIQUE INDEX IF NOT EXISTS idx_drep_delegators_unique
    ON public.drep_delegators (drep_id, stake_address, epoch_no);