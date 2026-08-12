"""Sync DRep list from Blockfrost → Neon + Supabase (dual-write).

Blockfrost: GET /api/v0/governance/dreps (paginated)
Target: drep_list table
"""

import sys
import time

from config import TABLE_COLUMNS, BATCH_SIZE
from helpers import (
    get_logger, check_env, blockfrost_get_all_pages, neon_connect,
    neon_truncate, neon_upsert_batch, neon_row_count, now_iso, gen_uuid,
    supabase_upsert_batch, supabase_row_count,
)


def sync_drep_list(logger=None):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: drep_list (Blockfrost → Neon + Supabase) ===")
    columns = TABLE_COLUMNS["drep_list"]

    # 1. Fetch from Blockfrost
    logger.info("[drep_list] Fetching from Blockfrost...")
    raw = blockfrost_get_all_pages("governance/dreps", count=100, max_pages=100)
    logger.info(f"[drep_list] Got {len(raw)} DReps from Blockfrost")

    # 2. Transform
    seen = set()
    rows = []
    for d in raw:
        did = d.get("drep_id")
        if not did or did in seen:
            continue
        seen.add(did)
        rows.append({
            "id": gen_uuid(),
            "drep_id": did,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })

    logger.info(f"[drep_list] Transformed {len(rows)} rows")

    # 3. Upsert to Neon
    conn = neon_connect()

    logger.info(f"[drep_list] Upserting to Neon (batch={BATCH_SIZE})...")
    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        try:
            count = neon_upsert_batch(conn, "drep_list", columns, batch, conflict_cols=["drep_id"])
            inserted += count
        except Exception as e:
            logger.error(f"[drep_list] Neon error at batch {i}: {e}")

    logger.info(f"[drep_list] Neon: Inserted {inserted}/{len(rows)}")
    count = neon_row_count(conn, "drep_list")
    logger.info(f"[drep_list] Neon row count: {count}")
    conn.close()

    # 4. Upsert to Supabase
    logger.info(f"[drep_list] Upserting to Supabase (batch={BATCH_SIZE})...")
    sb_inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        try:
            sb_inserted += supabase_upsert_batch(
                "drep_list", columns, batch, conflict_cols=["drep_id"]
            )
        except Exception as e:
            logger.error(f"[drep_list] Supabase error at batch {i}: {e}")
    logger.info(f"[drep_list] Supabase: Inserted {sb_inserted}/{len(rows)}")
    try:
        sb_count = supabase_row_count("drep_list")
        logger.info(f"[drep_list] Supabase row count: {sb_count}")
    except Exception as e:
        logger.warning(f"[drep_list] Supabase count failed: {e}")

    return count


if __name__ == "__main__":
    check_env()
    sync_drep_list()
