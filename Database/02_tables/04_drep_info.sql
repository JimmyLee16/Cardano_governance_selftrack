-- Table: drep_info (Thông tin chi tiết DRep + stake)
-- Phụ thuộc: 01_extensions/01_enable_uuid_extension.sql, 02_tables/03_drep_list.sql

CREATE TABLE IF NOT EXISTS public.drep_info (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drep_id               VARCHAR(255) NOT NULL UNIQUE,
    amount                NUMERIC,
    active_epoch          INTEGER,
    last_active_epoch     INTEGER,
    url                   TEXT,
    payment_address       VARCHAR(255),
    given_name            TEXT,
    content_url           TEXT,
    https_uris            TEXT,
    metadata_fetched_at   TIMESTAMP WITH TIME ZONE,
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drep_info_active_epoch
    ON public.drep_info (active_epoch);
CREATE INDEX IF NOT EXISTS idx_drep_info_amount
    ON public.drep_info (amount);
