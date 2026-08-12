"""Sync DRep delegators from Koios → Neon + Supabase (dual-write, upsert).

Koios: GET /api/v1/drep_delegators?_drep_id={id} (paginated)
       GET /api/v1/tip (for current epoch)
Target: drep_delegators (flat, per-epoch snapshots)

Design (matches original Supabase edge function):
  - Upsert on (drep_id, stake_address, epoch_no) — no truncate, no data loss.
  - Cell-level checkpoint per DB in sync_drep_tracking (job_type='drep_delegators'):
    re-runs resume where they left off and are no-ops if the epoch already completed.
  - After a full pass, is_current is normalized so only rows of the current epoch
    are marked current; older epoch rows flip to false.
"""

import sys
import time

from config import TABLE_COLUMNS, API_DELAY
from helpers import (
    get_logger, check_env, koios_get, neon_connect, neon_query,
    neon_upsert_batch, neon_row_count, now_iso, gen_uuid,
    supabase_upsert_batch, supabase_row_count, supabase_select,
    supabase_update, supabase_update_raw,
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


# ── Tracking: Neon ─────────────────────────────────────────────────────

def neon_save_tracking(conn, epoch, pos, drep_id, total):
    row = neon_load_tracking(conn)
    now = now_iso()
    if row is None:
        neon_query(
            conn,
            """INSERT INTO sync_drep_tracking
               (job_type, last_processed_drep_id, last_processed_pos,
                batch_size, total_processed, last_sync_time,
                created_at, updated_at, current_epoch, last_snapshot_epoch)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (JOB_TYPE, drep_id, pos, 0, total, now, now, now, epoch, epoch),
        )
    else:
        neon_query(
            conn,
            """UPDATE sync_drep_tracking SET
               last_processed_drep_id=%s, last_processed_pos=%s,
               total_processed=%s, last_sync_time=%s, updated_at=%s,
               current_epoch=%s, last_snapshot_epoch=%s
               WHERE job_type=%s""",
            (drep_id, pos, total, now, now, epoch, epoch, JOB_TYPE),
        )


# ── Tracking: Supabase ─────────────────────────────────────────────────

def _with_retry(fn, attempts=3, delay=3.0):
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(delay)
    raise last


def sb_load_tracking():
    def _load():
        rows = supabase_select("sync_drep_tracking", columns="*",
                               filters={"job_type": JOB_TYPE})
        return rows[0] if rows else None
    return _with_retry(_load)


def neon_load_tracking(conn):
    def _load():
        col_list = ", ".join(TRACKING_COLS)
        rows = neon_query(
            conn,
            f"SELECT {col_list} FROM sync_drep_tracking WHERE job_type = %s",
            (JOB_TYPE,),
        )
        if not rows:
            return None
        return dict(zip(TRACKING_COLS, rows[0]))
    return _with_retry(_load)


def sb_save_tracking(epoch, pos, drep_id, total):
    row = sb_load_tracking()
    now = now_iso()
    payload = {
        "job_type": JOB_TYPE,
        "last_processed_drep_id": drep_id,
        "last_processed_pos": pos,
        "total_processed": total,
        "last_sync_time": now,
        "updated_at": now,
        "current_epoch": epoch,
        "last_snapshot_epoch": epoch,
    }
    if row is None:
        payload["created_at"] = now
        supabase_upsert_batch("sync_drep_tracking", TRACKING_COLS,
                              [payload], omit_cols=["id"])
    else:
        supabase_update("sync_drep_tracking", {"job_type": JOB_TYPE}, payload)


# ── is_current normalization ───────────────────────────────────────────

def neon_normalize_is_current(conn, epoch):
    neon_query(
        conn,
        """UPDATE drep_delegators
           SET is_current = (epoch_no = %s)""",
        (epoch,),
    )


def sb_normalize_is_current(epoch):
    supabase_update_raw("drep_delegators", f"epoch_no=neq.{epoch}",
                        {"is_current": False})
    supabase_update_raw("drep_delegators", f"epoch_no=eq.{epoch}",
                        {"is_current": True})


# ── Main ───────────────────────────────────────────────────────────────

def sync_drep_delegators(logger=None, force=False, should_cancel=None):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: drep_delegators (Koios → Neon + Supabase, upsert) ===")

    # 1. Current epoch
    tip = koios_get("tip")
    current_epoch = tip[0].get("epoch_no", 0) if tip else 0
    logger.info(f"[drep_delegators] Current epoch: {current_epoch}")

    # 2. DRep IDs
    conn = neon_connect()
    try:
        rows = neon_query(conn, "SELECT drep_id FROM drep_list ORDER BY drep_id")
        drep_ids = [r[0] for r in rows]
    except Exception as e:
        logger.error(f"[drep_delegators] Failed to load drep_list: {e}")
        conn.close()
        return 0
    drep_ids = [d for d in drep_ids if d not in SKIP_DREP_IDS]
    logger.info(f"[drep_delegators] Found {len(drep_ids)} DReps "
                f"(skipped {len(SKIP_DREP_IDS)} virtual DReps)")

    # 3. Resume points per DB
    def resume(dst):
        if dst == "neon":
            t = neon_load_tracking(conn)
        else:
            t = sb_load_tracking()
        if t and t.get("current_epoch") == current_epoch and not force:
            return t.get("last_processed_pos") or 0, t.get("total_processed") or 0
        return 0, 0

    neo_start, _ = resume("neon")
    sb_start, _ = resume("supabase")
    if neo_start >= len(drep_ids) and sb_start >= len(drep_ids):
        logger.info(f"[drep_delegators] Epoch {current_epoch} already synced. Skipping. (force={force})")
        conn.close()
        return 0

    total_neon = 0
    total_sb = 0
    errors = 0

    start_idx = min(neo_start, sb_start) if not force else 0
    end_idx = len(drep_ids)

    cancelled = False
    for i in range(start_idx, end_idx):
        if should_cancel is not None and should_cancel():
            logger.warning("[drep_delegators] Cancel requested — stopping at "
                           f"{i}/{end_idx}, progress saved.")
            cancelled = True
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
                # Neon upsert (keep id on conflict)
                try:
                    neon_upsert_batch(conn, "drep_delegators", COLUMNS, drep_rows,
                                      conflict_cols=CONFLICT_COLS, preserve_cols=["id"])
                    total_neon += len(drep_rows)
                except Exception as e:
                    logger.error(f"  Neon upsert error for {did}: {e}")
                # Supabase upsert (omit id → keeps existing id, DB default for new)
                try:
                    supabase_upsert_batch("drep_delegators", COLUMNS, drep_rows,
                                          conflict_cols=CONFLICT_COLS, omit_cols=["id"])
                    total_sb += len(drep_rows)
                except Exception as e:
                    logger.error(f"  Supabase upsert error for {did}: {e}")

            # checkpoint every N dreps + per-DB position bookkeeping
            if (i + 1) % 25 == 0 or i == end_idx - 1:
                if i >= neo_start:
                    neon_save_tracking(conn, current_epoch, i + 1, did, total_neon)
                if i >= sb_start:
                    sb_save_tracking(current_epoch, i + 1, did, total_sb)
                sys.stdout.write(f"\r  [drep_delegators] {i+1}/{end_idx} DReps, Neon {total_neon}, SB {total_sb}")
                sys.stdout.flush()

        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning(f"\n  Error for {did}: {e}")
            time.sleep(API_DELAY)

    sys.stdout.write("\n")
    logger.info(f"[drep_delegators] upserted Neon: {total_neon}, Supabase: {total_sb}, errors: {errors}")

    if cancelled:
        # Partial pass: keep tracking pointing at where we stopped so the
        # next run resumes. Skip is_current normalization (incomplete pass).
        completed = max(i, 0)
        last_id = drep_ids[completed - 1] if completed > 0 and drep_ids else None
        try:
            neon_save_tracking(conn, current_epoch, completed, last_id, 0)
        except Exception as e:
            logger.error(f"  Neon tracking save failed: {e}")
        try:
            sb_save_tracking(current_epoch, completed, last_id, 0)
        except Exception as e:
            logger.error(f"  Supabase tracking save failed: {e}")
        conn.close()
        logger.info(f"[drep_delegators] Cancelled — saved progress at DRep "
                    f"{completed}/{end_idx}. Run again to resume.")
        return completed

    # 4. Finalize is_current for full pass (both DBs current epoch)
    try:
        neon_normalize_is_current(conn, current_epoch)
    except Exception as e:
        logger.error(f"  Neon normalize is_current failed: {e}")
    try:
        sb_normalize_is_current(current_epoch)
    except Exception as e:
        logger.error(f"  Supabase normalize is_current failed: {e}")

    neon_save_tracking(conn, current_epoch, len(drep_ids), drep_ids[-1] if drep_ids else None, total_neon)
    sb_save_tracking(current_epoch, len(drep_ids), drep_ids[-1] if drep_ids else None, total_sb)

    count = neon_row_count(conn, "drep_delegators")
    logger.info(f"[drep_delegators] Neon row count: {count}")
    conn.close()
    try:
        sb_count = supabase_row_count("drep_delegators")
        logger.info(f"[drep_delegators] Supabase row count: {sb_count}")
    except Exception as e:
        logger.warning(f"[drep_delegators] Supabase count failed: {e}")
    return count


if __name__ == "__main__":
    check_env()
    sync_drep_delegators()