"""Tests for pure functions in helpers.py — no DB, no API required.

Run: python -m unittest tests.test_helpers -v
     python -m pytest tests/test_helpers.py -v
"""

import unittest
import uuid
import json
from datetime import datetime, timezone
import sys
from pathlib import Path
from unittest.mock import patch

# Add src/Python to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "Python"))

from helpers import (
    dedup_rows, gen_uuid, now_iso,
    fetch_ipfs_metadata, pg_upsert_batch,
)


class TestGenUuid(unittest.TestCase):

    def test_returns_valid_uuid_string(self):
        result = gen_uuid()
        parsed = uuid.UUID(result)
        self.assertEqual(str(parsed), result)

    def test_returns_v4_uuid(self):
        result = gen_uuid()
        parsed = uuid.UUID(result)
        self.assertEqual(parsed.version, 4)

    def test_generates_unique(self):
        uuids = {gen_uuid() for _ in range(100)}
        self.assertEqual(len(uuids), 100)

    def test_returns_string_not_uuid_object(self):
        result = gen_uuid()
        self.assertIsInstance(result, str)


class TestNowIso(unittest.TestCase):

    def test_returns_iso_format_string(self):
        result = now_iso()
        # Should be parseable by datetime.fromisoformat
        parsed = datetime.fromisoformat(result)
        self.assertIsInstance(parsed, datetime)

    def test_has_timezone_utc(self):
        result = now_iso()
        parsed = datetime.fromisoformat(result)
        self.assertIsNotNone(parsed.tzinfo)
        # Offset should be UTC (0)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)

    def test_close_to_current_time(self):
        before = datetime.now(timezone.utc)
        result = datetime.fromisoformat(now_iso())
        after = datetime.now(timezone.utc)
        self.assertTrue(before <= result <= after)


class TestDedupRows(unittest.TestCase):

    def test_empty_list(self):
        self.assertEqual(dedup_rows([]), [])

    def test_no_duplicates(self):
        rows = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        self.assertEqual(dedup_rows(rows), rows)

    def test_removes_duplicates_by_default_pk(self):
        rows = [
            {"id": "a", "val": 1},
            {"id": "b", "val": 2},
            {"id": "a", "val": 3},  # dup of first
        ]
        result = dedup_rows(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "a")
        self.assertEqual(result[0]["val"], 1)  # keeps first occurrence

    def test_custom_pk(self):
        rows = [
            {"drep_id": "d1", "name": "Alice"},
            {"drep_id": "d2", "name": "Bob"},
            {"drep_id": "d1", "name": "Alice2"},  # dup
        ]
        result = dedup_rows(rows, pk="drep_id")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Alice")  # keeps first

    def test_preserves_order(self):
        rows = [
            {"id": "c"},
            {"id": "a"},
            {"id": "b"},
            {"id": "a"},  # dup
        ]
        result = dedup_rows(rows)
        ids = [r["id"] for r in result]
        self.assertEqual(ids, ["c", "a", "b"])

    def test_none_pk_value(self):
        rows = [{"id": None}, {"id": None}]
        result = dedup_rows(rows)
        # None is hashable, dedup should keep only first
        self.assertEqual(len(result), 1)

    def test_single_row(self):
        rows = [{"id": "only"}]
        self.assertEqual(dedup_rows(rows), rows)


class TestFetchIpfsMetadata(unittest.TestCase):

    def test_empty_meta_url(self):
        self.assertEqual(fetch_ipfs_metadata(""), "")

    def test_extract_body_comment(self):
        with patch("helpers.fetch_json", return_value={"body": {"comment": "nice idea"}}):
            self.assertEqual(fetch_ipfs_metadata("https://x/ipfs/cid"), "nice idea")

    def test_fallback_to_rationale(self):
        with patch("helpers.fetch_json", return_value={"body": {"rationale": "reason"}}):
            self.assertEqual(fetch_ipfs_metadata("https://x/ipfs/cid"), "reason")

    def test_root_comment(self):
        with patch("helpers.fetch_json", return_value={"comment": "root c"}):
            self.assertEqual(fetch_ipfs_metadata("https://x/ipfs/cid"), "root c")

    def test_ipfs_scheme_resolved_against_gateway(self):
        with patch("helpers.fetch_json", return_value={}) as m:
            fetch_ipfs_metadata("ipfs://QmAbC", gateway="https://gw.example/ipfs/")
            m.assert_called_once_with("https://gw.example/ipfs/QmAbC")

    def test_bare_cid_resolved_against_gateway(self):
        with patch("helpers.fetch_json", return_value={}) as m:
            fetch_ipfs_metadata("QmAbC", gateway="https://gw.example/ipfs/")
            m.assert_called_once_with("https://gw.example/ipfs/QmAbC")

    def test_constitutional_committee_returns_full_json(self):
        data = {"body": {"comment": "x"}}
        with patch("helpers.fetch_json", return_value=data):
            result = fetch_ipfs_metadata("https://x", voter_role="ConstitutionalCommittee")
            self.assertEqual(json.loads(result), data)

    def test_failure_returns_empty(self):
        with patch("helpers.fetch_json", side_effect=Exception("boom")):
            self.assertEqual(fetch_ipfs_metadata("https://x"), "")


class _FakeCursor:
    def __init__(self):
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeConn:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.encoding = "utf-8"

    def cursor(self):
        return _FakeCursor()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class TestPgUpsertBatchSql(unittest.TestCase):
    """Verify SQL built by pg_upsert_batch (no real DB — mocks execute_values)."""

    def _run(self, table, columns, rows, **kwargs):
        captured = {}
        conn = _FakeConn()
        with patch("helpers.execute_values") as ev, patch(
            "psycopg2.extensions.quote_ident",
            side_effect=lambda s, ctx=None: '"%s"' % s,
        ):
            ev.side_effect = lambda cur, query, values, **kw: captured.update(
                query=query.as_string(None), values=list(values)
            )
            result = pg_upsert_batch(conn, table, columns, rows, **kwargs)
        return captured, result, conn

    def test_empty_rows_returns_zero(self):
        self.assertEqual(pg_upsert_batch(_FakeConn(), "t", ["a"], []), 0)

    def test_basic_insert_no_conflict(self):
        captured, _, conn = self._run("proposals", ["id", "proposal_id"], [{"id": "1", "proposal_id": "p1"}])
        self.assertIn('INSERT INTO "proposals" ("id", "proposal_id") VALUES %s', captured["query"])
        self.assertNotIn("ON CONFLICT", captured["query"])
        self.assertEqual(captured["values"], [("1", "p1")])
        self.assertTrue(conn.committed)

    def test_conflict_do_update_set_clause(self):
        captured, _, _ = self._run(
            "proposals", ["id", "proposal_id", "title"],
            [{"id": "1", "proposal_id": "p1", "title": "t"}],
            conflict_cols=["proposal_id"],
        )
        self.assertIn('ON CONFLICT ("proposal_id") DO UPDATE', captured["query"])
        self.assertIn('"id" = EXCLUDED."id"', captured["query"])
        self.assertIn('"title" = EXCLUDED."title"', captured["query"])
        self.assertNotIn('"proposal_id" = EXCLUDED', captured["query"])

    def test_conflict_with_preserve_cols_excludes_from_set(self):
        captured, _, _ = self._run(
            "proposals", ["id", "proposal_id", "title"],
            [{"id": "1", "proposal_id": "p1", "title": "t"}],
            conflict_cols=["proposal_id"],
            preserve_cols=["id"],
        )
        self.assertIn('ON CONFLICT ("proposal_id") DO UPDATE', captured["query"])
        self.assertNotIn('"id" = EXCLUDED."id"', captured["query"])
        self.assertIn('"title" = EXCLUDED."title"', captured["query"])

    def test_conflict_do_not_update(self):
        captured, _, _ = self._run(
            "proposals", ["id", "proposal_id"],
            [{"id": "1", "proposal_id": "p1"}],
            conflict_cols=["proposal_id"],
            do_update=False,
        )
        self.assertIn('ON CONFLICT ("proposal_id") DO NOTHING', captured["query"])

    def test_error_triggers_rollback(self):
        conn = _FakeConn()
        with patch("helpers.execute_values", side_effect=Exception("db error")):
            with self.assertRaises(Exception):
                pg_upsert_batch(conn, "t", ["a"], [{"a": 1}])
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)


if __name__ == "__main__":
    unittest.main()
