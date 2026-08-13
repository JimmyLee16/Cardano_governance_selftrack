"""Tests for generate_ai_summaries.py — is_skippable + API response parsing (mocked).

Run: python -m unittest tests.test_ai_summaries -v
     python -m pytest tests/test_ai_summaries.py -v
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "Python"))

from generate_ai_summaries import is_skippable, generate_summary_and_budget


class TestIsSkippable(unittest.TestCase):

    def test_none(self):
        self.assertFalse(is_skippable(None))

    def test_empty(self):
        self.assertFalse(is_skippable(""))

    def test_normal_proposal(self):
        self.assertFalse(is_skippable("gov_action123"))

    def test_skippable_prefix(self):
        self.assertTrue(is_skippable("final_verify_v3_something"))

    def test_skippable_case_insensitive(self):
        self.assertTrue(is_skippable("FINAL_VERIFY_V3_something"))


class _FakeResponse:
    def __init__(self, content, status=200):
        self._content = content
        self.status_code = status

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def _mock_post(content, status=200):
    return patch(
        "generate_ai_summaries.requests.post",
        return_value=_FakeResponse(content, status),
    )


class TestGenerateSummaryAndBudget(unittest.TestCase):

    def test_short_abstract_returns_none(self):
        with _mock_post(json.dumps({"summary": "x", "budget_requested": 1})):
            self.assertIsNone(generate_summary_and_budget("t", "short", "k"))

    def test_plain_json(self):
        with _mock_post(json.dumps({"summary": "Good summary.", "budget_requested": 500000})):
            result = generate_summary_and_budget("t", "a" * 50, "key")
        self.assertEqual(result["summary"], "Good summary.")
        self.assertEqual(result["budget_requested"], 500000)

    def test_markdown_fenced_json(self):
        content = "```json\n" + json.dumps({"summary": "S.", "budget_requested": 10}) + "\n```"
        with _mock_post(content):
            result = generate_summary_and_budget("t", "a" * 50, "key")
        self.assertEqual(result["summary"], "S.")

    def test_mixed_text_json(self):
        content = 'Here you go:\n{"summary": "S2", "budget_requested": 7}\nThanks'
        with _mock_post(content):
            result = generate_summary_and_budget("t", "a" * 50, "key")
        self.assertEqual(result["summary"], "S2")
        self.assertEqual(result["budget_requested"], 7)

    def test_budget_negative_becomes_none(self):
        with _mock_post(json.dumps({"summary": "S", "budget_requested": -5})):
            result = generate_summary_and_budget("t", "a" * 50, "key")
        self.assertIsNone(result["budget_requested"])

    def test_budget_null(self):
        with _mock_post(json.dumps({"summary": "S", "budget_requested": None})):
            result = generate_summary_and_budget("t", "a" * 50, "key")
        self.assertIsNone(result["budget_requested"])

    def test_summary_truncated_to_500(self):
        with _mock_post(json.dumps({"summary": "x" * 600, "budget_requested": 1})):
            result = generate_summary_and_budget("t", "a" * 50, "key")
        self.assertLessEqual(len(result["summary"]), 500)

    def test_api_error_raises_after_retries(self):
        with patch("generate_ai_summaries.time.sleep"):
            with _mock_post("", status=500):
                with self.assertRaises(Exception):
                    generate_summary_and_budget("t", "a" * 50, "key")


if __name__ == "__main__":
    unittest.main()