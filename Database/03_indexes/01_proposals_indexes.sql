-- Indexes for: proposals
-- Phụ thuộc: 02_tables/01_proposals.sql

CREATE INDEX IF NOT EXISTS idx_proposals_status ON public.proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_proposed_epoch ON public.proposals(proposed_epoch DESC);
CREATE INDEX IF NOT EXISTS idx_proposals_epoch_no ON public.proposals(epoch_no DESC);