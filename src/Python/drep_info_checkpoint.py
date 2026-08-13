"""Checkpoint for sync_drep_info — per-epoch progress saved to a local JSON file.

Design:
  - One checkpoint file per epoch: `drep_info_checkpoint_<epoch>.json`.
  - Stores the list of drep_ids already processed for that epoch.
  - Re-running the script resumes from the checkpoint, so each run only
    processes a slice of DReps instead of all ~2000 every time.

NOTE — checkpoint granularity is arbitrary and fully configurable:
  - How many DReps are processed per run   -> `DREPS_PER_RUN` in sync_drep_info.py
  - How often progress is saved to disk    -> every `CHUNKED_BATCH` rows
      * smaller CHUNKED_BATCH  = more frequent, safer checkpoints (loses less
        progress on crash), at the cost of more JSON writes
      * larger CHUNKED_BATCH   = faster, but a crash loses more progress
  The checkpoint itself is only a bookmark; you can tune either value freely
  without touching this module.
"""

import json
import time
from pathlib import Path

CHECKPOINT_DIR = Path(__file__).parent

_EPOCH_KEY = "epoch"
_PROCESSED_KEY = "processed"


def _checkpoint_path(epoch):
    return CHECKPOINT_DIR / f"drep_info_checkpoint_{epoch}.json"


def load(epoch):
    """Load the checkpoint for the given epoch.

    Returns {"epoch": <int>, "processed": <list[str]>}.
    A missing, corrupt, or stale (different epoch) file starts fresh.
    """
    path = _checkpoint_path(epoch)
    fresh = {"epoch": epoch, "processed": []}
    if not path.exists():
        return fresh
    try:
        with open(path, encoding="utf-8") as f:
            ckpt = json.load(f)
        if not isinstance(ckpt, dict) or ckpt.get(_EPOCH_KEY) != epoch:
            return fresh
        processed = ckpt.get(_PROCESSED_KEY, [])
        if not isinstance(processed, list):
            processed = []
        return {"epoch": epoch, "processed": processed}
    except Exception:
        return fresh


def mark_done(ckpt, drep_ids):
    """Mark a list of drep_ids as processed (in-memory, deduped)."""
    seen = set(ckpt.get(_PROCESSED_KEY, []))
    for did in drep_ids:
        if did not in seen:
            seen.add(did)
            ckpt[_PROCESSED_KEY].append(did)


def save(ckpt, retries=3):
    """Persist the checkpoint to disk (best-effort, atomic write + retry)."""
    path = _checkpoint_path(ckpt.get(_EPOCH_KEY, 0))
    for attempt in range(retries):
        try:
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(ckpt, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
            return
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)