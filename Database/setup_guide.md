# 📄 Database Setup Guide

This repository contains Cardano Governance Sync tools. This section covers database setup for **any PostgreSQL provider** (Railway, Render, Fly.io, local Docker, etc.).

## PostgreSQL Setup

### 1. Connection String Format
```
postgresql://user:password@host:5432/dbname?sslmode=require
```

Examples by provider:
- **Railway**: `postgresql://postgres:password@containers-us-west-xxx.railway.app:5432/railway?sslmode=require`
- **Render**: `postgresql://user:pass@dpg-xxx.render.com:5432/dbname?sslmode=require`
- **Local Docker**: `postgresql://postgres:password@localhost:5432/cardano_gov?sslmode=disable`

### 2. Required Extensions
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### 3. Core Tables (created by sync scripts)
- `proposals` - Governance proposals metadata
- `proposal_voting_summary` - Aggregated vote counts
- `drep_list` - DRep registry
- `drep_info` - DRep metadata + stake
- `drep_delegators` - Current delegations (per-epoch snapshots)
- `ga_*` (per proposal) - Vote activities (created automatically via triggers)

### 4. Key Triggers (automatic table creation)
When inserting new proposals, two triggers auto-create:
1. `trg_create_proposal_activities_table` - Creates `ga_<hash>_<sanitized>` table
2. `trg_create_proposal_summary_entry` - Creates entry in voting summary

### 5. Running Initial Setup
```bash
# 1. Clone repo & install
git clone <repo-url>
cd new_repo
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env
# Fill: BLOCKFROST_PROJECT_ID, DATABASE_URL

# 3. Run database schema
psql "$DATABASE_URL" -f Database/database_schema.sql

# 4. Run sync pipeline
cd Scripts/Python
python sync_all.py
```

### 6. Verification
```bash
python Scripts/Python/verify.py
# Check row counts across all tables
```

## Notes
- Schema (`Database/database_schema.sql`) runs on any PostgreSQL 14+
- No provider-specific features used - pure standard PostgreSQL
- Triggers require `uuid-ossp` extension for `uuid_generate_v4()`