# 📄 Database Setup Guide

This repository contains Cardano Governance Sync tools. This section covers database setup.

## Neon PostgreSQL Setup

### 1. Connection String Format
```
postgresql://user:password@ep-xxx-pooler.region.aws.neon.tech/dbname?sslmode=require
```

### 2. Required Extensions
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### 3. Core Tables (created by sync scripts)
- `proposals` - Governance proposals metadata
- `proposal_voting_summary` - Aggregated vote counts
- `drep_list` - DRep registry
- `drep_info` - DRep metadata + stake
- `drep_delegators` - Current delegations
- `ga_*` (per proposal) - Vote activities (created automatically via triggers)

### 4. Key Triggers (automatic table creation)
When inserting new proposals, two triggers auto-create:
1. `trg_create_proposal_activities_table` - Creates `ga_<hash>_<sanitized>` table
2. `trg_create_proposal_summary_entry` - Creates entry in voting summary

### 5. Running Initial Setup
```bash
# 1. Clone repo & install
git clone <repo-url>
cd neon_sync
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env
# Fill: BLOCKFROST_PROJECT_ID, NEON_CONN, SUPABASE_KEY

# 3. Run sync pipeline
python scripts/sync_epoch.py
python scripts/sync_proposals.py
python scripts/sync_vote_activities.py --only-active
```

### 6. Verification
```bash
python scripts/verify.py
# Check row counts across all tables
```