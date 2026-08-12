# 🚀 QUICK START - Cardano Governance Sync Tool

> **Chạy xong 5 bước này trong 5 phút** để có database hoạt động.

---

## ⚡ Bước 1: Clone & Cài đặt

```bash
# 1. Clone repo
git clone <repo-url>
cd neon_sync

# 2. Tạo virtual env (Windows)
python -m venv .venv
.venv\Scripts\activate

# 3. Cài dependencies
pip install -r requirements.txt
```

> **Lưu ý**: Cần Python 3.11+. Nếu dùng Windows, `pip install psycopg2-binary` có thể thất bại do thiếu C compiler - dùng `pip install psycopg2` (sẽ tự build).

---

## ⚡ Bước 2: Cấu hình `.env`

```bash
copy .env.example .env
```

Chỉnh file `.env` với các giá trị sau:

```ini
# ===== Cardano API =====
BLOCKFROST_PROJECT_ID=your_blockfrost_project_id
IPFS_GATEWAY=https://ipfs.io/ipfs/

# ===== Neon PostgreSQL (Nguồn thật) =====
NEON_CONN=postgresql://user:password@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require

# ===== Supabase (Dữ liệu xem/UI) =====
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key        # <--- PHẢI service role key, không phải anon!
SUPABASE_GOVERNANCE_URL_1=https://your-project.supabase.co
SUPABASE_GOVERNANCE_SERVICE_ROLE_KEY_1=your_service_role_key
```

> **Quan trọng**: `NEON_CONN` bắt buộc có `?sslmode=require`. Chuỗi kết nối mẫu:
> `postgresql://ep_user:ep_pwd@ep-cardanainstance-pooler.us-east-1.aws.neon.tech/cardano?sslmode=require`

---

## ⚡ Bước 3: Kiểm tra kết nối

```bash
python -c "
from helpers import neon_connect
conn = neon_connect()
print('✅ Neon connection OK')
conn.close()
"
```

Nếu thấy `✅ Neon connection OK` → Tiếp bước 4.

Nếu lỗi: Kiểm tra `NEON_CONN` có đúng format không, và cho phép IP kết nối tới Neon.

---

## ⚡ Bước 4: Chạy pipeline đồng bộ (full)

```bash
# Chạy tất cả các bước theo đúng thứ tự:
python sync_all.py
```

Hoặc chạy từng bước riêng lẻ (theo thứ tự quan trọng):

```bash
# Bước 4.1: Sync epoch + status proposal
python sync_epoch.py

# Bước 4.2: Sync proposals + tạo ga_* tables (trigger tự động)
python sync_proposals.py

# Bước 4.3: Sync DRep list + info
python sync_drep_list.py
python sync_drep_info.py

# Bước 4.4: Sync vote activities + IPFS comments (QUAN TR�ỌNG)
python sync_vote_activities.py --only-active

# Bước 4.5: Sync delegators (current + history)
python sync_drep_delegators.py
```

> **Lưu ý quan trọng**: Order quan trọng! Bắt buộc chạy theo thứ tự trên. Trigger tạo `ga_*` tables sẽ hoạt động đúng khi `proposals` đã có dữ liệu.

---

## ⚡ Bước 5: Xác nhận dữ liệu

```bash
python verify.py
```

**Kết quả mong đợi** (số row count ví dụ):

```
proposals:               45
proposal_voting_summary: 45
ga_<hash>_govaction...:  1280
drep_list:              28
drep_info:              28
drep_delegators:        28
sync_jobs:              6
```

Nếu tất cả bảng đều có row > 0 → **Setup xong! Bắt đầu dùng GUI hoặc script của bạn.**

---

## 🛠 Troubleshooting sau bước 5

| Lỗi phổ biến | Nguyên nhân | Fix |
|--------------|-----------|-----|
| Comment NULL liên tục | `meta_url` bị None hoặc IPFS không có `comment`/`rationale` | Kiểm tra API Koios: `GET /api/v1/proposal_votes?_proposal_id={pid}` |
| `neon_upsert_batch` lỗi batch | Thiếu key `comment` trong row dict | Code đã fix: Luôn include `'comment': comment` (có thể là `''`) |
| `sync_epoch.py` chậm | BATCH_SIZE quá nhỏ | Tăng từ 1000 lên 5000 trong `config.py` |
| `psql` command not found | Chưa cài PostgreSQL client | Windows: tải Installer PG; Mac: `brew install postgresql` |

---

## 📦 Tài liệu tham khảo sau Quick Start

- `README.md` - Documentation đầy đủ (architecture, scripts, GUI, backup)
- `SCHEMA.md` - Chi tiết schema database + trigger + code samples
- `logs/` - Logs tự động tạo sau mỗi lần chạy script
- `backups/` - Sao lưu database (chạy `python backup_neon_db.py`)

---

## 🎯 Bây giờ làm gì?

1. **Chạy GUI**: `python gui.py` - có giao diện kéo thả từng bước
2. **Xem code mẫu**: `SCHEMA.md` có kèm code cho upsert, fetch IPPS, backup
3. **Tự động hóa**: Thêm vào Task Scheduler (Windows) hoặc cron (Linux/Mac) để chạy hàng giờ/ngày
4. **Deploy Supabase Edge Functions** (optional): Xem `README.md` section ☁️ Supabase Edge Functions

---
*Quick Start tự động tạo vào 12/08/2026*