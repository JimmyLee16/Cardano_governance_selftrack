# Hướng dẫn TUI / CLI

TUI và CLI trong repo này chỉ là **lớp giao diện cơ bản** — gọi các script sync đã có sẵn.
Người dùng tự thêm subcommand, flag tùy chỉnh, hoặc menu mới theo nhu cầu.

---

## 1. Chạy nhanh

### TUI (full-screen, arrow keys)
```bash
# Từ repo root
python tui.py          # Python TUI (pure stdlib, ANSI)
node tui.js            # JS TUI (blessed)

# Hoặc từ src/
cd src/Python && python tui.py
cd src/JavaScript && node tui.js
```

### CLI (subcommands)
```bash
# Python
python src/Python/cli.py sync
python src/Python/cli.py sync proposals
python src/Python/cli.py verify
python src/Python/cli.py status
python src/Python/cli.py backup --no-data
python src/Python/cli.py ai --apply
python src/Python/cli.py logs --tail

# JS
node src/JavaScript/cli.js sync
node src/JavaScript/cli.js sync proposals
node src/JavaScript/cli.js verify
node src/JavaScript/cli.js status
node src/JavaScript/cli.js backup --no-data
node src/JavaScript/cli.js ai --apply
node src/JavaScript/cli.js logs --tail
node src/JavaScript/cli.js              # interactive menu
```

---

## 2. Cấu trúc file

```
new_repo/
├── tui.py                          # Root entry → src/Python/tui.py
├── tui.js                          # Root entry → src/JavaScript/tui.js
├── src/
│   ├── Python/
│   │   ├── tui.py                  # TUI logic (ANSI, msvcrt/termios)
│   │   ├── cli.py                  # CLI logic (argparse)
│   │   ├── config.py               # Table columns, API config
│   │   ├── helpers.py              # pg_connect, pg_upsert_batch, ...
│   │   └── sync_*.py               # 7 script sync + verify + backup + ai
│   └── JavaScript/
│       ├── tui.js                  # TUI logic (blessed)
│       ├── cli.js                  # CLI logic (Commander + Inquirer)
│       ├── config.js
│       ├── helpers.js
│       └── sync_*.js
```

---

## 3. TUI chỉ là wrapper — không chứa logic sync

TUI/CLI **không tự implement** sync, verify, backup, AI. Chúng chỉ gọi các script đã có:

| TUI menu item     | Script được gọi              |
|-------------------|------------------------------|
| Full Sync         | `sync_all.py` / `sync_all.js`|
| Sync: Step        | `sync_all.py --only=<step>`  |
| Verify DB         | `verify.py` / `verify.js`    |
| DB Status         | Query trực tiếp qua `helpers`|
| Backup DB         | `backup_db.py`               |
| AI Summaries      | `generate_ai_summaries.py`   |
| View Logs         | Đọc file trong `logs/`       |

**Điều này có nghĩa:**
- Thêm script sync mới → tự động dùng được qua TUI (chỉ cần thêm menu item)
- Đổi logic sync → sửa trong `sync_*.py`, không cần động TUI
- TUI/CLI là optional — chạy `python sync_all.py` trực tiếp vẫn OK

---

## 4. Thêm subcommand mới (Python CLI)

### Ví dụ: thêm command `pythonover`

**Bước 1:** Viết script `src/Python/sync_governance_overview.py`

```python
def sync_governance_overview(logger=None):
    # logic của bạn
    pass

if __name__ == "__main__":
    sync_governance_overview()
```

**Bước 2:** Thêm subcommand vào `cli.py`

```python
# Trong build_parser():
p_overview = sub.add_parser("overview", help="Governance overview report")
p_overview.add_argument("--format", default="table", choices=["table", "json"])
p_overview.set_defaults(func=cmd_overview)

# Hàm handler:
def cmd_overview(args):
    _print_header("Governance Overview")
    _run_script("sync_governance_overview.py", ["--format", args.format])
```

**Bước 3:** Chạy
```bash
python cli.py overview
python cli.py overview --format json
```

---

## 5. Thêm flag tùy chỉnh (Python CLI)

Mỗi subcommand đã có sẵn flag cơ bản. Thêm flag mới:

```python
# Trong build_parser(), sửa p_sync:
p_sync.add_argument("--batch-size", type=int, default=25, help="Override BATCH_SIZE")
p_sync.add_argument("--dry-run", action="store_true", help="Preview without writing")

# Trong cmd_sync():
def cmd_sync(args):
    extra = []
    if args.batch_size != 25:
        extra.extend(["--batch-size", str(args.batch_size)])
    if args.dry_run:
        extra.append("--dry-run")
    _run_script("sync_all.py", extra)
```

Script underlying (`sync_all.py`) cần đọc flag này:
```python
# Trong sync_all.py
if "--batch-size" in sys.argv:
    idx = sys.argv.index("--batch-size")
    BATCH_SIZE = int(sys.argv[idx + 1])
```

---

## 6. Thêm menu item mới (Python TUI)

### Ví dụ: thêm "Governance Overview" vào TUI

**Bước 1:** Thêm vào `MAIN_MENU` trong `tui.py`:

```python
MAIN_MENU = [
    ("Full Sync",             "Run all 7 sync steps + verify",          True),
    ("Sync: Step",            "Choose a specific sync step",            True),
    ("Verify DB",             "Check row counts across all tables",     True),
    ("DB Status",             "Quick connection + row count check",     True),
    ("Governance Overview",   "Custom report — thêm bởi bạn",           True),  # ← mới
    ("Backup DB",             "Export DB to .sql file",                 True),
    ("AI Summaries",          "Generate AI summaries + budget extract", True),
    ("View Logs",             "Browse sync log files",                  True),
    ("Quit",                  "Exit",                                   True),
]
```

**Bước 2:** Thêm handler trong main loop:

```python
elif action == "Governance Overview":
    action_governance_overview()
```

**Bước 3:** Viết hàm action:

```python
def action_governance_overview():
    show_cursor()
    clear_screen()
    # Logic của bạn ở đây — query DB, format output, v.v.
    from helpers import pg_connect, pg_query
    conn = pg_connect()
    rows = pg_query(conn, "SELECT status, count(*) FROM proposals GROUP BY status")
    print(f"{'Status':<20} {'Count':>10}")
    for row in rows:
        print(f"{row[0]:<20} {row[1]:>10}")
    conn.close()
    input(f"\n{C.GRAY}Press Enter to return...{C.RESET}")
```

---

## 7. Thêm subcommand / menu (JS)

### JS CLI — thêm subcommand

```javascript
// Trong cli.js
program
  .command('overview')
  .description('Governance overview report')
  .option('--format <type>', 'Output format', 'table')
  .action(async (opts) => {
    printHeader('Governance Overview');
    // Logic của bạn, hoặc gọi script:
    await runScript('sync_governance_overview.js', ['--format', opts.format]);
  });
```

### JS TUI — thêm menu item

```javascript
// Trong tui.js, sửa items trong showMainMenu():
const items = [
  ['Full Sync',           'Run all 7 sync steps + verify'],
  ['Sync: Step',          'Choose a specific sync step'],
  ['Verify DB',           'Check row counts across all tables'],
  ['DB Status',           'Quick connection + row count check'],
  ['Governance Overview', 'Custom report'],           // ← mới
  ['Backup DB',           'Export DB to .sql file'],
  ['AI Summaries',        'Generate AI summaries + budget extract'],
  ['View Logs',           'Browse sync log files'],
  ['Quit',                'Exit'],
];

// Thêm case trong switch:
case 'Governance Overview':
  await showGovernanceOverview(screen);
  break;

// Viết hàm:
async function showGovernanceOverview(screen) {
  return new Promise((resolve) => {
    // Dùng blessed.box hoặc runScript()
    // ...
    resolve();
  });
}
```

---

## 8. Các helper có sẵn để dùng

### Python (`from helpers import ...`)

| Helper | Mô tả |
|--------|-------|
| `pg_connect()` | Kết nối PostgreSQL qua `DATABASE_URL` |
| `pg_upsert_batch(conn, table, columns, rows, conflict_cols)` | Upsert batch |
| `pg_row_count(conn, table)` | Đếm rows |
| `pg_query(conn, sql, params)` | Raw SQL query |
| `pg_truncate(conn, table)` | Xóa toàn bộ rows |
| `pg_drop_triggers(conn, table, triggers)` | Drop triggers tạm thời |
| `pg_ensure_proposal_activities_table(conn, proposal_id)` | Tạo ga_* table |
| `koios_get(endpoint)` / `koios_post(endpoint, body)` | Gọi Koios API |
| `blockfrost_get(endpoint)` / `blockfrost_get_all_pages(endpoint)` | Gọi Blockfrost |
| `fetch_ipfs_metadata(meta_url)` | Fetch IPFS metadata |
| `get_logger(name)` | Logger có file handler |
| `check_env()` | Validate env vars |
| `now_iso()` / `gen_uuid()` / `dedup_rows(rows, pk)` | Utilities |

### JavaScript (`require('./helpers')`)

| Helper | Mô tả |
|--------|-------|
| `pgConnect()` | Kết nối PostgreSQL qua `DATABASE_URL` |
| `koiosGet(endpoint)` / `koiosPost(endpoint, body)` | Gọi Koios |
| `blockfrostGet(endpoint)` | Gọi Blockfrost |
| `fetchIpfsMetadata(metaUrl)` | Fetch IPFS |
| `info(msg)` / `error(msg)` / `warn(msg)` | Logging |

### Config (`from config import ...` / `require('./config')`)

| Biến | Mô tả |
|------|-------|
| `TABLE_COLUMNS` | Dict column names per table |
| `GA_TABLE_COLUMNS` | Column names cho ga_* tables |
| `BATCH_SIZE` / `LARGE_BATCH` | Batch size cho upsert |
| `API_DELAY` / `MAX_RETRIES` / `RETRY_DELAY` | API config |
| `PROPOSAL_TRIGGERS` | Triggers cần drop/recreate khi sync proposals |
| `SYNC_ORDER` | Thứ tự 7 bước sync |

---

## 9. Convention

- **TUI/CLI = thin wrapper**: Không chứa business logic, chỉ gọi script
- **Script = logic thật**: Mỗi `sync_*.py` tự chạy độc lập được (`python sync_proposals.py`)
- **Helpers = reusable**: `pg_*`, `koios_*`, `blockfrost_*` dùng chung cho mọi script
- **Config = single source of truth**: `TABLE_COLUMNS` trong config.py phải khớp DB schema
- **Thêm feature mới** = viết script mới + thêm menu item + thêm CLI subcommand
- **Không hardcode** connection string, API key — luôn đọc từ env vars

---

## 10. Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| `can't open file 'tui.py'` | Chạy sai thư mục | `cd D:\Blockchain\tooldev\new_repo` rồi `python tui.py` |
| `ModuleNotFoundError: helpers` | `src/Python` không trong sys.path | Chạy từ `src/Python/` hoặc dùng root `tui.py` |
| `UnicodeEncodeError` trên Windows | Console cp1252 | TUI tự fix UTF-8, nhưng nếu lỗi thêm `chcp 65001` |
| TUI hiển thị sai layout | Terminal quá nhỏ | Tối thiểu 80x24 |
| `blessed not found` (JS) | Chưa `npm install` | `cd src/JavaScript && npm install` |
| `DATABASE_URL not set` | Thiếu `.env` | `cp .env.example .env` rồi điền values |
