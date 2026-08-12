-- 📄 new_repo\Database\database_schema.sql
-- Complete PostgreSQL Schema for Cardano Governance (Combined Master)
-- Auto-generated from individual scripts in 01_extensions/, 02_tables/, 03_indexes/, 04_triggers/
-- Chạy: psql "$DATABASE_URL" -f database_schema.sql

-- ============================================================
-- 01 Extensions
-- ============================================================
\ir 01_extensions/01_enable_uuid_extension.sql

-- ============================================================
-- 02 Core Tables (theo thứ tự phụ thuộc)
-- ============================================================
\ir 02_tables/01_proposals.sql
\ir 02_tables/02_proposal_voting_summary.sql
\ir 02_tables/03_drep_list.sql
\ir 02_tables/04_drep_info.sql
\ir 02_tables/05_drep_delegators.sql
\ir 02_tables/06_sync_jobs.sql

-- ============================================================
-- 03 Indexes
-- ============================================================
\ir 03_indexes/01_proposals_indexes.sql
\ir 03_indexes/02_sync_jobs_indexes.sql
\ir 03_indexes/03_drep_delegators_indexes.sql

-- ============================================================
-- 04 Triggers & Functions
-- ============================================================
\ir 04_triggers/01_trg_create_proposal_activities_table.sql
\ir 04_triggers/02_trg_create_proposal_summary_entry.sql