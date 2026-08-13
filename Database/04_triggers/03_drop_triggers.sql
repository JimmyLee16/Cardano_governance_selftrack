-- Helper: Drop triggers (used when reloading the schema or running sync_proposals)
-- Depends on: 04_triggers/01_trg_create_proposal_activities_table.sql, 04_triggers/02_trg_create_proposal_summary_entry.sql

DROP TRIGGER IF EXISTS trg_create_proposal_activities_table ON public.proposals;
DROP TRIGGER IF EXISTS trg_create_proposal_summary_entry ON public.proposals;

-- Optional: Drop functions too (uncomment if needed)
-- DROP FUNCTION IF EXISTS public.trg_create_proposal_activities_table();
-- DROP FUNCTION IF EXISTS public.trg_create_proposal_summary_entry();