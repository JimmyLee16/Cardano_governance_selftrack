"""Config: API endpoints, table schemas, field mappings, PostgreSQL connection.
Generic PostgreSQL - works with any provider (Railway, Render, local, Docker, etc.)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

# ── API Sources ────────────────────────────────────────────────────
KOIOS_BASE = "https://api.koios.rest/api/v1"
BLOCKFROST_BASE = "https://cardano-mainnet.blockfrost.io/api/v0"
IPFS_GATEWAY = os.getenv("IPFS_GATEWAY", "https://ipfs.io/ipfs/")

# ── API Keys ───────────────────────────────────────────────────────
BLOCKFROST_KEY = os.getenv("BLOCKFROST_PROJECT_ID", "")

# ── PostgreSQL Connection ──────────────────────────────────────────
# Generic PostgreSQL connection string (works with any provider)
# Format: postgresql://user:pass@host:5432/dbname?sslmode=require
DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── Table Schemas (columns matching PostgreSQL DB) ─────────────────
TABLE_COLUMNS = {
    "proposals": [
        "id", "proposal_id", "title", "abstract", "first_reference_uri",
        "author_name", "proposal_index", "proposal_tx_hash", "proposed_epoch",
        "expiration", "proposal_type", "epoch_no", "status", "description",
        "budget_requested", "voting_start_date", "voting_end_date",
        "implementation_start_date", "implementation_end_date",
        "documentation_urls", "discussion_urls", "data_fetched_at",
        "created_at", "updated_at", "activities_table_created",
        "activities_table_name", "abstract_summary", "slug",
    ],
    "drep_list": ["id", "drep_id", "created_at", "updated_at"],
    "drep_info": [
        "id", "drep_id", "amount", "active_epoch", "last_active_epoch",
        "url", "payment_address", "given_name", "content_url", "https_uris",
        "metadata_fetched_at", "created_at", "updated_at",
    ],
    "proposal_voting_summary": [
        "id", "proposal_id", "proposal_type", "epoch_no",
        "drep_yes_votes_cast", "drep_active_yes_vote_power", "drep_yes_vote_power",
        "drep_yes_pct", "drep_no_votes_cast", "drep_active_no_vote_power",
        "drep_no_vote_power", "drep_no_pct", "drep_abstain_votes_cast",
        "drep_active_abstain_vote_power", "drep_abstain_vote_power",
        "drep_always_abstain_vote_power", "drep_always_no_confidence_vote_power",
        "pool_yes_votes_cast", "pool_active_yes_vote_power", "pool_yes_vote_power",
        "pool_yes_pct", "pool_no_votes_cast", "pool_active_no_vote_power",
        "pool_no_vote_power", "pool_no_pct", "pool_abstain_votes_cast",
        "pool_active_abstain_vote_power",
        "pool_passive_always_abstain_votes_assigned",
        "pool_passive_always_abstain_vote_power",
        "pool_passive_always_no_confidence_votes_assigned",
        "pool_passive_always_no_confidence_vote_power",
        "committee_yes_votes_cast", "committee_yes_pct",
        "committee_no_votes_cast", "committee_no_pct",
        "committee_abstain_votes_cast", "data_fetched_at",
        "created_at", "updated_at",
    ],
    "drep_delegators": [
        "id", "drep_id", "stake_address", "stake_address_hex",
        "script_hash", "epoch_no", "amount_lovelace", "amount_ada",
        "is_current", "delegation_type", "first_seen_epoch",
        "last_seen_epoch", "delegation_count", "is_whale", "is_exchange",
        "created_at", "updated_at",
    ],
}

# ga_* tables all share the same schema
GA_TABLE_COLUMNS = [
    "id", "block_time", "voter_role", "voter_id", "vote",
    "meta_url", "comment", "processed_at", "created_at", "updated_at",
]

# ── Sync config ────────────────────────────────────────────────────
BATCH_SIZE = 25
LARGE_BATCH = 500
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
API_DELAY = 0.5  # delay between API calls

# Tables with triggers to drop during insert
PROPOSAL_TRIGGERS = [
    "trg_create_proposal_activities_table",
    "trg_create_proposal_summary_entry",
]

# Sync order
SYNC_ORDER = [
    "epoch",           # update current epoch first
    "proposals",       # then proposals
    "drep_list",       # then drep list
    "drep_info",       # then drep info (needs drep_list)
    "voting_summary",  # voting summary for proposals
    "vote_activities", # ga_* tables (needs proposals)
    "drep_delegators", # delegators (needs drep_list)
]
