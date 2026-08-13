-- Table: sync_jobs (tracks sync job run history)
-- Depends on: 01_extensions/01_enable_uuid_extension.sql

CREATE TABLE IF NOT EXISTS public.sync_jobs (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type         VARCHAR(50) NOT NULL DEFAULT 'unknown',
    status           VARCHAR(50) NOT NULL DEFAULT 'pending',
    config           JSONB DEFAULT '{}',
    started_at       TIMESTAMP WITH TIME ZONE,
    completed_at     TIMESTAMP WITH TIME ZONE,
    error_message    TEXT
);