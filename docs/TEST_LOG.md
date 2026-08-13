# Test Log

Tech log for the test suite of the Cardano Governance self-tracking project.

## Summary

| Metric                | Value        |
|-----------------------|--------------|
| Date                  | 2026-08-13   |
| Python                | 3.12.1       |
| PostgreSQL            | 16.14        |
| Total tests run       | 87           |
| Passed                | 87           |
| Failed                | 0            |
| Skipped               | 0            |

## Test Files

| Test file              | Count | Type                          | Requires DB |
|------------------------|-------|-------------------------------|-------------|
| `tests/test_config.py` | 27    | Unit — config constants       | No          |
| `tests/test_helpers.py`| 28    | Unit — helpers (pure + SQL)   | No          |
| `tests/test_checkpoint.py` | 11 | Unit — checkpoint file logic | No          |
| `tests/test_ai_summaries.py` | 13 | Unit — AI summary parsing | No          |
| `tests/test_schema.py` | 8     | Integration — DB schema       | Yes         |

## Test Environment

- OS: Ubuntu 24.04 (Noble)
- Python: 3.12.1
- PostgreSQL 16.14 via `apt` (`postgresql`, `postgresql-contrib`), started with `service postgresql start`
- Test database: `cardano_gov_test` (user `postgres` / password `postgres`)
- Schema loaded from `Database/database_schema.sql` (tables, indexes, triggers, functions)

### Setup commands

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo service postgresql start

# as postgres superuser:
sudo -n su postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD 'postgres';\""
sudo -n su postgres -c "createdb cardano_gov_test"

# load schema:
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d cardano_gov_test -f Database/database_schema.sql
```

### Run command

```bash
DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/cardano_gov_test" \
  python -m unittest discover -s tests -v
```

Without `DATABASE_URL`, the 8 schema tests are skipped (they only read `information_schema`; they never create or modify the DB).

## What Is Covered

### `test_config.py` (27 tests)
- `TABLE_COLUMNS` / `GA_TABLE_COLUMNS`: all values are lists, strings, no duplicates, all tables have `id` + timestamps; required columns for `proposals`, `drep_list`, `drep_delegators`, `proposal_voting_summary`
- `SYNC_ORDER`: 7 steps, unique, first = `epoch`, last = `drep_delegators`
- `PROPOSAL_TRIGGERS`: 2 triggers expected
- `SyncConfig`: batch size, retries, delays are sane values

### `test_helpers.py` (28 tests)
- `dedup_rows`: empty/custom PK/`None` PK/order preservation/duplicates
- `gen_uuid`: valid v4 UUID string, unique
- `now_iso`: ISO 8601, UTC timezone
- `fetch_ipfs_metadata`: comment/rationale extraction, `ipfs://` + bare-CID gateway resolution, `ConstitutionalCommittee` returns full JSON, error → empty string
- `pg_upsert_batch`: generated SQL (`INSERT ... ON CONFLICT DO UPDATE/DO NOTHING`, `preserve_cols` excluded from `SET`, `VALUES %s`), empty rows → 0, error → rollback (mocked `execute_values` + `quote_ident`, no live DB)

### `test_checkpoint.py` (11 tests)
- `load`: fresh state, roundtrip, stale epoch → fresh, corrupt file → fresh, wrong structure → fresh
- `mark_done`: append, dedupe, empty
- `save`: writes file, no temp leftovers, multi-chunk workflow resume

### `test_ai_summaries.py` (13 tests)
- `is_skippable`: `None`/empty/normal → False; `final_verify_v3_*` prefix → True (case-insensitive)
- `generate_summary_and_budget` (mocked `requests.post`): short abstract → `None`, plain/markdown-fenced/mixed JSON, negative/`None` budget → `None`, summary truncated to 500 chars, HTTP error → raises after retries

### `test_schema.py` (8 tests) — integration
- 6 core tables exist, no unexpected tables
- Expected columns per table
- Expected indexes exist
- Trigger functions exist; `proposal_*` triggers exist
- `uuid-ossp` extension installed

## Result

```
$ DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/cardano_gov_test" python -m unittest discover -s tests
.......................................................................................
----------------------------------------------------------------------
Ran 87 tests in 0.204s

OK
```

## Notes

- Dependencies installed for testing: `python-dotenv`, `psycopg2-binary`, `requests`
- The schema integration test is read-only (queries `information_schema`), safe to run against a non-production DB
- Test DB `cardano_gov_test` left running for further work
