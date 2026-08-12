# Database Schema Structure

```
Database/
├── database_schema.sql              # Master file (kết hợp tất cả, chạy file này để setup full)
├── setup_guide.md                   # Hướng dẫn setup PostgreSQL
├── migrations/
│   └── 20240101_initial_schema.sql  # Migration ban đầu (giữ nguyên)
└── [Individual scripts by purpose]
    ├── 01_extensions/               # PostgreSQL extensions
    │   └── 01_enable_uuid_extension.sql
    ├── 02_tables/                   # Core tables (theo thứ tự phụ thuộc)
    │   ├── 01_proposals.sql
    │   ├── 02_proposal_voting_summary.sql
    │   ├── 03_drep_list.sql
    │   ├── 04_drep_info.sql
    │   ├── 05_drep_delegators.sql
    │   └── 06_sync_jobs.sql
    ├── 03_indexes/                  # Indexes riêng biệt
    │   ├── 01_proposals_indexes.sql
    │   ├── 02_sync_jobs_indexes.sql
    │   └── 03_drep_delegators_indexes.sql
    ├── 04_triggers/                 # Triggers & Functions
    │   ├── 01_trg_create_proposal_activities_table.sql  # Tự tạo ga_* table
    │   ├── 02_trg_create_proposal_summary_entry.sql     # Tự tạo voting_summary entry
    │   └── 03_drop_triggers.sql       # Helper drop triggers
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
│ proposal_voting_summary│  │  ga_<md5>_<title>   │  │  (trigger tạo row mới    │
│  PK = proposal_id      │  │  (dynamic, 1/proposal)│  │   trong voting_summary)  │
│  FK → proposals        │  │  vote activities     │  └──────────────────────────┘
│  DRep/Pool/Committee   │  │  id, voter_id, vote, │
│  vote counts + power   │  │  comment, block_time │
└───────────────────────┘  └─────────────────────┘
                                      ▲
                                      │ logical link
                                      │ (activities_table_name
                                      │  lưu trong proposals)
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
  │      sync_jobs        │  ◄── standalone (lịch sử chạy sync)
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
  ═══►  Logical link (không phải FK, lưu tên table trong cột)
  1:1   One-to-one
  1:N   One-to-many
  PK    Primary Key
  ga_*  Dynamic table, 1 table per proposal (tạo bởi trigger)
```

## Cách chạy

### Option 1: Chạy file master (khuyên dùng)
```bash
psql "$DATABASE_URL" -f database_schema.sql
```

### Option 2: Chạy từng file riêng (cho CI/CD, debug)
```bash
# 1. Extensions
psql "$DATABASE_URL" -f 01_extensions/01_enable_uuid_extension.sql

# 2. Tables (theo thứ tự)
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

## Phụ thuộc (Dependency Order)

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

## Files chính

| File | Mục đích |
|------|----------|
| `database_schema.sql` | **File tổng - chạy file này để setup toàn bộ** |
| `01_extensions/01_enable_uuid_extension.sql` | Bật uuid-ossp cho uuid_generate_v4() |
| `02_tables/01_proposals.sql` | Bảng cốt lõi lưu proposals |
| `02_tables/02_proposal_voting_summary.sql` | Tổng hợp vote |
| `02_tables/03_drep_list.sql` | DRep registry |
| `02_tables/04_drep_info.sql` | DRep metadata + stake |
| `02_tables/05_drep_delegators.sql` | Delegation snapshots per epoch |
| `02_tables/06_sync_jobs.sql` | Theo dõi lịch chạy sync jobs |
| `03_indexes/*.sql` | Indexes tách riêng cho dễ maintain |
| `04_triggers/01_trg_create_proposal_activities_table.sql` | Auto-create ga_* tables |
| `04_triggers/02_trg_create_proposal_summary_entry.sql` | Auto-create voting_summary entry |
| `04_triggers/03_drop_triggers.sql` | Helper drop triggers khi reload |
| `migrations/20240101_initial_schema.sql` | Migration gốc (giữ nguyên cho lịch sử) |

## Note

- File master `database_schema.sql` dùng `\ir` (PostgreSQL include relative) để include các file con
- Chạy trên `psql` (không chạy được trên pgAdmin query tool trực tiếp do `\ir`)
- Để chạy trên pgAdmin: copy-paste nội dung từng file theo thứ tự
- Schema chạy được trên bất kỳ PostgreSQL provider nào: Railway, Render, Fly.io, local Docker, etc.