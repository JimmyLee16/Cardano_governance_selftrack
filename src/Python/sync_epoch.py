"""Sync epoch info from Koios → PostgreSQL.

Koios: GET /api/v1/tip
Updates: proposals.epoch_no, proposals.status (expired → done, in-window → active)
"""

from config import API_DELAY
from helpers import (
    get_logger, check_env, koios_get, pg_connect, pg_query, now_iso,
)
import time


def sync_epoch(logger=None):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: epoch (Koios -> PostgreSQL) ===")

    # 1. Get current epoch from Koios
    tip = koios_get("tip")
    if not tip:
        logger.error("[epoch] Failed to get tip from Koios")
        return 0

    current_epoch = tip[0].get("epoch_no", 0)
    logger.info(f"[epoch] Current epoch: {current_epoch}")

    # 2. Update PostgreSQL
    conn = pg_connect()
    try:
        with conn.cursor() as cur:
            # Update epoch_no for all proposals that don't have current epoch
            cur.execute(
                "UPDATE proposals SET epoch_no = %s WHERE epoch_no IS NULL OR epoch_no != %s",
                (current_epoch, current_epoch)
            )
            epoch_updated = cur.rowcount
            logger.info(f"[epoch] Updated epoch_no for {epoch_updated} proposals")

            # Mark expired proposals as done
            cur.execute(
                "UPDATE proposals SET status = 'done' "
                "WHERE expiration IS NOT NULL AND expiration <> '' "
                "AND expiration::integer <= %s AND (status != 'done' OR status IS NULL)",
                (current_epoch,)
            )
            status_updated = cur.rowcount
            logger.info(f"[epoch] Marked {status_updated} proposals as done (expired)")

            # Mark not-yet-expired proposals as active (in voting window)
            cur.execute(
                "UPDATE proposals SET status = 'active' "
                "WHERE expiration IS NOT NULL AND expiration <> '' "
                "AND expiration::integer > %s AND (status != 'active' OR status IS NULL)",
                (current_epoch,)
            )
            active_updated = cur.rowcount
            logger.info(f"[epoch] Marked {active_updated} proposals as active (in voting window)")

        conn.commit()
    finally:
        conn.close()

    logger.info(f"[epoch] Done! Epoch={current_epoch}")
    return current_epoch


if __name__ == "__main__":
    check_env()
    sync_epoch()