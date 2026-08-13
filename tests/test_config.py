"""Tests for config.py — validate TABLE_COLUMNS structure, no DB required.

Run: python -m unittest tests.test_config -v
     python -m pytest tests/test_config.py -v
"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "Python"))

from config import (
    TABLE_COLUMNS, GA_TABLE_COLUMNS, SYNC_ORDER,
    BATCH_SIZE, API_DELAY, MAX_RETRIES, RETRY_DELAY,
    PROPOSAL_TRIGGERS,
)


class TestTableColumns(unittest.TestCase):

    EXPECTED_TABLES = {
        "proposals", "drep_list", "drep_info",
        "proposal_voting_summary", "drep_delegators",
    }

    def test_has_expected_tables(self):
        tables = set(TABLE_COLUMNS.keys())
        self.assertEqual(tables, self.EXPECTED_TABLES)

    def test_all_tables_have_columns(self):
        for table, cols in TABLE_COLUMNS.items():
            self.assertIsInstance(cols, list, f"{table} columns should be a list")
            self.assertGreater(len(cols), 0, f"{table} should have at least 1 column")

    def test_all_columns_are_strings(self):
        for table, cols in TABLE_COLUMNS.items():
            for col in cols:
                self.assertIsInstance(col, str, f"{table}.{col} should be string")

    def test_no_duplicate_columns(self):
        for table, cols in TABLE_COLUMNS.items():
            self.assertEqual(len(cols), len(set(cols)), f"{table} has duplicate columns")

    def test_proposals_has_required_columns(self):
        cols = TABLE_COLUMNS["proposals"]
        required = {"id", "proposal_id", "title", "status", "activities_table_name"}
        self.assertTrue(required.issubset(set(cols)))

    def test_drep_list_has_required_columns(self):
        cols = TABLE_COLUMNS["drep_list"]
        required = {"id", "drep_id"}
        self.assertTrue(required.issubset(set(cols)))

    def test_drep_delegators_has_required_columns(self):
        cols = TABLE_COLUMNS["drep_delegators"]
        required = {"id", "drep_id", "stake_address", "epoch_no", "amount_lovelace"}
        self.assertTrue(required.issubset(set(cols)))

    def test_proposal_voting_summary_has_required_columns(self):
        cols = TABLE_COLUMNS["proposal_voting_summary"]
        required = {"id", "proposal_id"}
        self.assertTrue(required.issubset(set(cols)))

    def test_all_tables_have_id_column(self):
        for table, cols in TABLE_COLUMNS.items():
            self.assertIn("id", cols, f"{table} should have 'id' column")

    def test_all_tables_have_timestamps(self):
        for table, cols in TABLE_COLUMNS.items():
            self.assertIn("created_at", cols, f"{table} should have 'created_at'")
            self.assertIn("updated_at", cols, f"{table} should have 'updated_at'")


class TestGaTableColumns(unittest.TestCase):

    def test_is_list(self):
        self.assertIsInstance(GA_TABLE_COLUMNS, list)

    def test_has_required_columns(self):
        required = {"id", "block_time", "voter_role", "voter_id", "vote", "comment"}
        self.assertTrue(required.issubset(set(GA_TABLE_COLUMNS)))

    def test_no_duplicates(self):
        self.assertEqual(len(GA_TABLE_COLUMNS), len(set(GA_TABLE_COLUMNS)))

    def test_all_strings(self):
        for col in GA_TABLE_COLUMNS:
            self.assertIsInstance(col, str)


class TestSyncOrder(unittest.TestCase):

    def test_is_list(self):
        self.assertIsInstance(SYNC_ORDER, list)

    def test_has_seven_steps(self):
        self.assertEqual(len(SYNC_ORDER), 7)

    def test_epoch_is_first(self):
        self.assertEqual(SYNC_ORDER[0], "epoch")

    def test_drep_delegators_is_last(self):
        self.assertEqual(SYNC_ORDER[-1], "drep_delegators")

    def test_all_steps_unique(self):
        self.assertEqual(len(SYNC_ORDER), len(set(SYNC_ORDER)))

    def test_all_steps_are_strings(self):
        for step in SYNC_ORDER:
            self.assertIsInstance(step, str)


class TestSyncConfig(unittest.TestCase):

    def test_batch_size_positive(self):
        self.assertGreater(BATCH_SIZE, 0)

    def test_api_delay_non_negative(self):
        self.assertGreaterEqual(API_DELAY, 0)

    def test_max_retries_positive(self):
        self.assertGreater(MAX_RETRIES, 0)

    def test_retry_delay_non_negative(self):
        self.assertGreaterEqual(RETRY_DELAY, 0)


class TestProposalTriggers(unittest.TestCase):

    def test_is_list(self):
        self.assertIsInstance(PROPOSAL_TRIGGERS, list)

    def test_has_two_triggers(self):
        self.assertEqual(len(PROPOSAL_TRIGGERS), 2)

    def test_contains_expected_triggers(self):
        expected = {"trg_create_proposal_activities_table", "trg_create_proposal_summary_entry"}
        self.assertEqual(set(PROPOSAL_TRIGGERS), expected)


if __name__ == "__main__":
    unittest.main()
