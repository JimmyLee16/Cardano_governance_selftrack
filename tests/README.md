# Tests — Setup & Run Guide

How to install a lightweight local PostgreSQL, load the schema, run the test suite, and poke at the data with a few sample queries.

## 1. Install PostgreSQL (lightweight)

Ubuntu / Debian (Codespace container — same as used in the test run):

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo service postgresql start
sudo service postgresql status   # expect: 16/main (port 5432): online
```

## 2. Create a test DB and set the password

```bash
# grant the postgres superuser a password (used for TCP connections from tests)
sudo -n su postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD 'postgres';\""

# create a throwaway test database
sudo -n su postgres -c "createdb cardano_gov_test"
```

## 3. Load the schema

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d cardano_gov_test -f Database/database_schema.sql
```

This creates all tables, indexes, triggers and functions. Run from the repo root.

## 4. Install Python deps (once)

```bash
pip install python-dotenv psycopg2-binary requests
```

## 5. Run the tests

Full suite (unit + schema integration):

```bash
DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/cardano_gov_test" \
  python -m unittest discover -s tests -v
```

Run a single test file:

```bash
DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/cardano_gov_test" \
  python -m unittest tests.test_schema -v
```

Unit-only tests (no DB needed — schema tests will be skipped):

```bash
python -m unittest tests.test_config tests.test_helpers tests.test_checkpoint tests.test_ai_summaries -v
```

Expected result (all green):

```
Ran 87 tests in 0.204s
OK
```

## 6. Sample queries

Verify the schema was loaded correctly:

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d cardano_gov_test
```

List all tables:

```sql
\dt
```

Core tables and their row counts:

```sql
SELECT 'proposals' AS tbl, count(*) FROM proposals
UNION ALL SELECT 'proposal_voting_summary', count(*) FROM proposal_voting_summary
UNION ALL SELECT 'drep_list', count(*) FROM drep_list
UNION ALL SELECT 'drep_info', count(*) FROM drep_info
UNION ALL SELECT 'drep_delegators', count(*) FROM drep_delegators
UNION ALL SELECT 'sync_jobs', count(*) FROM sync_jobs;
```

Check triggers exist:

```sql
SELECT tgname, tgrelid::regclass AS on_table
FROM pg_trigger
WHERE NOT tgisinternal;
```

Check trigger functions:

```sql
SELECT proname FROM pg_proc WHERE proname LIKE 'trg_%';
```

List indexes:

```sql
\d proposals
```

Last sync job (if any data):

```sql
SELECT job_name, status, started_at, finished_at
FROM sync_jobs
ORDER BY started_at DESC
LIMIT 10;
```

Clean up when done:

```bash
sudo -n su postgres -c "psql -c 'DROP DATABASE IF EXISTS cardano_gov_test;'"
```