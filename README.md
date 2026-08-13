# Cardano Governance Sync Tool

Public repo for a governance data sync system from the Cardano blockchain (Blockfrost/Koios/IPFS) → **PostgreSQL** (Railway, Render, local, Docker, etc.).

> **⚠️ This is the baseline version.**
>
> Enough to: initialize the database, fetch + write governance data from Koios/Blockfrost/IPFS into PostgreSQL, verify, backup, generate AI summaries, TUI/CLI.
>
> Does not yet include extension layers (analytics, reporting, sharding, views, auxiliary functions). Add them yourself when you need deep tracking, analysis, and evaluation features.

## Directory Structure

```
new_repo/
├── Database/                          # SQL schema + setup guide
│   ├── database_schema.sql            # Full schema (single entry point, includes all below)
│   ├── README.md                      # DB overview
│   ├── setup_guide.md                 # PostgreSQL setup guide
│   ├── 01_extensions/                 # Extensions
│   │   └── 01_enable_uuid_extension.sql
│   ├── 02_tables/                     # 6 core tables (CREATE TABLE)
│   │   ├── 01_proposals.sql
│   │   ├── 02_proposal_voting_summary.sql
│   │   ├── 03_drep_list.sql
│   │   ├── 04_drep_info.sql
│   │   ├── 05_drep_delegators.sql
│   │   └── 06_sync_jobs.sql
│   ├── 03_indexes/                    # Indexes
│   │   ├── 01_proposals_indexes.sql
│   │   ├── 02_sync_jobs_indexes.sql
│   │   └── 03_drep_delegators_indexes.sql
│   ├── 04_triggers/                   # Triggers (auto-create ga_* tables)
│   │   ├── 01_trg_create_proposal_activities_table.sql
│   │   ├── 02_trg_create_proposal_summary_entry.sql
│   │   └── 03_drop_triggers.sql
│   └── migrations/
│       └── 20240101_initial_schema.sql
├── src/
│   ├── Python/                        # Sync scripts + CLI + TUI + utils (PostgreSQL generic)
│   │   ├── tui.py                     # TUI entry (full-screen, ANSI, pure stdlib)
│   │   ├── cli.py                     # CLI entry (subcommands)
│   │   ├── config.py                  # Table columns, API config
│   │   ├── helpers.py                 # Core helpers (PostgreSQL, IPFS, Koios, logging)
│   │   ├── drep_info_checkpoint.py    # Checkpoint/resume for drep_info sync
│   │   ├── sync_epoch.py
│   │   ├── sync_proposals.py
│   │   ├── sync_drep_list.py
│   │   ├── sync_drep_info.py
│   │   ├── sync_drep_delegators.py
│   │   ├── sync_voting_summary.py
│   │   ├── sync_vote_activities.py
│   │   ├── sync_all.py                # Orchestrator (runs the whole pipeline)
│   │   ├── verify.py                  # Checks row counts
│   │   ├── backup_db.py
│   │   ├── generate_ai_summaries.py
│   │   └── utils/                     # 9 helper/debug modules
│   └── JavaScript/                    # Sync scripts + CLI + TUI (PostgreSQL generic)
│       ├── tui.js                     # TUI entry (blessed, full-screen)
│       ├── cli.js                     # CLI entry (Commander + Inquirer)
│       ├── sync_epoch.js
│       ├── sync_proposals.js
│       ├── sync_drep_list.js
│       ├── sync_drep_info.js
│       ├── sync_drep_delegators.js
│       ├── sync_voting_summary.js
│       ├── sync_vote_activities.js
│       ├── sync_all.js                # Orchestrator
│       ├── verify.js
│       ├── config.js                  # Table column definitions
│       ├── helpers.js                 # Core helpers (PostgreSQL, IPFS, Koios, logging)
│       └── package.json
├── tests/                             # Unit + schema integration tests
│   ├── README.md                      # PostgreSQL setup + how to run tests
│   ├── test_config.py                 # Config constants (no DB)
│   ├── test_helpers.py                # Pure helpers + SQL build (no DB)
│   ├── test_checkpoint.py             # Checkpoint file logic (no DB)
│   ├── test_ai_summaries.py           # AI summary parsing, mocked API (no DB)
│   └── test_schema.py                 # DB schema integration (skipped without DATABASE_URL)
├── docs/                              # Docs
│   ├── SCRIPTS_GUIDE.md               # Script logic notes
│   ├── TUI_CLI_GUIDE.md               # TUI/CLI usage guide
│   └── TEST_LOG.md                    # Test run log
├── UI/                                # Dashboard guide
│   └── DASHBOARD_GUIDE.md             # Streamlit dashboard guide + sample app
├── .env.example                       # Environment variable template
├── requirements.txt                   # Python dependencies
├── package.json                       # Root JS (points to src/JavaScript)
├── tui.py                             # Root entry → src/Python/tui.py
├── tui.js                             # Root entry → src/JavaScript/tui.js
├── QUICK_START.md                     # Quick start guide
├── .gitignore
└── README.md
```

## Installation

### Python
```bash
cd src/Python
pip install -r ../../requirements.txt
# Or: pip install psycopg2-binary requests python-dotenv
cp ../../.env.example .env
# Edit .env with DATABASE_URL, BLOCKFROST_PROJECT_ID
```

### JavaScript (Node.js)
```bash
cd src/JavaScript
npm install
cp ../../.env.example .env
# Edit .env with DATABASE_URL, BLOCKFROST_PROJECT_ID
```

## Run

### TUI (full-screen interactive) — Recommended
```bash
# From repo root — no cd needed
python tui.py          # Python TUI (pure stdlib, ANSI)
node tui.js            # JS TUI (blessed, full-screen)

# Or from src/
cd src/Python && python tui.py
cd src/JavaScript && node tui.js
```

TUI has a full-screen menu, arrow keys to navigate, Enter to select:
- Full Sync / Sync per step
- Verify DB / DB Status
- Backup DB (full / logic only)
- AI Summaries (dry-run / apply / skip-existing)
- View Logs (choose file, view last 100 lines)

### Python CLI (subcommands)
```bash
cd src/Python

# Full sync (runs all 7 steps + verify)
python cli.py sync

# Skip drep_delegators (slow)
python cli.py sync --skip-delegators

# Run only 1 step
python cli.py sync proposals

# Verify DB
python cli.py verify

# Quick DB status
python cli.py status

# Backup DB
python cli.py backup
python cli.py backup --no-data        # logic only

# AI summaries
python cli.py ai --dry-run            # preview
python cli.py ai --apply              # write to DB
python cli.py ai --apply --skip-existing  # only NULL fields

# Logs
python cli.py logs                    # list log files
python cli.py logs --tail             # tail latest log
```

### JavaScript CLI
```bash
cd src/JavaScript

# Full sync
node cli.js sync

# Skip drep_delegators
node cli.js sync --skip-delegators

# Only 1 step
node cli.js sync proposals

# Verify DB
node cli.js verify

# Quick DB status
node cli.js status

# Backup (calls Python backup_db.py)
node cli.js backup
node cli.js backup --no-data

# AI summaries (calls Python generate_ai_summaries.py)
node cli.js ai --apply

# Logs
node cli.js logs
node cli.js logs --tail

# Interactive menu (default when no args)
node cli.js
```

### Direct scripts (bypassing CLI)
```bash
# Python
python sync_all.py --skip-delegators
python verify.py

# JavaScript
node sync_all.js --skip-delegators
node verify.js
```

## Sync steps (in order)

| Step | Script | Description |
|------|--------|-------|
| 1 | `sync_epoch` | Update current epoch from Koios tip |
| 2 | `sync_proposals` | Fetch proposal list from Koios → PostgreSQL |
| 3 | `sync_drep_list` | Fetch DRep registry from Blockfrost |
| 4 | `sync_drep_info` | Fetch DRep metadata/stake from Blockfrost |
| 5 | `sync_voting_summary` | Fetch voting summary from Koios |
| 6 | `sync_vote_activities` | Fetch vote activities (votes + IPFS comments) → ga_* tables |
| 7 | `sync_drep_delegators` | Fetch delegators from Koios (slow, can skip) |

## Database Setup

See `Database/setup_guide.md` to set up PostgreSQL with the full schema (6 main tables + triggers that auto-create ga_* tables).

The schema runs on any PostgreSQL provider: Railway, Render, Fly.io, local Docker, etc.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string: `postgresql://user:pass@host:5432/db?sslmode=require` |
| `BLOCKFROST_PROJECT_ID` | ✅ | Blockfrost API key |
| `IPFS_GATEWAY` | ❌ | IPFS gateway (default: `https://ipfs.io/ipfs/`) |

## Scope

This is the baseline version — enough to initialize the DB, sync, verify, backup, AI summaries, TUI/CLI. Add extension layers (analytics, reporting, sharding, views, auxiliary functions) yourself when needed.

## Notes

- **Python & JavaScript**: Both use generic PostgreSQL (`DATABASE_URL`), not locked to a specific provider
- ga_* tables are auto-created by a trigger on insert into `proposals`
- `sync_vote_activities` skips IPFS fetch if the vote already has a comment in the DB
- `sync_drep_info` and `sync_drep_delegators` support checkpoint/resume (run multiple times to complete)
- Logs saved at `src/Python/logs/` (Python) or console (JS)