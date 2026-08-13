# TUI / CLI Guide

The TUI and CLI in this repo are just a **thin interface layer** — they call the existing sync scripts.
Users can add their own subcommands, custom flags, or new menus as needed.

---

## 1. Quick start

### TUI (full-screen, arrow keys)
```bash
# From repo root
python tui.py          # Python TUI (pure stdlib, ANSI)
node tui.js            # JS TUI (blessed)

# Or from src/
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

## 2. File structure

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
│   │   └── sync_*.py               # 7 sync scripts + verify + backup + ai
│   └── JavaScript/
│       ├── tui.js                  # TUI logic (blessed)
│       ├── cli.js                  # CLI logic (Commander + Inquirer)
│       ├── config.js
│       ├── helpers.js
│       └── sync_*.js
```

---

## 3. TUI is just a wrapper — no sync logic

TUI/CLI **does not implement** sync, verify, backup, AI itself. They only call the existing scripts:

| TUI menu item     | Script called              |
|-------------------|------------------------------|
| Full Sync         | `sync_all.py` / `sync_all.js`|
| Sync: Step        | `sync_all.py --only=<step>`  |
| Verify DB         | `verify.py` / `verify.js`    |
| DB Status         | Direct query via `helpers`   |
| Backup DB         | `backup_db.py`               |
| AI Summaries      | `generate_ai_summaries.py`   |
| View Logs         | Read files in `logs/`        |

**What this means:**
- Add a new sync script → it automatically works through the TUI (just add a menu item)
- Change sync logic → edit in `sync_*.py`, no need to touch the TUI
- TUI/CLI is optional — running `python sync_all.py` directly still works

---

## 4. Add a new subcommand (Python CLI)

### Example: add the `pythonover` command

**Step 1:** Write the script `src/Python/sync_governance_overview.py`

```python
def sync_governance_overview(logger=None):
    # your logic
    pass

if __name__ == "__main__":
    sync_governance_overview()
```

**Step 2:** Add the subcommand to `cli.py`

```python
# In build_parser():
p_overview = sub.add_parser("overview", help="Governance overview report")
p_overview.add_argument("--format", default="table", choices=["table", "json"])
p_overview.set_defaults(func=cmd_overview)

# Handler function:
def cmd_overview(args):
    _print_header("Governance Overview")
    _run_script("sync_governance_overview.py", ["--format", args.format])
```

**Step 3:** Run
```bash
python cli.py overview
python cli.py overview --format json
```

---

## 5. Add custom flags (Python CLI)

Each subcommand already has basic flags. Add a new flag:

```python
# In build_parser(), edit p_sync:
p_sync.add_argument("--batch-size", type=int, default=25, help="Override BATCH_SIZE")
p_sync.add_argument("--dry-run", action="store_true", help="Preview without writing")

# In cmd_sync():
def cmd_sync(args):
    extra = []
    if args.batch_size != 25:
        extra.extend(["--batch-size", str(args.batch_size)])
    if args.dry_run:
        extra.append("--dry-run")
    _run_script("sync_all.py", extra)
```

The underlying script (`sync_all.py`) needs to read this flag:
```python
# In sync_all.py
if "--batch-size" in sys.argv:
    idx = sys.argv.index("--batch-size")
    BATCH_SIZE = int(sys.argv[idx + 1])
```

---

## 6. Add a new menu item (Python TUI)

### Example: add "Governance Overview" to the TUI

**Step 1:** Add to `MAIN_MENU` in `tui.py`:

```python
MAIN_MENU = [
    ("Full Sync",             "Run all 7 sync steps + verify",          True),
    ("Sync: Step",            "Choose a specific sync step",            True),
    ("Verify DB",             "Check row counts across all tables",     True),
    ("DB Status",             "Quick connection + row count check",     True),
    ("Governance Overview",   "Custom report — added by you",           True),  # ← new
    ("Backup DB",             "Export DB to .sql file",                 True),
    ("AI Summaries",          "Generate AI summaries + budget extract", True),
    ("View Logs",             "Browse sync log files",                  True),
    ("Quit",                  "Exit",                                   True),
]
```

**Step 2:** Add a handler in the main loop:

```python
elif action == "Governance Overview":
    action_governance_overview()
```

**Step 3:** Write the action function:

```python
def action_governance_overview():
    show_cursor()
    clear_screen()
    # Your logic here — query DB, format output, etc.
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

## 7. Add a subcommand / menu (JS)

### JS CLI — add a subcommand

```javascript
// In cli.js
program
  .command('overview')
  .description('Governance overview report')
  .option('--format <type>', 'Output format', 'table')
  .action(async (opts) => {
    printHeader('Governance Overview');
    // Your logic, or call a script:
    await runScript('sync_governance_overview.js', ['--format', opts.format]);
  });
```

### JS TUI — add a menu item

```javascript
// In tui.js, edit the items in showMainMenu():
const items = [
  ['Full Sync',           'Run all 7 sync steps + verify'],
  ['Sync: Step',          'Choose a specific sync step'],
  ['Verify DB',           'Check row counts across all tables'],
  ['DB Status',           'Quick connection + row count check'],
  ['Governance Overview', 'Custom report'],           // ← new
  ['Backup DB',           'Export DB to .sql file'],
  ['AI Summaries',        'Generate AI summaries + budget extract'],
  ['View Logs',           'Browse sync log files'],
  ['Quit',                'Exit'],
];

// Add a case in the switch:
case 'Governance Overview':
  await showGovernanceOverview(screen);
  break;

// Write the function:
async function showGovernanceOverview(screen) {
  return new Promise((resolve) => {
    // Use blessed.box or runScript()
    // ...
    resolve();
  });
}
```

---

## 8. Available helpers

### Python (`from helpers import ...`)

| Helper | Description |
|--------|-------|
| `pg_connect()` | Connect to PostgreSQL via `DATABASE_URL` |
| `pg_upsert_batch(conn, table, columns, rows, conflict_cols)` | Upsert batch |
| `pg_row_count(conn, table)` | Count rows |
| `pg_query(conn, sql, params)` | Raw SQL query |
| `pg_truncate(conn, table)` | Delete all rows |
| `pg_drop_triggers(conn, table, triggers)` | Temporarily drop triggers |
| `pg_ensure_proposal_activities_table(conn, proposal_id)` | Create ga_* table |
| `koios_get(endpoint)` / `koios_post(endpoint, body)` | Call the Koios API |
| `blockfrost_get(endpoint)` / `blockfrost_get_all_pages(endpoint)` | Call Blockfrost |
| `fetch_ipfs_metadata(meta_url)` | Fetch IPFS metadata |
| `get_logger(name)` | Logger with file handler |
| `check_env()` | Validate env vars |
| `now_iso()` / `gen_uuid()` / `dedup_rows(rows, pk)` | Utilities |

### JavaScript (`require('./helpers')`)

| Helper | Description |
|--------|-------|
| `pgConnect()` | Connect to PostgreSQL via `DATABASE_URL` |
| `koiosGet(endpoint)` / `koiosPost(endpoint, body)` | Call Koios |
| `blockfrostGet(endpoint)` | Call Blockfrost |
| `fetchIpfsMetadata(metaUrl)` | Fetch IPFS |
| `info(msg)` / `error(msg)` / `warn(msg)` | Logging |

### Config (`from config import ...` / `require('./config')`)

| Variable | Description |
|------|-------|
| `TABLE_COLUMNS` | Dict of column names per table |
| `GA_TABLE_COLUMNS` | Column names for ga_* tables |
| `BATCH_SIZE` / `LARGE_BATCH` | Batch size for upsert |
| `API_DELAY` / `MAX_RETRIES` / `RETRY_DELAY` | API config |
| `PROPOSAL_TRIGGERS` | Triggers to drop/recreate when syncing proposals |
| `SYNC_ORDER` | Order of the 7 sync steps |

---

## 9. Convention

- **TUI/CLI = thin wrapper**: Contains no business logic, only calls scripts
- **Script = real logic**: Each `sync_*.py` runs standalone (`python sync_proposals.py`)
- **Helpers = reusable**: `pg_*`, `koios_*`, `blockfrost_*` shared by all scripts
- **Config = single source of truth**: `TABLE_COLUMNS` in config.py must match the DB schema
- **Add a new feature** = write a new script + add a menu item + add a CLI subcommand
- **Don't hardcode** connection strings, API keys — always read from env vars

---

## 10. Troubleshooting

| Error | Cause | Fix |
|-----|-------------|-----|
| `can't open file 'tui.py'` | Wrong working directory | `cd D:\Blockchain\tooldev\new_repo` then `python tui.py` |
| `ModuleNotFoundError: helpers` | `src/Python` not in sys.path | Run from `src/Python/` or use the root `tui.py` |
| `UnicodeEncodeError` on Windows | Console is cp1252 | TUI fixes UTF-8 automatically, but if it still fails add `chcp 65001` |
| TUI renders wrong layout | Terminal too small | Minimum 80x24 |
| `blessed not found` (JS) | `npm install` not run | `cd src/JavaScript && npm install` |
| `DATABASE_URL not set` | `.env` missing | `cp .env.example .env` then fill in the values |