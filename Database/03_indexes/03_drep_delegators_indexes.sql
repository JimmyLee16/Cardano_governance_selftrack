-- Indexes for: drep_delegators (unique constraint defined inline with table)
-- Phụ thuộc: 02_tables/05_drep_delegators.sql

-- Unique index already created in 05_drep_delegators.sql:
-- CREATE UNIQUE INDEX idx_drep_delegators_unique ON public.drep_delegators (drep_id, stake_address, epoch_no);

-- Additional indexes if needed:
-- CREATE INDEX IF NOT EXISTS idx_drep_delegators_drep_id ON public.drep_delegators(drep_id);
-- CREATE INDEX IF NOT EXISTS idx_drep_delegators_epoch_no ON public.drep_delegators(epoch_no);