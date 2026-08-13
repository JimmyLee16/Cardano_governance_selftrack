# Script Logic Guide

Detailed notes on every script in this repo: what each one does, where it pulls data from, where it writes, and how the pieces fit together.

---

## 1. Architecture Overview

```
 Cardano on-chain data
   Koios API ──────┐
   Blockfrost API ─┤  →  sync_*.py  →  PostgreSQL  →  verify / backup / AI / dashboard
   IPFS gateway ───┘
```

- **Pipeline pattern**: each sync script does **fetch → transform → upsert**.
- **7 sync steps** run in a strict order (see `config.py::SYNC_ORDER`):
  1. `epoch`
  2. `proposals`
  3. `drep_list`
  4. `drep_info`
  5. `voting_summary`
  6. `vote_activities`
  7. `drep_delegators`
- **Two parallel implementations** with identical logic:
  - Python: `src/Python/*.py` (primary)
  - JavaScript: `src/JavaScript/*.js` (equivalent)
- **Entry points**: `sync_all.py` (orchestrator), `cli.py` (subcommands), `tui.py` (full-screen menu).

### Storage (PostgreSQL)
6 core tables + dynamic `ga_*` tables (1 per proposal):

| Table | Populated by | Notes |
|-------|-------------|-------|
| `proposals` | `sync_epoch`, `sync_proposals` | Core; PK `proposal_id` |
| `proposal_voting_summary` | `sync_voting_summary` (+ trigger on proposals insert) | 1 row per proposal |
| `drep_list` | `sync_drep_list` | Registry, PK `drep_id` |
| `drep_info` | `sync_drep_info` | Metadata + stake per DRep |
| `drep_delegators` | `sync_drep_delegators` | Per-epoch snapshots, upsert on `(drep_id, stake_address, epoch_no)` |
| `sync_jobs` | (reserved) | Sync job history |
| `ga_<md5>_<sanitized>` | `sync_vote_activities` | Vote activities per proposal |

---

## 2. `config.py` — single source of truth

- **API endpoints**: `KOIOS_BASE`, `BLOCKFROST_BASE`, `IPFS_GATEWAY` (all from env, with defaults).
- **Keys from env only**: `BLOCKFROST_PROJECT_ID`, `DATABASE_URL` — nothing hardcoded.
- **`TABLE_COLUMNS`**: column list per table. This MUST match the DB schema — every upsert uses these exact column names.
- **`GA_TABLE_COLUMNS`**: shared schema for all `ga_*` tables.
- **`BATCH_SIZE = 25`**, `LARGE_BATCH = 500`, `MAX_RETRIES = 3`, `RETRY_DELAY = 2`, `API_DELAY = 0.5`.
- **`PROPOSAL_TRIGGERS`**: trigger names dropped/recreated around `proposals` inserts.
- **`SYNC_ORDER`**: the canonical 7-step order.

---

## 3. `helpers.py` — shared helpers

### API layer
- `fetch_json(url, headers, params, retries=5)` — GET with retry; handles HTTP 429 (rate-limit, honors `Retry-After`) and 5xx.
- `koios_get(endpoint, params)` / `koios_post(endpoint, body)` — Koios wrapper (POST for batch endpoints).
- `blockfrost_get(endpoint, params)` / `blockfrost_get_all_pages(endpoint, count, max_pages)` — Blockfrost wrapper with `project_id` header + pagination.
- `fetch_ipfs_metadata(meta_url, gateway, voter_role)` — resolves `ipfs://`/bare CIDs against `IPFS_GATEWAY`, then extracts a comment from `body.comment` / `body.rationale` / root `comment` / root `rationale`. Special case: `ConstitutionalCommittee` role returns the **full JSON** string instead.

### PostgreSQL layer
- `pg_connect()` — `psycopg2.connect(DATABASE_URL)`.
- `pg_truncate(conn, table)` — full truncate (used by backup tooling).
- `pg_drop_triggers(conn, table, trigger_names)` / `pg_recreate_proposal_triggers(conn, table)` — drop/recreate the two proposal triggers (needed so inserts during sync don't spawn orphan `ga_*` tables or duplicate summary rows).
- `pg_ensure_proposal_activities_table(conn, proposal_id)` — **replicates the trigger logic in Python**: builds the `ga_<md5[:10]>_<sanitized[:40]>` name, creates the table + unique index on `(voter_id, block_time)` + secondary indexes, then sets `proposals.activities_table_name/created`.
- `pg_upsert_batch(conn, table, columns, rows, conflict_cols, do_update, preserve_cols)` — batch upsert via `execute_values`. `do_update=True` → `ON CONFLICT DO UPDATE` (excluding conflict + `preserve_cols`); `False` → `DO NOTHING`.
- `pg_row_count(conn, table)` — `SELECT count(*)`.
- `pg_query(conn, sql, params)` — raw SQL; returns rows or `[]`.

### Utilities
- `now_iso()`, `gen_uuid()`, `dedup_rows(rows, pk)`.
- `get_logger()` — console (INFO) + file handler into `src/Python/logs/sync_<ts>.log` (DEBUG).
- `check_env()` — exits if `DATABASE_URL` or `BLOCKFROST_PROJECT_ID` is missing.

---

## 4. The 7 sync steps

### Step 1 — `sync_epoch.py`
- **Source**: Koios `GET /api/v1/tip`.
- **Writes**: `proposals.epoch_no` + `proposals.status`.
- Logic:
  1. Read `current_epoch` from Koios tip.
  2. `UPDATE proposals SET epoch_no = current` for all rows.
  3. Mark expired proposals (`expiration <= current_epoch`) → `status = 'done'`.
  4. Mark in-window proposals (`expiration > current_epoch`) → `status = 'active'`.

### Step 2 — `sync_proposals.py`
- **Source**: Koios `GET /api/v1/proposal_list`.
- **Writes**: `proposals` (new rows) + ensures `ga_*` tables.
- Logic:
  1. Fetch + transform: merge `meta_json.body` fields; combine `abstract`/`rationale`/`motivation` into `abstract`; take first reference URI; first author name; `abstract_summary = abstract[:500]`.
  2. Split fetched rows into **new** vs **existing** by `proposal_id`.
  3. For new rows: **drop triggers** first (avoid orphan `ga_*` tables), batch-insert with `conflict_cols=['proposal_id']` and `do_update=False`, then **recreate triggers**.
  4. For existing rows: plain `UPDATE` of metadata fields only — never touches `status` (that's `sync_epoch`'s job).
  5. Ensure `ga_*` table exists for every proposal missing one (via `pg_ensure_proposal_activities_table`).

### Step 3 — `sync_drep_list.py`
- **Source**: Blockfrost `GET /api/v0/governance/dreps` (paginated, 100/page).
- **Writes**: `drep_list` (id, drep_id, timestamps).
- Logic: dedupe by `drep_id`, batch upsert on `conflict_cols=['drep_id']`.

### Step 4 — `sync_drep_info.py`
- **Source**: Blockfrost `GET /api/v0/governance/dreps/{id}` + `/{id}/metadata`; Koios tip for epoch.
- **Writes**: `drep_info`.
- Logic:
  1. Reads all `drep_id` from `drep_list`.
  2. **Checkpoint/resume**: processes only `DREPS_PER_RUN = 50` per run (so a GUI/TUI run stays fast); progress tracked per epoch (via `drep_info_checkpoint` module).
  3. Per DRep: fetch info + metadata; normalize `paymentAddress`/`givenName` (`@value`/`contentUrl`); extract https URIs from references; convert amount lovelace → ADA; extract `content_url` from image.
  4. Flushes to Postgres in chunks (`BATCH_SIZE`) with fresh connection per flush (PgBouncer transaction-pooling workaround) and 3 retries.
  5. Supports a `should_cancel()` callback (used by GUI) that flushes + saves progress on cancel.

Checkpoint module: `drep_info_checkpoint.py` (sibling of `sync_drep_info.py`) — one JSON file per epoch (`drep_info_checkpoint_<epoch>.json`), resume on re-run.

### Step 5 — `sync_voting_summary.py`
- **Source**: Koios `GET /api/v1/proposal_voting_summary?_proposal_id={id}`.
- **Writes**: `proposal_voting_summary`.
- Logic:
  1. Reads `proposal_id` list from `proposals WHERE status IN ('voting','active')`; filters out test proposals (`final_verify_v3...`).
  2. For each proposal: fetch summary, map all `drep_*`, `pool_*`, `committee_*` vote counts/powers into a row.
  3. Batch upsert on `conflict_cols=['proposal_id']` with `preserve_cols=['id','created_at']` (no truncate).

### Step 6 — `sync_vote_activities.py`
- **Source**: Koios `GET /api/v1/proposal_votes?_proposal_id={id}` + IPFS metadata for comments.
- **Writes**: `ga_*` tables.
- Logic:
  1. Reads `(proposal_id, activities_table_name)` from `proposals` (optionally only active/voting, `--only-active`).
  2. For each proposal: fetch votes; compare current row count with Koios; **skip if already up to date** (same count AND all rows have comments).
  3. For votes without a comment yet: fetch IPFS metadata for `comment`; skip IPFS if a comment already exists in DB.
  4. Upsert on `conflict_cols=['voter_id','block_time']`, `preserve_cols=['id']`.

### Step 7 — `sync_drep_delegators.py`
- **Source**: Koios `GET /api/v1/drep_delegators?_drep_id={id}` (paginated, limit=1000) + `/tip`.
- **Writes**: `drep_delegators` (+ `sync_drep_tracking` for checkpoint).
- Logic:
  1. Reads DRep list from `drep_list`, **skips virtual DReps** `drep_always_abstain`, `drep_always_no_confidence` (they have hundreds of thousands of delegators).
  2. **Resume via `sync_drep_tracking` table** (job_type, position, epoch); re-runs resume where they left off; no-op if the current epoch already completed (unless `--force`).
  3. Per DRep: paginate delegators; build flat per-epoch rows; `is_current = (epoch_no == current_epoch)`; `delegation_type` = `script` if `script_hash` else `regular`; flag whales (`> 1M ADA`).
  4. Upsert on `(drep_id, stake_address, epoch_no)`, `preserve_cols=['id']` — **no truncate, no data loss**.
  5. After the full pass, normalize `is_current` so only current-epoch rows are marked current.

---

## 5. `sync_all.py` — orchestrator

- Runs the 7 steps in `SYNC_ORDER` (dynamic import by module name).
- Flags: `--skip-delegators` (skip slow step 7), `--only=<step>`, `--verify` (verify only).
- Calls `sync_vote_activities` with `only_active=True`.
- Ends with a final `verify.py` run.
- **Failure isolation**: each step is wrapped in try/except; one failing step doesn't stop the rest (it logs `❌` and continues).

---

## 6. `verify.py`

- Prints a row-count table for every table in `TABLE_COLUMNS` + extra analytic tables (`drep_voting_cache`, `drep_epoch_stats`, `drep_voting_patterns`, `proposal_report_insights`).
- Also counts all `ga_*` tables via `pg_stat_user_tables`.
- Logic: `SELECT count(*)` per table; prints `ERROR` if the table doesn't exist.

---

## 7. `cli.py` — command line interface

Thin wrapper (no business logic) around the scripts:

| Command | Calls |
|---------|-------|
| `sync [step] [--skip-delegators]` | `sync_all.py` with `--only=<step>` |
| `verify` | `verify.py` |
| `backup [--no-data] [--tables] [--out]` | `backup_db.py` |
| `ai [--apply] [--skip-existing]` | `generate_ai_summaries.py` |
| `logs [--tail]` | reads `src/Python/logs/*.log` |
| `status` | inline: connection + row counts + `ga_*` count |

Runs sibling scripts via `subprocess` with `sys.executable`.

---

## 8. `tui.py` — full-screen menu

Pure-stdlib ANSI TUI (msvcrt on Windows, termios on Unix). No sync logic — every menu item shells out to a script:

| Menu | Action |
|------|--------|
| Full Sync | `sync_all.py` |
| Sync: Step | `sync_all.py --only=<step>` |
| Verify DB | `verify.py` |
| DB Status | inline `pg_row_count` |
| Backup DB | `backup_db.py` / `backup_db.py --no-data` |
| AI Summaries | `generate_ai_summaries.py --dry-run` / `--apply` / `--apply --skip-existing` |
| View Logs | reads log files, view last 80 lines |

---

## 9. `backup_db.py`

PostgreSQL backup **without pg_dump** (pure psycopg2), writes one `.sql` file:
- Functions/procedures (`pg_get_functiondef`)
- Triggers (`pg_get_triggerdef`)
- Views / matviews (`pg_get_viewdef`)
- Non-primary indexes (`pg_get_indexdef`)
- Sequences (`setval`)
- Data via `COPY ... FROM STDIN` (pg_dump-compatible)

Flags: `--tables a,b,c`, `--no-data` (logic only), `--out path.sql`.

> Restore note: data uses COPY, so target tables must already exist; set `session_replication_role=replica` before restore if triggers should NOT re-fire.

---

## 10. `generate_ai_summaries.py`

Uses any **OpenAI-compatible** API (OpenAI, Azure, NIM, Groq, Together, OpenRouter, Ollama, vLLM, LM Studio) to fill:
- `proposals.abstract_summary` (200–400 char plain-text summary)
- `proposals.budget_requested` (ADA amount, or NULL if not mentioned)

- Env: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.
- Prompt asks the model to return JSON `{summary, budget_requested}`; robust JSON extraction handles markdown fences/mixed text.
- **Flags**: `--dry-run` (default, preview only), `--apply` (write), `--apply --skip-existing` (only NULL fields — for incremental runs after new syncs).
- Skips test proposals (`final_verify_v3_...`) and abstracts shorter than 20 chars.
- Per-field "only update if NULL/empty" logic; reconnects to Postgres if SSL drops; rate-limits between calls.

---

## 11. `utils/` — debugging / inspection scripts

| Script | What it does |
|--------|--------------|
| `_check_expiration.py` | Inspects `expiration`/`epoch_no`/`status` column types + samples; counts expired vs active vs current Koios epoch |
| `_check_status.py` | Status distribution in `proposals` |
| `_check_trigger.py` | Inspects triggers on `proposals` |
| `_check_trigger_type.py` | Verifies actual trigger type (BEFORE/AFTER) + proposal count |
| `_debug_ipfs.py` | Tests IPFS fetch against a real `meta_url` from Koios |
| `_debug_koios_votes.py` | Dumps raw Koios `proposal_votes` response for a sample proposal |
| `_debug_meta_url.py` | Checks `meta_url` type/value |
| `_find_dup_ga.py` | Finds duplicate `ga_*` tables |

---

## 12. JavaScript equivalents (`src/JavaScript/`)

Same pipeline, Node.js, using `node-fetch` + `pg`:
- `config.js` — column definitions mirroring `config.py::TABLE_COLUMNS`.
- `helpers.js` — `pgConnect`, `pgUpsertBatch`, `koiosGet/Post`, `blockfrostGet`, `fetchIpfsMetadata`, logging.
- `sync_*.js` — one file per step; `sync_all.js` orchestrator; `verify.js`; `cli.js` (Commander + Inquirer); `tui.js` (blessed).

Behavior differences worth noting:
- `sync_drep_info.js` uses an in-memory slice approach (`DREPS_PER_RUN`) instead of the JSON checkpoint file.
- `sync_drep_delegators.js` normalizes `is_current` after a full pass, same as Python.

---

## 13. Key design decisions & gotchas

1. **Order matters** — `voting_summary` and `vote_activities` need `proposals`; `drep_info`/`drep_delegators` need `drep_list`. Always run via `sync_all.py` or follow `SYNC_ORDER`.
2. **`ga_*` tables are created two ways**: by the `BEFORE INSERT` trigger `trg_create_proposal_activities_table`, and (for safety) by `pg_ensure_proposal_activities_table` inside `sync_proposals`. Both produce the same name scheme: `ga_<md5(proposal_id)[:10]>_<sanitized[:40]>`.
3. **Triggers are dropped during inserts** in `sync_proposals` to avoid orphan `ga_*` tables / duplicate summary rows; they are recreated afterwards.
4. **`status` is only owned by `sync_epoch`** — `sync_proposals` never overwrites it.
5. **Checkpoint/resume**:
   - `drep_info`: per-epoch progress in a local JSON file (`src/Python/drep_info_checkpoint_<epoch>.json`, managed by `drep_info_checkpoint.py`). The granularity is configurable: `DREPS_PER_RUN` controls how many DReps per run, and `CHUNKED_BATCH` controls how often progress is saved.
   - `drep_delegators`: `sync_drep_tracking` table + `--force` to re-run a completed epoch.
6. **No destructive upserts** — `voting_summary`, `vote_activities`, `drep_delegators` all use `ON CONFLICT DO UPDATE` (no truncate), so re-runs are idempotent.
7. **Test data filtered** everywhere via `final_verify_v3` prefix.
8. **Rate limiting** built into every fetch path (`API_DELAY`, retry with backoff, `Retry-After` handling).