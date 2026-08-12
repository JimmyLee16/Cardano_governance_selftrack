# Cardano Governance Sync Tool

Repo công khai cho hệ thống đồng bộ governance data từ Cardano blockchain (Blockfrost/Koios/IPFS) → **PostgreSQL** (Railway, Render, local, Docker, etc.).

> **⚠️ Đây là phiên bản cơ bản (baseline).**
>
> Đủ để: khởi tạo database, fetch + ghi dữ liệu governance từ Koios/Blockfrost/IPFS vào PostgreSQL, verify, backup, generate AI summaries, TUI/CLI.
>
> Chưa bao gồm các tầng mở rộng (analytics, reporting, sharding, views, functions phụ trợ). Tự thêm khi cần xây dựng các hoạt động theo dõi, phân tích và đánh giá sâu. 

## Cấu trúc thư mục

```
new_repo/
├── Database/                          # SQL schema + hướng dẫn setup
│   ├── database_schema.sql            # Full schema (CREATE TABLE 6 bảng + triggers)
│   ├── setup_guide.md                 # Hướng dẫn setup PostgreSQL
│   └── migrations/
│       └── 20240101_initial_schema.sql
├── src/
│   ├── Python/                        # 14 script sync + CLI + TUI (PostgreSQL generic)
│   │   ├── tui.py                     # TUI entry (full-screen, ANSI, pure stdlib)
│   │   ├── cli.py                     # CLI entry (subcommands)
│   │   ├── config.py                  # Table columns, API config
│   │   ├── helpers.py                 # Core helpers (PostgreSQL, IPFS, Koios, logging)
│   │   ├── sync_epoch.py
│   │   ├── sync_proposals.py
│   │   ├── sync_drep_list.py
│   │   ├── sync_drep_info.py
│   │   ├── sync_drep_delegators.py
│   │   ├── sync_voting_summary.py
│   │   ├── sync_vote_activities.py
│   │   ├── sync_all.py                # Orchestrator (chạy toàn bộ pipeline)
│   │   ├── verify.py                  # Kiểm tra row counts
│   │   ├── _backfill_recent_20.py
│   │   ├── backup_db.py
│   │   ├── generate_ai_summaries.py
│   │   └── utils/                     # 9 helper modules
│   └── JavaScript/                    # 12 script sync + CLI + TUI (PostgreSQL generic)
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
├── .env.example                       # Template biến môi trường
├── requirements.txt                   # Python dependencies
├── package.json                       # Root JS (points to src/JavaScript)
├── tui.py                             # Root entry → src/Python/tui.py
├── tui.js                             # Root entry → src/JavaScript/tui.js
├── .gitignore
└── README.md
```

## Cài đặt

### Python
```bash
cd src/Python
pip install -r ../../requirements.txt
# Hoặc: pip install psycopg2-binary requests python-dotenv
cp ../../.env.example .env
# Chỉnh .env với DATABASE_URL, BLOCKFROST_PROJECT_ID
```

### JavaScript (Node.js)
```bash
cd src/JavaScript
npm install
cp ../../.env.example .env
# Chỉnh .env với DATABASE_URL, BLOCKFROST_PROJECT_ID
```

## Chạy

### TUI (full-screen interactive) — Khuyến nghị
```bash
# Từ repo root — không cần cd
python tui.py          # Python TUI (pure stdlib, ANSI)
node tui.js            # JS TUI (blessed, full-screen)

# Hoặc từ src/
cd src/Python && python tui.py
cd src/JavaScript && node tui.js
```

TUI có menu full-screen, arrow keys để navigate, Enter để chọn:
- Full Sync / Sync từng bước
- Verify DB / DB Status
- Backup DB (full / logic only)
- AI Summaries (dry-run / apply / skip-existing)
- View Logs (chọn file, xem last 100 lines)

### Python CLI (subcommands)
```bash
cd src/Python

# Full sync (chạy hết 7 bước + verify)
python cli.py sync

# Skip drep_delegators (chậm)
python cli.py sync --skip-delegators

# Chỉ chạy 1 bước
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

# Chỉ 1 bước
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

### Direct scripts (không qua CLI)
```bash
# Python
python sync_all.py --skip-delegators
python verify.py

# JavaScript
node sync_all.js --skip-delegators
node verify.js
```

## Các bước sync (thứ tự)

| Bước | Script | Mô tả |
|------|--------|-------|
| 1 | `sync_epoch` | Cập nhật epoch hiện tại từ Koios tip |
| 2 | `sync_proposals` | Lấy proposal list từ Koios → PostgreSQL |
| 3 | `sync_drep_list` | Lấy DRep registry từ Blockfrost |
| 4 | `sync_drep_info` | Lấy metadata/stake DRep từ Blockfrost |
| 5 | `sync_voting_summary` | Lấy voting summary từ Koios |
| 6 | `sync_vote_activities` | Lấy vote activities (votes + IPFS comments) → ga_* tables |
| 7 | `sync_drep_delegators` | Lấy delegators từ Koios (chậm, có thể skip) |

## Database Setup

Xem `Database/setup_guide.md` để setup PostgreSQL với schema đầy đủ (6 bảng chính + triggers tạo ga_* tables tự động).

Schema chạy được trên bất kỳ PostgreSQL provider nào: Railway, Render, Fly.io, local Docker, etc.

## Biến môi trường

| Variable | Required | Mô tả |
|----------|----------|-------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string: `postgresql://user:pass@host:5432/db?sslmode=require` |
| `BLOCKFROST_PROJECT_ID` | ✅ | Blockfrost API key |
| `IPFS_GATEWAY` | ❌ | IPFS gateway (mặc định: `https://ipfs.io/ipfs/`) |

## Phạm vi

Đây là phiên bản cơ bản — đủ để khởi tạo DB, sync, verify, backup, AI summaries, TUI/CLI. Các tầng mở rộng (analytics, reporting, sharding, views, functions phụ trợ) tự thêm khi cần.

## Lưu ý

- **Python & JavaScript**: Cả hai đều dùng PostgreSQL generic (`DATABASE_URL`), không lock vào provider cụ thể
- ga_* tables được tạo tự động bởi trigger khi insert vào `proposals`
- `sync_vote_activities` bỏ qua IPFS fetch nếu vote đã có comment trong DB
- `sync_drep_info` và `sync_drep_delegators` có checkpoint/resume (chạy nhiều lần để hoàn thành)
- Logs lưu tại `src/Python/logs/` (Python) hoặc console (JS)
