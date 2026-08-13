# 🚀 QUICK START - Cardano Governance Sync Tool

> **Complete these 5 steps in 5 minutes** to get a working database.

---

## ⚡ Step 1: Clone & Install

```bash
# 1. Clone repo
git clone <repo-url>
cd neon_sync

# 2. Create virtual env (Windows)
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

> **Note**: Python 3.11+ is required. On Windows, `pip install psycopg2-binary` may fail due to a missing C compiler - use `pip install psycopg2` (it will build automatically).

---

## ⚡ Step 2: Configure `.env`

```bash
copy .env.example .env
```

Edit the `.env` file with the following values:

```ini
# ===== Cardano API =====
BLOCKFROST_PROJECT_ID=your_blockfrost_project_id
IPFS_GATEWAY=https://ipfs.io/ipfs/

# ===== Neon PostgreSQL (Real source) =====
NEON_CONN=postgresql://user:password@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require

# ===== Supabase (View/UI data) =====
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key        # <--- MUST be a service role key, not anon!
SUPABASE_GOVERNANCE_URL_1=https://your-project.supabase.co
SUPABASE_GOVERNANCE_SERVICE_ROLE_KEY_1=your_service_role_key
```

> **Important**: `NEON_CONN` must include `?sslmode=require`. Example connection string:
> `postgresql://ep_user:ep_pwd@ep-cardanainstance-pooler.us-east-1.aws.neon.tech/cardano?sslmode=require`

---

## ⚡ Step 3: Check the connection

```bash
python -c "
from helpers import neon_connect
conn = neon_connect()
print('✅ Neon connection OK')
conn.close()
"
```

If you see `✅ Neon connection OK` → Continue to step 4.

On error: Check that `NEON_CONN` has the correct format, and allow your IP to connect to Neon.

---

## ⚡ Step 4: Run the sync pipeline (full)

```bash
# Run all steps in the correct order:
python sync_all.py
```

Or run each step individually (in order of importance):

```bash
# Step 4.1: Sync epoch + proposal status
python sync_epoch.py

# Step 4.2: Sync proposals + create ga_* tables (auto trigger)
python sync_proposals.py

# Step 4.3: Sync DRep list + info
python sync_drep_list.py
python sync_drep_info.py

# Step 4.4: Sync vote activities + IPFS comments (IMPORTANT)
python sync_vote_activities.py --only-active

# Step 4.5: Sync delegators (current + history)
python sync_drep_delegators.py
```

> **Important note**: Order matters! You must run the steps in the order above. The trigger that creates `ga_*` tables only works correctly once `proposals` has data.

---

## ⚡ Step 5: Verify the data

```bash
python verify.py
```

**Expected result** (example row counts):

```
proposals:               45
proposal_voting_summary: 45
ga_<hash>_govaction...:  1280
drep_list:              28
drep_info:              28
drep_delegators:        28
sync_jobs:              6
```

If all tables have row > 0 → **Setup complete! Start using the GUI or your own scripts.**

---

## 🛠 Troubleshooting after step 5

| Common error | Cause | Fix |
|--------------|-----------|-----|
| Comment stays NULL | `meta_url` is None or IPFS has no `comment`/`rationale` | Check the Koios API: `GET /api/v1/proposal_votes?_proposal_id={pid}` |
| `neon_upsert_batch` batch error | Missing `comment` key in the row dict | Code is fixed: Always include `'comment': comment` (may be `''`) |
| `sync_epoch.py` slow | BATCH_SIZE too small | Increase from 1000 to 5000 in `config.py` |
| `psql` command not found | PostgreSQL client not installed | Windows: download PG Installer; Mac: `brew install postgresql` |

---

## 📦 References after Quick Start

- `README.md` - Full documentation (architecture, scripts, GUI, backup)
- `SCHEMA.md` - Database schema details + triggers + code samples
- `logs/` - Logs are created automatically after each script run
- `backups/` - Database backups (run `python backup_neon_db.py`)

---

## 🎯 What to do now?

1. **Run the GUI**: `python gui.py` - has a drag-and-drop interface for each step
2. **View sample code**: `SCHEMA.md` includes code for upsert, fetch IPPS, backup
3. **Automate**: Add to Task Scheduler (Windows) or cron (Linux/Mac) to run hourly/daily
4. **Deploy Supabase Edge Functions** (optional): See the ☁️ Supabase Edge Functions section in `README.md`

---
*Quick Start auto-generated on 12/08/2026*