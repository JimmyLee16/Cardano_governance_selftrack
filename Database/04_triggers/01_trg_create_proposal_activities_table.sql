-- Function & Trigger: Tự động tạo ga_* table cho proposal mới
-- Chạy AFTER INSERT trên proposals
-- Phụ thuộc: 02_tables/01_proposals.sql

-- Function: Tạo ga_* table cho proposal mới
CREATE OR REPLACE FUNCTION public.trg_create_proposal_activities_table()
RETURNS TRIGGER AS $$
DECLARE
    md5_prefix TEXT;
    sanitized_title TEXT;
    table_name TEXT;
BEGIN
    -- Lấy 10 ký tự đầu của md5(title) để tạo tên table ngắn
    md5_prefix := encode(digest(NEW.title, 'md5'), 'hex')[:10];
    -- Sanitize title: lowercase, remove special chars, truncate
    sanitized_title := lower(regexp_replace(NEW.title, '[^a-z0-9]', '', 'g'));
    if length(sanitized_title) > 30 then
        sanitized_title := left(sanitized_title, 30);
    end if;

    table_name := 'ga_' || md5_prefix || '_' || sanitized_title;

    -- Tạo table IF NOT EXISTS
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            block_time TIMESTAMP WITH TIME ZONE NULL,
            voter_role VARCHAR(50) NULL,
            voter_id VARCHAR(255) NULL,
            vote VARCHAR(50) NULL,
            meta_url TEXT NULL,
            comment TEXT NULL,
            processed_at TIMESTAMP WITH TIME ZONE NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )', table_name
    );

    -- Thêm indexes
    EXECUTE format(
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_%I_voter_block_time ON %I (voter_id, block_time)',
        table_name, table_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%I_voter ON %I (voter_id)',
        table_name, table_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%I_role ON %I (voter_role)',
        table_name, table_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%I_block_time ON %I (block_time DESC)',
        table_name, table_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_%I_vote ON %I (vote)',
        table_name, table_name
    );

    -- Lưu tên table xuống proposals
    UPDATE public.proposals
    SET activities_table_name = table_name
    WHERE proposal_id = NEW.proposal_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: Chạy sau mỗi INSERT INTO proposals
DROP TRIGGER IF EXISTS trg_create_proposal_activities_table ON public.proposals;
CREATE TRIGGER trg_create_proposal_activities_table
    AFTER INSERT ON public.proposals
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_create_proposal_activities_table();