-- Indexes for: drep_delegators (unique constraint defined inline with table)
-- Depends on: 02_tables/05_drep_delegators.sql

-- Unique index already created in 05_drep_delegators.sql:
-- CREATE UNIQUE INDEX uq_drep_delegators_drep_stake_epoch ON public.drep_delegators (drep_id, stake_address, epoch_no);
