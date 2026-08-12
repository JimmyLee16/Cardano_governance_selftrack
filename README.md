# Cardano Governance Sync Tool

A Python toolkit for syncing Cardano governance data (proposals, votes, DReps, activities) from **Koios/Blockfrost** → **Neon PostgreSQL** + **Supabase** (dual-write). Includes a PyQt6 GUI, automated backup, and Supabase Edge Functions.

---

## 📦 Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Koios API  │────▶│  Python      │────▶│  Neon PostgreSQL│
│  Blockfrost │     │  Sync Scripts│     │  (Primary)      │
└─────────────┘     └──────┬───────┘     └────────┬────────┘
                           │                      │
                    ┌──────▼───────┐     ┌────────▼────────┐
                    │   Supabase   │     │  Supabase Edge  │
                    │  (Mirror)    │     │  Functions      │
                    └──────────────┘     └─────────────────┘
```

**Data Flow:**
1. **Koios/Blockfrost** → Python scripts → **Neon** (source of truth)
2. **Neon** → Python scripts → **Supabase** (read replica for UI)
3. **Supabase Edge Functions** (optional): Real-time sync for active proposals

---

## 🗄 Database Schema (Neon)

### Core Tables

| Table | Description | Key Columns |
|-------|-------------|-------------|
| `proposals` | Governance proposals metadata | `proposal_id`, `title`, `status`, `proposed_epoch`, `expiration`, `activities_table_name` |
| `proposal_voting_summary` | Aggregated vote counts per proposal | `proposal_id`, `drep_yes_votes_cast`, `drep_no_votes_cast`, `pool_yes_votes_cast`, ... |
| `ga_*` (per proposal) | Vote activities (one table per proposal) | `voter_id`, `voter_role`, `vote`, `meta_url`, `comment`, `block_time` |
| `drep_list` | DRep registry | `drep_id`, `has_script` |
| `drep_info` | DRep metadata & stake | `drep_id`, `amount`, `active_epoch`, `given_name`, `metadata_fetched_at` |
| `drep_delegators` | Current delegations | `drep_id`, `stake_address`, `amount_lovelace`, `epoch_no` |
| `drep_delegators_N` | Historical delegation snapshots | Same as above + epoch suffix |
| `sync_jobs` | Job scheduling config | `job_type`, `status`, `config` (JSON) |

### Auto-Created Tables
- `ga_<hash>_<sanitized_id>` — created by trigger `trg_create_proposal_activities_table` on `proposals` insert
- `proposal_voting_summary` entries created by trigger `trg_create_proposal_summary_entry`

### Key Indexes
- `ga_*` tables: unique index on `(voter_id, block_time)`
- `drep_delegators`: unique on `(drep_id, stake_address, epoch_no)`

---

## ⚙️ Environment Setup

### 1. Clone & Install
```bash
git clone <repo-url>
cd neon_sync
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. Configure `.env`
Copy `.env.example` → `.env` and fill:

```ini
# Cardano API keys
BLOCKFROST_PROJECT_ID=your_blockfrost_project_id_here
IPFS_GATEWAY=https://ipfs.io/ipfs/

# Neon target database
NEON_CONN=postgresql://user:pass@host/dbname?sslmode=require

# Supabase (for dual-write & Edge Functions)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key
SUPABASE_GOVERNANCE_URL_1=https://your-project.supabase.co
SUPABASE_GOVERNANCE_SERVICE_ROLE_KEY_1=your_service_role_key
```

> **Note**: `NEON_CONN` must be a PostgreSQL connection string with SSL. The Neon connection string format:
> `postgresql://user:password@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require`

### 3. Verify Connection
```bash
python -c "from helpers import neon_connect; print('Neon OK:', neon_connect().close())"
```

---

## 🚀 Scripts Reference

### Core Sync Scripts (run in order)

| Script | Purpose | Key Args |
|--------|---------|----------|
| `sync_epoch.py` | Fetch current epoch from Koios; update `proposals.epoch_no` + derive `status` (active/done) | — |
| `sync_proposals.py` | Fetch all proposals from Koios; upsert to `proposals` + create `ga_*` tables via trigger | — |
| `sync_drep_list.py` | Fetch DRep registry from Koios | — |
| `sync_drep_info.py` | Fetch DRep metadata (Blockfrost) + stake | — |
| `sync_drep_delegators.py` | Fetch current delegations + historical snapshots | `--epoch <N>` |
| `sync_voting_summary.py` | Fetch vote aggregates per proposal | — |
| `sync_vote_activities.py` | **Fetch vote activities + IPFS comments** for proposals with `status IN ('voting','active')` | `--only-active` (default) |

### Utility Scripts

| Script | Purpose |
|--------|---------|
| `_backfill_recent_20.py` | Backfill vote summary + activities for **20 most recent proposals by `proposed_epoch`** (fetches IPFS comments for missing votes) |
| `backup_neon_db.py` | Full DB dump (schema + data + functions + triggers) → `.sql` file |
| `sync_all.py` | Run all core sync steps sequentially |
| `sync_bidirectional.py` | Reconcile Neon ↔ Supabase differences |
| `sync_supabase_to_neon.py` | One-way Supabase → Neon sync |
| `verify.py` | Row-count verification across tables |
| `generate_ai_summaries.py` | AI-generated proposal summaries (optional) |

### Running Individual Scripts
```bash
# Full pipeline
python sync_all.py

# Single step
python sync_epoch.py
python sync_proposals.py
python sync_vote_activities.py --only-active

# Backfill missing comments for recent proposals
python _backfill_recent_20.py

# Backup database
python backup_neon_db.py --out backups/my_backup.sql
```

---

## 🖥 GUI (PyQt6)

### Launch
```bash
python gui.py
```

### Features
- **Step-by-step execution** with progress bars & live logs
- **Run order enforced**: epoch → proposals → drep_list → drep_info → voting_summary → vote_activities → drep_delegators
- **Cancel-safe**: each step commits independently
- **Log viewer** with color-coded levels (INFO/WARN/ERROR)
- **Verify tab**: row counts across all tables

### GUI Workflow
1. Click **"Run All"** for full pipeline, or individual step buttons
2. Watch live logs in the output pane
3. Use **"Verify"** after run to confirm row counts
4. Logs saved to `logs/sync_YYYYMMDD_HHMMSS.log`

---

## 💾 Backup & Restore

### Full Backup (schema + data + functions + triggers)
```bash
python backup_neon_db.py                    # timestamped file in backups/
python backup_neon_db.py --out my_backup.sql
python backup_neon_db.py --no-data          # schema only (functions, triggers, views)
python backup_neon_db.py --tables proposals,ga_<hash>...
```

**Output**: `backups/neon_backup_YYYYMMDD_HHMMSS.sql` (~90 MB for full DB)

### Restore
```bash
psql "$NEON_CONN" -f backups/neon_backup_20260812_072301.sql
```
> Requires `psql` client. The dump uses `COPY` for data — tables must exist (run `sync_proposals.py` first to create `ga_*` tables via triggers).

---

## ☁️ Supabase Edge Functions (Optional)

Deployed functions in project `oprjfabqtiqcejoyhjsw`:

| Function | Trigger | Purpose |
|----------|---------|---------|
| `sync-epoch` | Cron (hourly) | Update epoch + proposal status |
| `sync-proposals` | Cron (daily) | Sync proposals metadata |
| `sync-vote-activities` | Cron (5 min) | **Real-time vote activities + IPFS comments** for `voting`/`active` proposals |
| `sync-voting-summary` | Cron (15 min) | Vote aggregates |
| `sync-drep-list/info/delegators` | Cron (daily) | DRep data |
| `sync-all` | Manual | Orchestrates all above |

### Key Logic in `sync-vote-activities` (reference implementation)
```typescript
// 1. Only process proposals with status 'voting' OR 'active'
// 2. For each vote: check if comment already exists in ga_* table
// 3. If missing comment AND meta_url exists → fetch IPFS
// 4. IPFS fetch priority: body.comment → body.rationale → root comment → root rationale
// 5. Upsert with merge-duplicates; only write comment if non-empty
// 6. Skip IPFS fetch if vote already has comment
```

> **Current status**: You are migrating away from Edge Functions → Python scripts are now primary.

---

## 🗂 Project Structure

```
neon_sync/
├── gui.py                    # PyQt6 GUI entry point
├── run_neon_sync.py          # CLI runner (optional)
├── sync_all.py               # Full pipeline orchestrator
├── sync_epoch.py             # Epoch + status sync
├── sync_proposals.py         # Proposals + ga_* table creation
├── sync_drep_list.py         # DRep registry
├── sync_drep_info.py         # DRep metadata + stake
├── sync_drep_delegators.py   # Delegations (current + history)
├── sync_voting_summary.py    # Vote aggregates
├── sync_vote_activities.py   # Vote activities + IPFS comments
├── sync_bidirectional.py     # Neon ↔ Supabase reconciliation
├── sync_supabase_to_neon.py  # Supabase → Neon sync
├── _backfill_recent_20.py    # Backfill 20 recent proposals (IPFS comments)
├── backup_neon_db.py         # Full DB dump utility
├── verify.py                 # Row-count verification
├── config.py                 # Table schemas, constants, env loading
├── helpers.py                # Core helpers: Neon, Supabase, Koios, IPFS, logging
├── requirements.txt          # psycopg2, requests, python-dotenv, PyQt6
├── .env.example              # Environment template
├── backups/                  # Auto-created backup files
├── logs/                     # Auto-created run logs
└── README.md                 # This file
```

---

## 🔧 Development & Debugging

### Enable Debug Logging
```bash
set DEBUG=1
python sync_vote_activities.py
```

### Common Issues

| Issue | Fix |
|-------|-----|
| `NEON_CONN` connection timeout | Check Neon endpoint, SSL mode, firewall |
| `Supabase` 401/403 | Verify `SUPABASE_KEY` is service role key (not anon) |
| `ga_*` table missing | Run `sync_proposals.py` — trigger creates tables |
| Comment not appearing | Check `meta_url` exists in Koios vote data; IPFS gateway reachable |
| Neon connection closed during batch | Script auto-reconnects; increase `BATCH_SIZE` in `config.py` |

### Verify Data Integrity
```bash
python verify.py
# Output: table-by-table row counts for Neon + Supabase
```

---

## 📝 Key Implementation Details

### Comment Fetch Logic (`helpers.py::fetch_ipfs_metadata`)
```python
# Priority order:
1. metaData.body.comment
2. metaData.body.rationale
3. metaData.comment
4. metaData.rationale
5. raw string

# Special: ConstitutionalCommittee → returns full JSON string
```

### Upsert Strategy (Neon)
```python
# conflict_cols=["voter_id", "block_time"]
# preserve_cols=("id", "created_at")   # never overwrite on conflict
# do_update=True                       # UPDATE other columns (including comment)
```

### Upsert Strategy (Supabase)
```python
# on_conflict="voter_id,block_time"
# resolution=merge-duplicates
# omit_cols=("id", "created_at")       # preserve existing
```

### Status Derivation (`sync_epoch.py`)
```sql
-- Active: expiration > current_epoch
UPDATE proposals SET status = 'active' WHERE expiration::int > current_epoch;

-- Done: expiration <= current_epoch
UPDATE proposals SET status = 'done' WHERE expiration::int <= current_epoch;
```

---

## 📋 Checklist for New Environment

- [ ] Neon project created, connection string in `.env`
- [ ] Supabase project created, service role key in `.env`
- [ ] Blockfrost project ID in `.env`
- [ ] `pip install -r requirements.txt`
- [ ] Run `python sync_all.py` (first run creates all tables)
- [ ] Verify row counts with `python verify.py`
- [ ] Configure Supabase Edge Functions (optional)
- [ ] Schedule backups: `python backup_neon_db.py` via cron/Task Scheduler

---

## 🤝 Contributing

1. Fork & create feature branch
2. Run `python verify.py` before/after changes
3. Update docstrings & this README if schema/scripts change
4. PR with clear description of sync logic changes

---

## 📄 License

Internal tool — Cardano Governance Data Sync. Not for public distribution without authorization.