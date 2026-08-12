-- Table: drep_list (DRep registry - danh sách DRep)
-- Phụ thuộc: 01_extensions/01_enable_uuid_extension.sql

CREATE TABLE IF NOT EXISTS public.drep_list (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drep_id     VARCHAR(255) NOT NULL UNIQUE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
