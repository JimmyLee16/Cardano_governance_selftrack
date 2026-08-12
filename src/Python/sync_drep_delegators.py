"""Sync DRep delegators from Koios → PostgreSQL (upsert).

Koios: GET /api/v1/drep_delegators?_drep_id={id} (paginated)
       GET /api/v1/tip (for current epoch)
Target: drep_delegators (flat, per-epoch snapshots)

Design:
  - Upsert on (drep_id, stake_address, epoch_no) — no truncate, no data loss.
  - Cell-level checkpoint in sync_drep_tracking (job_type='drep_delegators'):
    re-runs resume where they left off and are no-ops if the epoch already completed.
  - After a full pass, is_current is normalized so only rows of the current epoch
    are marked current; older epoch rows flip to false.
"""

import sys
import time

from config import TABLE_COLUMNS, API_DELAY
from helpers import (
    get_logger, check_env, koios_get, pg_connect, pg_query,
    pg_upsert_batch, pg_row_count, now_iso, gen_uuid,
)

JOB_TYPE = "drep_delegators"

# Virtual DReps representing all undelegated/no-confidence stake on-chain.
# They have hundreds of thousands of delegators (takes days to paginate),
# so they are excluded from sync.
SKIP_DREP_IDS = {"drep_always_abstain", "drep_always_no_confidence"}

COLUMNS = TABLE_COLUMNS["drep_delegators"]
CONFLICT_COLS = ["drep_id", "stake_address", "epoch_no"]

TRACKING_COLS = [
    "id", "job_type", "last_processed_drep_id", "last_processed_pos",
    "batch_size", "total_processed", "last_sync_time",
    "created_at", "updated_at", "current_epoch", "last_snapshot_epoch",
]


# ── Tracking: PostgreSQL ─────────────────────────────────────────────────

def pg_save_tracking(conn, epoch, pos, drep_id, total):
    row = pg_load_tracking(conn)
    now = now_iso()
    if row is None:
        pg_query(
            conn,
            """INSERT INTO sync_drep_tracking
               (job_type, last_processed_drep_id, last_processed_pos,
                batch_size, total_processed, last_sync_time,
                created_at, updated_at, current_epoch, last_snapshot_epoch)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (JOB_TYPE, drep_id, pos, 0, total, now, now, now, epoch, epoch),
        )
    else:
        pg_query(
            conn,
            """UPDATE sync_drep_tracking SET
               last_processed_drep_id=%s, last_processed_pos=%s,
               total_processed=%s, last_sync_time=%s, updated_at=%s,
               current_epoch=%s, last_snapshot_epoch=%s
               WHERE job_type=%s""",
            (drep_id, pos, total, now, now, epoch, epoch, JOB_TYPE),
        )


def pg_load_tracking(conn):
    def _load():
        col_list = ", ".join(TRACKING_COLS)
        rows = pg_query(
            conn,
            f"SELECT {col_list} FROM sync_drep_tracking WHERE job_type = %s",
            (JOB_TYPE,),
        )
        if not rows:
            return None
        return dict(zip(TRACKING_COLS, rows[0]))
    # Simple retry
    for _ in range(3):
        try:
            return _load()
        except Exception as e:
            time.sleep(1)
    return None


# ── is_current normalization ───────────────────────────────────────────

def pg_normalize_is_current(conn, epoch):
    pg_query(
        conn,
        """UPDATE drep_delegators
           SET is_current = (epoch_no = %s)""",
        (epoch,),
    )


# ── Main ───────────────────────────────────────────────────────────────

def sync_drep_delegators(logger=None, force=False, should_cancel=None):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: drep_delegators (Koios → PostgreSQL, upsert) ===")

    # 1. Current epoch
    tip = koios_get("tip")
    current_epoch = tip[0].get("epoch_no", 0) if tip else 0
    logger.info(f"[drep_delegators] Current epoch: {current_epoch}")

    # 2. DRep IDs
    conn = pg_connect()
    try:
        rows = pg_query(conn, "SELECT drep_id FROM drep_list ORDER BY drep_id")
        drep_ids = [r[0] for r in rows]
    except Exception as e:
        logger.error(f"[drep_delegators] Failed to load drep_list: {e}")
        conn.close()
        return 0
    drep_ids = [d for d in drep_ids if d not in SKIP_DREP_IDS]
    logger.info(f"[drep_delegators] Found {len(drep_ids)} DReps "
                f"(skipped {len(SKIP_DREP_IDS)} virtual DReps)")

    # 3. Resume points
    def resume():
        t = pg_load_tracking(conn)
        if t and t.get("current_epoch") == current_epoch and not force:
            return t.get("last_processed_pos") or 0, t.get("total_processed") or 0
        return 0, 0

    start_idx, _ = resume()
    if start_idx >= len(drep_ids):
        logger.info(f"[drep_delegators] Epoch {current_epoch} already synced. Skipping. (force={force})")
        conn.close()
        return 0

    total = 0
    errors = 0

    for i in range(start_idx, len(drep_ids)):
        if should_cancel is not None and should_cancel():
            logger.warning("[drep_delegators] Cancel requested — stopping at "
                           f"{i}/{len(drep_ids)}, progress saved.")
            break
        did = drep_ids[i]
        try:
            offset = 0
            page_size = 1000
            drep_rows = []

            while True:
                data = koios_get("drep_delegators", params={
                    "_drep_id": did,
                    "offset": offset,
                    "limit": page_size,
                })
                if not data:
                    break
                for item in data:
                    amount_lovelace = int(item.get("amount", 0))
                    script_hash = item.get("script_hash")
                    epoch_item = item.get("epoch_no", current_epoch)
                    drep_rows.append({
                        "id": gen_uuid(),
                        "drep_id": did,
                        "stake_address": item.get("stake_address"),
                        "stake_address_hex": item.get("stake_address_hex"),
                        "script_hash": script_hash,
                        "epoch_no": epoch_item,
                        "amount_lovelace": amount_lovelace,
                        "amount_ada": amount_lovelace / 1_000_000,
                        "is_current": epoch_item == current_epoch,
                        "delegation_type": "script" if script_hash else "regular",
                        "first_seen_epoch": epoch_item,
                        "last_seen_epoch": epoch_item,
                        "delegation_count": 1,
                        "is_whale": (amount_lovelace / 1_000_000) > 1_000_000,
                        "is_exchange": False,
                        "created_at": now_iso(),
                        "updated_at": now_iso(),
                    })
                if len(data) < page_size:
                    break
                offset += page_size
                time.sleep(API_DELAY)

            if drep_rows:
                pg_upsert_batch(conn, "drep_delegators", COLUMNS, drep_rows,
                                conflict_cols=CONFLICT_COLS, preserve_cols=["id"])
                total += len(drep_rows)

            # checkpoint every N dreps
            if (i + 1) % 25 == 0 or i == len(drep_ids) - 1:
                pg_save_tracking(conn, current_epoch, i + 1, did, total)
                sys.stdout.write(f"\r  [drep_delegators] {i+1}/{len(drep_ids)} DReps, Total {total}")
                sys.stdout.flush()

        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning(f"\n  Error for {did}: {e}")
            time.sleep(API_DELAY)

    sys.stdout.write("\n")
    logger.info(f"[drep_delegators] upserted: {total}, errors: {errors}")

    # 4. Finalize is_current for full pass
    pg_normalize_is_current(conn, current_epoch)
    pg_save_tracking(conn, current_epoch, len(drep_ids), drep_ids[-1] if drep_ids else None, total)

    count = pg_row_count(conn, "drep_delegators")
    logger.info(f"[drep_delegators] Row count: {count}")
    conn.close()
    return count


if __name__ == "__main__":
    check_env()
    sync_drep_delegators()