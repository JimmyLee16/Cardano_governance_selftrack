-- Function & Trigger: Auto-create an entry in proposal_voting_summary
-- Runs AFTER INSERT on proposals
-- Depends on: 02_tables/01_proposals.sql, 02_tables/02_proposal_voting_summary.sql

-- Function: Create an entry in proposal_voting_summary
CREATE OR REPLACE FUNCTION public.create_proposal_summary_entry()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.proposal_voting_summary (proposal_id, proposal_type, epoch_no, created_at, updated_at)
    VALUES (NEW.proposal_id, NEW.proposal_type, NEW.epoch_no, NOW(), NOW())
    ON CONFLICT (proposal_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public';

-- Trigger: Runs after each INSERT INTO proposals
DROP TRIGGER IF EXISTS trg_create_proposal_summary_entry ON public.proposals;
CREATE TRIGGER trg_create_proposal_summary_entry
    AFTER INSERT ON public.proposals
    FOR EACH ROW
    EXECUTE FUNCTION public.create_proposal_summary_entry();
