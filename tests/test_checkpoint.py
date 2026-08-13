"""Tests for drep_info_checkpoint.py — pure file-based checkpoint logic, no DB/API.

Run: python -m unittest tests.test_checkpoint -v
     python -m pytest tests/test_checkpoint.py -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "Python"))

import drep_info_checkpoint as ckpt


class TestCheckpointLoad(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        ckpt.CHECKPOINT_DIR = Path(self._tmp.name)

    def test_load_missing_returns_fresh(self):
        c = ckpt.load(123)
        self.assertEqual(c["epoch"], 123)
        self.assertEqual(c["processed"], [])

    def test_load_roundtrip(self):
        ckpt.save({"epoch": 1, "processed": ["a", "b"]})
        c = ckpt.load(1)
        self.assertEqual(c, {"epoch": 1, "processed": ["a", "b"]})

    def test_load_stale_epoch_starts_fresh(self):
        ckpt.save({"epoch": 1, "processed": ["a"]})
        c = ckpt.load(2)
        self.assertEqual(c["epoch"], 2)
        self.assertEqual(c["processed"], [])

    def test_load_corrupt_file_starts_fresh(self):
        ckpt._checkpoint_path(7).write_text("not json {", encoding="utf-8")
        c = ckpt.load(7)
        self.assertEqual(c["processed"], [])

    def test_load_wrong_structure_starts_fresh(self):
        path = ckpt._checkpoint_path(8)
        path.write_text(json.dumps({"epoch": 8, "processed": "nope"}), encoding="utf-8")
        c = ckpt.load(8)
        self.assertEqual(c["processed"], [])


class TestCheckpointMarkDone(unittest.TestCase):

    def test_mark_done_appends(self):
        c = {"epoch": 1, "processed": ["a"]}
        ckpt.mark_done(c, ["b", "c"])
        self.assertEqual(set(c["processed"]), {"a", "b", "c"})

    def test_mark_done_dedupes(self):
        c = {"epoch": 1, "processed": ["a"]}
        ckpt.mark_done(c, ["a", "a", "b"])
        self.assertEqual(c["processed"], ["a", "b"])

    def test_mark_done_empty(self):
        c = {"epoch": 1, "processed": []}
        ckpt.mark_done(c, [])
        self.assertEqual(c["processed"], [])


class TestCheckpointSave(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        ckpt.CHECKPOINT_DIR = Path(self._tmp.name)

    def test_save_creates_file(self):
        c = {"epoch": 5, "processed": ["x", "y"]}
        ckpt.save(c)
        path = ckpt._checkpoint_path(5)
        self.assertTrue(path.exists())
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), c)

    def test_save_no_temp_leftover(self):
        ckpt.save({"epoch": 5, "processed": []})
        tmps = list(Path(self._tmp.name).glob("*.tmp"))
        self.assertEqual(tmps, [])

    def test_full_workflow_resume(self):
        c = ckpt.load(10)
        ckpt.mark_done(c, ["a", "b"])
        ckpt.save(c)
        ckpt.mark_done(c, ["c"])
        ckpt.save(c)
        reloaded = ckpt.load(10)
        self.assertEqual(set(reloaded["processed"]), {"a", "b", "c"})


if __name__ == "__main__":
    unittest.main()