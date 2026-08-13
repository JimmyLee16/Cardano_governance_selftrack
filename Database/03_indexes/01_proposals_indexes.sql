-- Indexes for: proposals
-- Depends on: 02_tables/01_proposals.sql

CREATE INDEX IF NOT EXISTS idx_proposals_status ON public.proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_proposal_id ON public.proposals(proposal_id);
CREATE INDEX IF NOT EXISTS idx_proposals_epoch ON public.proposals(epoch_no);
