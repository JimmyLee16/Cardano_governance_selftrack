# Database Schema Structure

```
Database/
├── database_schema.sql              # Master file (combines everything, run this for a full setup)
├── setup_guide.md                   # PostgreSQL setup guide
├── migrations/
│   └── 20240101_initial_schema.sql  # Initial migration (kept as-is)
└── [Individual scripts by purpose]
    ├── 01_extensions/               # PostgreSQL extensions
    │   └── 01_enable_uuid_extension.sql
    ├── 02_tables/                   # Core tables (in dependency order)
    │   ├── 01_proposals.sql
    │   ├── 02_proposal_voting_summary.sql
    │   ├── 03_drep_list.sql
    │   ├── 04_drep_info.sql
    │   ├── 05_drep_delegators.sql
    │   └── 06_sync_jobs.sql
    ├── 03_indexes/                  # Separate indexes
    │   ├── 01_proposals_indexes.sql
    │   ├── 02_sync_jobs_indexes.sql
    │   └── 03_drep_delegators_indexes.sql
    ├── 04_triggers/                 # Triggers & Functions
    │   ├── 01_trg_create_proposal_activities_table.sql  # Auto-creates ga_* tables
    │   ├── 02_trg_create_proposal_summary_entry.sql     # Auto-creates voting_summary entry
    │   └── 03_drop_triggers.sql       # Helper to drop triggers
    └── 05_views/                    # (Reserved for future views)
```

## Schema Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CARDANO GOVERNANCE DB SCHEMA                    │
│                         (PostgreSQL · 6 core tables + ga_*)             │
└─────────────────────────────────────────────────────────────────────────┘

                          ┌───────────────────────┐
                          │      proposals        │
                          │  (core · PK proposal_id) │
                          └───────────┬───────────┘
                                      │
            ┌─────────────────────────┼──────────────────────────┐
            │                         │                          │
            │ 1:1 (FK proposal_id)   │ AFTER INSERT             │ AFTER INSERT
            │                         │                          │
            ▼                         ▼                          ▼
┌───────────────────────┐  ┌─────────────────────┐  ┌──────────────────────────┐
│ proposal_voting_summary│  │  ga_<md5>_<title>   │  │  (trigger creates a new  │
│  PK = proposal_id      │  │  (dynamic, 1/proposal)│  │   row in voting_summary)│
│  FK → proposals        │  │  vote activities     │  └──────────────────────────┘
│  DRep/Pool/Committee   │  │  id, voter_id, vote, │
│  vote counts + power   │  │  comment, block_time │
└───────────────────────┘  └─────────────────────┘
                                      ▲
                                      │ logical link
                                      │ (activities_table_name
                                      │  stored in proposals)
                                      │
                          ┌───────────┴───────────┐
                          │      proposals        │
                          │ .activities_table_name│
                          └───────────────────────┘


  ┌───────────────────────┐
  │      drep_list        │  ◄── DRep registry (PK drep_id)
  │  PK = drep_id (UUID)  │
  └───────────┬───────────┘
              │
     ┌────────┴────────┐
     │ 1:1             │ 1:N
     │ (FK drep_id)    │ (FK drep_id)
     ▼                 ▼
┌──────────────┐  ┌─────────────────────┐
│  drep_info   │  │  drep_delegators    │
│ PK = drep_id │  │  PK = id (UUID)     │
│ FK → drep_list│  │  FK drep_id → drep_list│
│ metadata+stake│  │  unique(drep_id,    │
└──────────────┘  │   stake_address,    │
                  │   epoch_no)         │
                  └─────────────────────┘


  ┌───────────────────────┐
  │      sync_jobs        │  ◄── standalone (sync run history)
  │  PK = id (UUID)       │
  │  job_type, status,    │
  │  config (JSONB)       │
  └───────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│  TRIGGERS (AFTER INSERT ON proposals)                                  │
│                                                                        │
│  1. trg_create_proposal_activities_table                               │
│     → CREATE TABLE ga_<md5(title)[:10]>_<sanitized_title>              │
│     → UPDATE proposals.activities_table_name = table_name              │
│                                                                        │
│  2. trg_create_proposal_summary_entry                                  │
│     → INSERT INTO proposal_voting_summary (proposal_id, epoch_no, 0s) │
│                                                                        │
└─────────────────────────────────────────────────────────────────────────┘

LEGEND
  ───►  Foreign Key (FK)
  ═══►  Logical link (not an FK, stores the table name in a column)
  1:1   One-to-one
  1:N   One-to-many
  PK    Primary Key
  ga_*  Dynamic table, 1 table per proposal (created by trigger)
```

## How to run

### Option 1: Run the master file (recommended)
```bash
psql "$DATABASE_URL" -f database_schema.sql
```

### Option 2: Run files individually (for CI/CD, debug)
```bash
# 1. Extensions
psql "$DATABASE_URL" -f 01_extensions/01_enable_uuid_extension.sql

# 2. Tables (in order)
psql "$DATABASE_URL" -f 02_tables/01_proposals.sql
psql "$DATABASE_URL" -f 02_tables/02_proposal_voting_summary.sql
psql "$DATABASE_URL" -f 02_tables/03_drep_list.sql
psql "$DATABASE_URL" -f 02_tables/04_drep_info.sql
psql "$DATABASE_URL" -f 02_tables/05_drep_delegators.sql
psql "$DATABASE_URL" -f 02_tables/06_sync_jobs.sql

# 3. Indexes
psql "$DATABASE_URL" -f 03_indexes/01_proposals_indexes.sql
psql "$DATABASE_URL" -f 03_indexes/02_sync_jobs_indexes.sql
psql "$DATABASE_URL" -f 03_indexes/03_drep_delegators_indexes.sql

# 4. Triggers
psql "$DATABASE_URL" -f 04_triggers/01_trg_create_proposal_activities_table.sql
psql "$DATABASE_URL" -f 04_triggers/02_trg_create_proposal_summary_entry.sql
```

## Dependencies (Dependency Order)

```
01_extensions/01_enable_uuid_extension.sql
    ↓
02_tables/01_proposals.sql
    ↓
02_tables/02_proposal_voting_summary.sql  (FK → proposals)
    ↓
02_tables/03_drep_list.sql
    ↓
02_tables/04_drep_info.sql         (FK → drep_list)
02_tables/05_drep_delegators.sql   (FK → drep_list)
02_tables/06_sync_jobs.sql
    ↓
03_indexes/*.sql
    ↓
04_triggers/01_trg_create_proposal_activities_table.sql  (AFTER INSERT ON proposals)
04_triggers/02_trg_create_proposal_summary_entry.sql     (AFTER INSERT ON proposals)
```

## Main files

| File | Purpose |
|------|----------|
| `database_schema.sql` | **Master file - run this to set up everything** |
| `01_extensions/01_enable_uuid_extension.sql` | Enable uuid-ossp for uuid_generate_v4() |
| `02_tables/01_proposals.sql` | Core table that stores proposals |
| `02_tables/02_proposal_voting_summary.sql` | Vote aggregation |
| `02_tables/03_drep_list.sql` | DRep registry |
| `02_tables/04_drep_info.sql` | DRep metadata + stake |
| `02_tables/05_drep_delegators.sql` | Delegation snapshots per epoch |
| `02_tables/06_sync_jobs.sql` | Tracks sync job run history |
| `03_indexes/*.sql` | Indexes kept separate for easier maintenance |
| `04_triggers/01_trg_create_proposal_activities_table.sql` | Auto-create ga_* tables |
| `04_triggers/02_trg_create_proposal_summary_entry.sql` | Auto-create voting_summary entry |
| `04_triggers/03_drop_triggers.sql` | Helper to drop triggers on reload |
| `migrations/20240101_initial_schema.sql` | Original migration (kept for history) |

## Note

- The master file `database_schema.sql` uses `\ir` (PostgreSQL relative include) to include the sub-files
- Run via `psql` (cannot be run directly in the pgAdmin query tool because of `\ir`)
- To run on pgAdmin: copy-paste the contents of each file in order
- The schema runs on any PostgreSQL provider: Railway, Render, Fly.io, local Docker, etc.