"""Sync epoch info from Koios → Neon + Supabase (dual-write).

Koios: GET /api/v1/tip
Updates: proposals.epoch_no, proposals.status (in-window → active, expired → done)
"""

from config import API_DELAY
from helpers import (
    get_logger, check_env, koios_get, neon_connect, now_iso,
    supabase_update,
)
import time


def sync_epoch(logger=None):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: epoch (Koios -> Neon + Supabase) ===")

    # 1. Get current epoch from Koios
    tip = koios_get("tip")
    if not tip:
        logger.error("[epoch] Failed to get tip from Koios")
        return 0

    current_epoch = tip[0].get("epoch_no", 0)
    logger.info(f"[epoch] Current epoch: {current_epoch}")

    # 2. Update Neon
    conn = neon_connect()
    with conn.cursor() as cur:
        # Update epoch_no for all proposals that don't have current epoch
        cur.execute(
            "UPDATE proposals SET epoch_no = %s WHERE epoch_no IS NULL OR epoch_no != %s",
            (current_epoch, current_epoch)
        )
        epoch_updated = cur.rowcount
        logger.info(f"[epoch] Neon: Updated epoch_no for {epoch_updated} proposals")

        # Mark expired proposals as done
        cur.execute(
            "UPDATE proposals SET status = 'done' "
            "WHERE expiration::integer <= %s AND (status != 'done' OR status IS NULL)",
            (current_epoch,)
        )
        status_updated = cur.rowcount
        logger.info(f"[epoch] Neon: Marked {status_updated} proposals as done (expired)")

        # Mark not-yet-expired proposals as active (in voting window)
        cur.execute(
            "UPDATE proposals SET status = 'active' "
            "WHERE expiration IS NOT NULL AND expiration <> '' "
            "AND expiration::integer > %s AND (status != 'active' OR status IS NULL)",
            (current_epoch,)
        )
        active_updated = cur.rowcount
        logger.info(f"[epoch] Neon: Marked {active_updated} proposals as active (in voting window)")

    conn.commit()
    conn.close()

    # 3. Update Supabase (epoch_no for stale rows, status for expired)
    try:
        from helpers import supabase_select
        # epoch_no: fetch rows where epoch_no is null OR != current_epoch
        # PostgREST or filter: ?or=(epoch_no.is.null,epoch_no.neq.646)
        stale_rows = supabase_select(
            "proposals", "proposal_id",
            limit=10000
        )
        # Filter client-side (simpler than complex PostgREST or-filter)
        stale_ids = []
        all_rows = supabase_select("proposals", "proposal_id,epoch_no", limit=10000)
        for row in all_rows:
            en = row.get("epoch_no")
            if en is None or int(en) != current_epoch:
                stale_ids.append(row["proposal_id"])

        sb_epoch_updated = 0
        for pid in stale_ids:
            try:
                supabase_update("proposals", {"proposal_id": pid}, {"epoch_no": current_epoch})
                sb_epoch_updated += 1
            except Exception as e:
                logger.warning(f"[epoch] Supabase: Failed epoch_no for {pid[:40]}: {e}")
        logger.info(f"[epoch] Supabase: Updated epoch_no for {sb_epoch_updated}/{len(stale_ids)} proposals")

        # status: fetch all and filter expired
        rows = supabase_select("proposals", "proposal_id,expiration,status", limit=10000)
        expired_ids = []
        for row in rows:
            exp = row.get("expiration")
            status = row.get("status")
            if exp is None or status == "done":
                continue
            try:
                if int(exp) <= current_epoch:
                    expired_ids.append(row["proposal_id"])
            except (ValueError, TypeError):
                continue

        sb_status_updated = 0
        for pid in expired_ids:
            try:
                supabase_update("proposals", {"proposal_id": pid}, {"status": "done"})
                sb_status_updated += 1
            except Exception as e:
                logger.warning(f"[epoch] Supabase: Failed status for {pid[:40]}: {e}")

        logger.info(f"[epoch] Supabase: Marked {sb_status_updated}/{len(expired_ids)} proposals as done (expired)")

        # status: mark not-yet-expired proposals as active (in voting window)
        active_ids = []
        for row in rows:
            exp = row.get("expiration")
            status = row.get("status")
            if exp is None or status == "done" or status == "active":
                continue
            try:
                if int(exp) > current_epoch:
                    active_ids.append(row["proposal_id"])
            except (ValueError, TypeError):
                continue

        sb_active_updated = 0
        for pid in active_ids:
            try:
                supabase_update("proposals", {"proposal_id": pid}, {"status": "active"})
                sb_active_updated += 1
            except Exception as e:
                logger.warning(f"[epoch] Supabase: Failed active status for {pid[:40]}: {e}")

        logger.info(f"[epoch] Supabase: Marked {sb_active_updated}/{len(active_ids)} proposals as active (in voting window)")
    except Exception as e:
        logger.error(f"[epoch] Supabase update failed: {e}")

    logger.info(f"[epoch] Done! Epoch={current_epoch}")
    return current_epoch


if __name__ == "__main__":
    check_env()
    sync_epoch()
