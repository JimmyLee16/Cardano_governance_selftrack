-- Table: drep_list (DRep registry - danh sách DRep)
-- Phụ thuộc: 01_extensions/01_enable_uuid_extension.sql

CREATE TABLE IF NOT EXISTS public.drep_list (
    drep_id               UUID PRIMARY KEY,
    given_name            TEXT,
    content_url           TEXT,
    https_uris            JSONB DEFAULT '[]',
    amount                NUMERIC,
    active_epoch          INTEGER,
    last_active_epoch     INTEGER,
    url                   TEXT,
    script_hash           TEXT,
    has_script            BOOLEAN DEFAULT FALSE
);