-- Function & Trigger: Tự động tạo entry trong proposal_voting_summary
-- Chạy AFTER INSERT trên proposals
-- Phụ thuộc: 02_tables/01_proposals.sql, 02_tables/02_proposal_voting_summary.sql

-- Function: Tạo entry trong proposal_voting_summary
CREATE OR REPLACE FUNCTION public.trg_create_proposal_summary_entry()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.proposal_voting_summary (
        proposal_id, epoch_no,
        drep_yes_votes_cast, drep_no_votes_cast,
        drep_active_yes_vote_power, drep_active_no_vote_power,
        pool_yes_votes_cast, pool_no_votes_cast,
        committee_yes_votes_cast, committee_no_votes_cast,
        data_fetched_at
    )
    SELECT
        NEW.proposal_id,
        NEW.epoch_no,
        0, 0, 0, 0,
        0, 0,
        0, 0,
        NOW()
    WHERE NOT EXISTS (
        SELECT 1 FROM public.proposal_voting_summary
        WHERE proposal_id = NEW.proposal_id
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: Chạy sau mỗi INSERT INTO proposals
DROP TRIGGER IF EXISTS trg_create_proposal_summary_entry ON public.proposals;
CREATE TRIGGER trg_create_proposal_summary_entry
    AFTER INSERT ON public.proposals
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_create_proposal_summary_entry();