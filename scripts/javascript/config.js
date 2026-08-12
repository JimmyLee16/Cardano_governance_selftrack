// js/config.js
// Table column definitions cho DRP scripts
// Khớp với config.py::TABLE_COLUMNS

// drep_list columns
exports.drep_list = [
  'drep_id',
  'given_name',
  'content_url',
  'https_uris',
  'amount',
  'active_epoch',
];

// drep_info columns
exports.drep_info = [
  'drep_id',
  'given_name',
  'content_url',
  'https_uris',
  'amount',
  'active_epoch',
  'stake_address',
];

// drep_delegators columns
exports.drep_delegators = [
  'id',
  'drep_id',
  'stake_address',
  'stake_address_hex',
  'script_hash',
  'amount_lovelace',
  'epoch_no',
  'timestamp',
  'timestamp_epoch',
];

// proposals columns (reference)
exports.proposals = [
  'proposal_id',
  'title',
  'status',
  'proposed_epoch',
  'expiration',
  'activities_table_name',
  'abstract',
  'author_name',
  'epoch_no',
  'description',
  'budget_requested',
  'data_fetched_at',
  'created_at',
  'updated_at',
];

// ga_* table columns (reference)
exports.ga_table = [
  'id',
  'block_time',
  'voter_role',
  'voter_id',
  'vote',
  'meta_url',
  'comment',
  'processed_at',
  'created_at',
  'updated_at',
];

// proposal_voting_summary columns
exports.proposal_voting_summary = [
  'proposal_id',
  'epoch_no',
  'drep_yes_votes_cast',
  'drep_no_votes_cast',
  'drep_active_yes_vote_power',
  'drep_yes_vote_power',
  'drep_yes_pct',
  'drep_no_vote_power',
  'drep_no_pct',
  'drep_abstain_votes_cast',
  'drep_active_abstain_vote_power',
  'drep_always_abstain_vote_power',
  'drep_always_no_confidence_vote_power',
  'pool_yes_votes_cast',
  'pool_active_yes_vote_power',
  'pool_yes_vote_power',
  'pool_yes_pct',
  'pool_no_votes_cast',
  'pool_active_no_vote_power',
  'pool_no_vote_power',
  'pool_no_pct',
  'pool_abstain_votes_cast',
  'pool_active_abstain_vote_power',
  'committee_yes_votes_cast',
  'committee_yes_pct',
  'committee_no_votes_cast',
  'committee_no_pct',
  'committee_abstain_votes_cast',
  'data_fetched_at',
  'created_at',
  'updated_at',
];