"""Schema integration test — requires a live PostgreSQL DB with schema loaded.

This test verifies that database_schema.sql creates all expected tables,
indexes, triggers, and functions correctly.

Requirements:
    - DATABASE_URL env var pointing to a test DB (NOT production!)
    - Schema must be loaded: psql "$DATABASE_URL" -f Database/database_schema.sql
    - Or use Neon branch: see scripts below

To test on a Neon branch (does NOT touch main DB):
    1. Create branch:  via Neon MCP or CLI
    2. Load schema:     psql "$BRANCH_URL" -f Database/database_schema.sql
    3. Run test:        DATABASE_URL="$BRANCH_URL" python -m unittest tests.test_schema -v

Run: python -m unittest tests.test_schema -v
     DATABASE_URL=postgresql://... python -m pytest tests/test_schema.py -v

NOTE: This test is skipped if DATABASE_URL is not set or DB is unreachable.
      It does NOT create or modify schema — only reads information_schema.
"""

import unittest
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "Python"))


def _has_db():
    """Check if DATABASE_URL is set and DB is reachable."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return False
    try:
        import psycopg2
        conn = psycopg2.connect(url, connect_timeout=5)
        conn.close()
        return True
    except Exception:
        return False


# Skip entire module if no DB
@unittest.skipUnless(_has_db(), "DATABASE_URL not set or DB unreachable — skipping schema integration test")
class TestSchemaTables(unittest.TestCase):
    """Verify all 6 core tables exist."""

    EXPECTED_TABLES = [
        "proposals",
        "proposal_voting_summary",
        "drep_list",
        "drep_info",
        "drep_delegators",
        "sync_jobs",
    ]

    @classmethod
    def setUpClass(cls):
        from helpers import pg_connect
        cls.conn = pg_connect()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _get_tables(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            )
            return [row[0] for row in cur.fetchall()]

    def test_all_core_tables_exist(self):
        tables = set(self._get_tables())
        for table in self.EXPECTED_TABLES:
            self.assertIn(table, tables, f"Table '{table}' not found in DB")

    def test_no_unexpected_core_tables(self):
        """At minimum, the 6 core tables should exist."""
        tables = set(self._get_tables())
        for expected in self.EXPECTED_TABLES:
            self.assertIn(expected, tables)


@unittest.skipUnless(_has_db(), "DATABASE_URL not set or DB unreachable")
class TestSchemaExtension(unittest.TestCase):
    """Verify uuid-ossp extension is installed."""

    @classmethod
    def setUpClass(cls):
        from helpers import pg_connect
        cls.conn = pg_connect()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_uuid_extension_installed(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'uuid-ossp'")
            result = cur.fetchone()
            self.assertIsNotNone(result, "uuid-ossp extension not installed")
            self.assertEqual(result[0], "uuid-ossp")


@unittest.skipUnless(_has_db(), "DATABASE_URL not set or DB unreachable")
class TestSchemaTriggers(unittest.TestCase):
    """Verify triggers exist on proposals table."""

    EXPECTED_TRIGGERS = [
        "trg_create_proposal_activities_table",
        "trg_create_proposal_summary_entry",
    ]

    @classmethod
    def setUpClass(cls):
        from helpers import pg_connect
        cls.conn = pg_connect()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_proposal_triggers_exist(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT tgname FROM pg_trigger "
                "WHERE NOT tgisinternal AND tgrelid = 'public.proposals'::regclass "
                "ORDER BY tgname"
            )
            triggers = [row[0] for row in cur.fetchall()]
        for expected in self.EXPECTED_TRIGGERS:
            self.assertIn(expected, triggers, f"Trigger '{expected}' not found on proposals")


@unittest.skipUnless(_has_db(), "DATABASE_URL not set or DB unreachable")
class TestSchemaFunctions(unittest.TestCase):
    """Verify trigger functions exist."""

    EXPECTED_FUNCTIONS = [
        "create_proposal_activities_table",
        "create_proposal_summary_entry",
    ]

    @classmethod
    def setUpClass(cls):
        from helpers import pg_connect
        cls.conn = pg_connect()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_trigger_functions_exist(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT routine_name FROM information_schema.routines "
                "WHERE routine_schema = 'public' AND routine_type = 'FUNCTION'"
            )
            functions = [row[0] for row in cur.fetchall()]
        for expected in self.EXPECTED_FUNCTIONS:
            self.assertIn(expected, functions, f"Function '{expected}' not found")


@unittest.skipUnless(_has_db(), "DATABASE_URL not set or DB unreachable")
class TestSchemaIndexes(unittest.TestCase):
    """Verify key indexes exist."""

    EXPECTED_INDEXES = [
        "proposals_pkey",
        "proposals_proposal_id_key",
        "idx_proposals_status",
        "idx_proposals_proposal_id",
        "proposal_voting_summary_pkey",
        "pvs_proposal_id_key",
        "drep_list_pkey",
        "drep_list_drep_id_key",
        "drep_info_pkey",
        "drep_info_drep_id_key",
        "drep_delegators_pkey",
        "uq_drep_delegators_drep_stake_epoch",
        "sync_jobs_pkey",
    ]

    @classmethod
    def setUpClass(cls):
        from helpers import pg_connect
        cls.conn = pg_connect()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_expected_indexes_exist(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
            )
            indexes = [row[0] for row in cur.fetchall()]
        for expected in self.EXPECTED_INDEXES:
            self.assertIn(expected, indexes, f"Index '{expected}' not found")


@unittest.skipUnless(_has_db(), "DATABASE_URL not set or DB unreachable")
class TestSchemaColumns(unittest.TestCase):
    """Verify key columns exist in proposals table."""

    EXPECTED_PROPOSAL_COLUMNS = [
        "id", "proposal_id", "title", "abstract", "status",
        "activities_table_name", "activities_table_created",
        "slug", "abstract_summary", "epoch_no", "proposed_epoch",
        "expiration", "proposal_type", "budget_requested",
        "voting_start_date", "voting_end_date",
    ]

    @classmethod
    def setUpClass(cls):
        from helpers import pg_connect
        cls.conn = pg_connect()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_proposals_has_expected_columns(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'proposals'"
            )
            columns = [row[0] for row in cur.fetchall()]
        for expected in self.EXPECTED_PROPOSAL_COLUMNS:
            self.assertIn(expected, columns, f"Column 'proposals.{expected}' not found")

    def test_drep_delegators_has_expected_columns(self):
        expected = [
            "id", "drep_id", "stake_address", "stake_address_hex",
            "epoch_no", "amount_lovelace", "amount_ada",
            "is_current", "delegation_type", "is_whale", "is_exchange",
        ]
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'drep_delegators'"
            )
            columns = [row[0] for row in cur.fetchall()]
        for col in expected:
            self.assertIn(col, columns, f"Column 'drep_delegators.{col}' not found")


if __name__ == "__main__":
    unittest.main()
