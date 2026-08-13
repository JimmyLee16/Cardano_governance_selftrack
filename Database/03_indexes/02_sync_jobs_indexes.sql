-- Indexes for: sync_jobs
-- Depends on: 02_tables/06_sync_jobs.sql

CREATE INDEX IF NOT EXISTS idx_sync_jobs_type ON public.sync_jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_status ON public.sync_jobs(status);