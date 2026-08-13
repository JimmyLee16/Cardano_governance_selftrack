# 🚀 QUICK START - Cardano Governance Sync Tool

> **Complete these 5 steps in 5 minutes** to get a working database.

---

## ⚡ Step 1: Clone & Install

```bash
# 1. Clone repo
git clone <repo-url>
cd Cardano_governance_selftrack

# 2. Create virtual env
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

> **Note**: Python 3.11+ is required. On Windows, if `pip install psycopg2-binary` fails, use `pip install psycopg2` instead.

---

## ⚡ Step 2: Set up the database

The tool works with **any PostgreSQL** — hosted (Railway, Render, Fly.io, Neon) or local. Pick one:

### Option A: Lite SQL — local PostgreSQL (fastest to test)

```bash
# Ubuntu / Debian / Codespace
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo service postgresql start

# Mac
# brew install postgresql && brew services start postgresql
```

```bash
# Create a DB + set the postgres password
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"
sudo -u postgres createdb cardano_gov

# Load the schema (tables, indexes, triggers, functions)
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d cardano_gov -f Database/database_schema.sql
```

Your connection string is then:

```ini
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/cardano_gov
```

### Option B: Hosted PostgreSQL (Railway, Render, Neon, Fly.io)

Create a DB on your provider, then:

```bash
psql "$DATABASE_URL" -f Database/database_schema.sql
```

> **Important**: `DATABASE_URL` must be `postgresql://user:pass@host:5432/dbname` (+ `?sslmode=require` for hosted providers).

---

## ⚡ Step 3: Configure `.env`

```bash
cp .env.example src/Python/.env
```

Edit `src/Python/.env`:

```ini
# ===== PostgreSQL (from step 2) =====
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/cardano_gov

# ===== Blockfrost (required for DRep list/info) =====
BLOCKFROST_PROJECT_ID=your_blockfrost_project_id

# ===== Optional =====
# IPFS_GATEWAY=https://ipfs.io/ipfs/
# OPENAI_API_KEY=sk-...            # for generate_ai_summaries.py
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o-mini
```

Check the connection:

```bash
cd src/Python
python cli.py status
```

If it shows the DB is reachable → continue to step 4.

---

## ⚡ Step 4: Run the sync pipeline (full)

```bash
cd src/Python

# Full sync (all 7 steps + verify)
python sync_all.py

# Or skip the slow delegators step
python sync_all.py --skip-delegators

# Or run one step at a time (in order!)
python sync_epoch.py
python sync_proposals.py        # also auto-creates ga_* tables (trigger)
python sync_drep_list.py
python sync_drep_info.py
python sync_voting_summary.py
python sync_vote_activities.py  # votes + IPFS comments
python sync_drep_delegators.py  # slow, can skip
```

> **Important**: Order matters! The trigger that creates `ga_*` tables only works once `proposals` has data.

---

## ⚡ Step 5: Verify the data

```bash
cd src/Python
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

If all tables have rows > 0 → **Setup complete!**

---

## 🛠 What to do now?

1. **Run the TUI**: `python tui.py` — full-screen menu for sync/verify/backup/AI/logs
2. **CLI**: `python cli.py sync | verify | status | backup | ai | logs`
3. **Run tests**: see `tests/README.md` (unit tests + schema integration tests)
4. **Read the docs**: `docs/SCRIPTS_GUIDE.md`, `docs/TUI_CLI_GUIDE.md`, `README.md`
5. **Dashboard**: see `UI/DASHBOARD_GUIDE.md` for a Streamlit dashboard guide

---

## 🛠 Troubleshooting

| Common error | Cause | Fix |
|--------------|-----------|-----|
| Comment stays NULL | `meta_url` is None or IPFS has no `comment`/`rationale` | Check the Koios API: `GET /api/v1/proposal_votes?_proposal_id={pid}` |
| Batch error: missing `comment` key | Row dict lacks the key | Always include `'comment': comment` (may be `''`) |
| `sync_drep_info` stops mid-way | API rate limit | Run it again — it resumes from a checkpoint |
| `sync_drep_delegators` too slow | Large delegator set | Use `--skip-delegators` or run repeatedly (it resumes) |
| `psql` command not found | PostgreSQL client not installed | Windows: PG Installer; Mac: `brew install postgresql` |

---

## 📦 References

- `README.md` — Full documentation (architecture, scripts, structure)
- `docs/SCRIPTS_GUIDE.md` — Script logic notes
- `docs/TUI_CLI_GUIDE.md` — TUI/CLI usage guide
- `docs/TEST_LOG.md` — Test run log (87 tests)
- `tests/README.md` — PostgreSQL setup + how to run tests
- `Database/setup_guide.md` — Detailed DB setup guide
- `UI/DASHBOARD_GUIDE.md` — Dashboard guide + sample app
- `logs/` — Logs are created automatically after each script run

---
*Quick Start — updated 13/08/2026*