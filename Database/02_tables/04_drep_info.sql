-- Table: drep_info (Thông tin chi tiết DRep + stake)
-- Phụ thuộc: 01_extensions/01_enable_uuid_extension.sql, 02_tables/03_drep_list.sql

CREATE TABLE IF NOT EXISTS public.drep_info (
    drep_id               UUID PRIMARY KEY REFERENCES public.drep_list(drep_id),
    amount                NUMERIC,
    active_epoch          INTEGER,
    given_name            TEXT,
    content_url           TEXT,
    https_uris            JSONB DEFAULT '[]',
    url                   TEXT,
    metadata_fetched_at   TIMESTAMP WITH TIME ZONE,
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);