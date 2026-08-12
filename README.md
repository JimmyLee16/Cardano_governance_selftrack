# Cardano Governance Self-track system

Repo công khai cho hệ thống đồng bộ governance data từ Cardano blockchain (Blockfrost/Koios/IPFS) → **PostgreSQL** (Neon, Supabase direct, Railway, Render, local, Docker, etc.).

## Cấu trúc thư mục

```
new_repo/
├── Database/                          # SQL schema + hướng dẫn setup
│   ├── database_schema.sql            # Full schema (CREATE TABLE 6 bảng + triggers)
│   ├── setup_guide.md                 # Hướng dẫn setup PostgreSQL
│   └── migrations/
│       └── 20240101_initial_schema.sql
├── Scripts/
│   ├── Python/                        # 12 script sync (PostgreSQL generic)
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
│   │   ├── backup_neon_db.py
│   │   ├── generate_ai_summaries.py
│   │   └── utils/                     # 9 helper modules
│   └── JavaScript/                    # 11 script sync (PostgreSQL generic)
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
├── package.json                       # Root JS (points to Scripts/JavaScript)
├── .gitignore
└── README.md
```

## Cài đặt

### Python
```bash
cd Scripts/Python
pip install -r ../../requirements.txt
# Hoặc: pip install psycopg2-binary requests python-dotenv
cp ../../.env.example .env
# Chỉnh .env với DATABASE_URL, BLOCKFROST_PROJECT_ID
```

### JavaScript (Node.js)
```bash
cd Scripts/JavaScript
npm install
cp ../../.env.example .env
# Chỉnh .env với DATABASE_URL, BLOCKFROST_PROJECT_ID
```

## Chạy

### Python pipeline
```bash
cd Scripts/Python

# Full sync (chạy hết 7 bước + verify)
python sync_all.py

# Skip drep_delegators (chậm)
python sync_all.py --skip-delegators

# Chỉ chạy 1 bước
python sync_all.py --only=proposals

# Chỉ verify DB
python sync_all.py --verify
# Hoặc
python verify.py
```

### JavaScript pipeline
```bash
cd Scripts/JavaScript

# Full sync
node sync_all.js

# Skip drep_delegators
node sync_all.js --skip-delegators

# Chỉ 1 bước
node sync_all.js --only=proposals

# Chỉ verify
node sync_all.js --verify
# Hoặc
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

Schema chạy được trên bất kỳ PostgreSQL provider nào: Neon, Supabase (direct connection), Railway, Render, Fly.io, local Docker, etc.

## Biến môi trường

| Variable | Required | Mô tả |
|----------|----------|-------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string: `postgresql://user:pass@host:5432/db?sslmode=require` |
| `BLOCKFROST_PROJECT_ID` | ✅ | Blockfrost API key |
| `IPFS_GATEWAY` | ❌ | IPFS gateway (mặc định: `https://ipfs.io/ipfs/`) |

## Lưu ý

- **Python & JavaScript**: Cả hai đều dùng PostgreSQL generic (`DATABASE_URL`), không lock vào provider cụ thể
- ga_* tables được tạo tự động bởi trigger khi insert vào `proposals`
- `sync_vote_activities` bỏ qua IPFS fetch nếu vote đã có comment trong DB
- `sync_drep_info` và `sync_drep_delegators` có checkpoint/resume (chạy nhiều lần để hoàn thành)
- Logs lưu tại `Scripts/Python/logs/` (Python) hoặc console (JS)