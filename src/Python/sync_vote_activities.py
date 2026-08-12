"""Sync vote activities from Koios + IPFS → PostgreSQL ga_* tables.

Koios: GET /api/v1/proposal_votes?_proposal_id={id}
IPFS: Fetch metadata for comment
Target: ga_* tables (one per proposal) in PostgreSQL
Reads proposals with activities_table_name from proposals table.
"""

import sys
import time

from config import GA_TABLE_COLUMNS, BATCH_SIZE, API_DELAY
from helpers import (
    get_logger, check_env, koios_get, fetch_ipfs_metadata,
    pg_connect, pg_upsert_batch, pg_row_count,
    now_iso, gen_uuid, pg_query,
)


def sync_vote_activities(logger=None, only_active=False):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: vote_activities (Koios+IPFS → ga_* tables) ===")

    # 1. Get proposals with activities_table_name from PostgreSQL
    conn = pg_connect()
    try:
        if only_active:
            proposals_res = pg_query(
                conn,
                "SELECT proposal_id, activities_table_name FROM proposals "
                "WHERE activities_table_name IS NOT NULL "
                "AND status IN ('voting','active') ORDER BY proposal_id"
            )
        else:
            proposals_res = pg_query(
                conn,
                "SELECT proposal_id, activities_table_name FROM proposals "
                "WHERE activities_table_name IS NOT NULL ORDER BY proposal_id"
            )
        proposals = [(r[0], r[1]) for r in proposals_res]
    finally:
        conn.close()
    # Skip test proposals
    proposals = [(pid, tbl) for pid, tbl in proposals if not pid.startswith("final_verify_v3")]

    logger.info(f"[vote_activities] Found {len(proposals)} proposals with ga_* tables")

    # 2. Process each proposal
    total_votes = 0
    errors = 0
    total_skipped = 0

    for idx, (pid, table_name) in enumerate(proposals):
        logger.info(f"\n  [{idx+1}/{len(proposals)}] {pid} → {table_name}")

        conn = pg_connect()
        try:
            # Fetch votes from Koios
            votes = koios_get("proposal_votes", params={"_proposal_id": pid})
            if not votes:
                logger.info(f"    No votes found")
                continue

            logger.info(f"    Got {len(votes)} votes from Koios")

            # Check if there are new votes (compare row count)
            count_res = pg_query(conn, f'SELECT count(*) FROM "{table_name}"')
            current_count = count_res[0][0] if count_res else 0

            # Build a set of (voter_id, block_time) that already have comments
            existing_with_comments = set()
            if current_count > 0:
                existing_res = pg_query(
                    conn,
                    f'SELECT voter_id, block_time FROM "{table_name}" '
                    f'WHERE comment IS NOT NULL AND comment != \'\''
                )
                for r in existing_res:
                    existing_with_comments.add((r[0], str(r[1])))

            if current_count == len(votes) and len(existing_with_comments) >= len(votes):
                logger.info(f"    Already up-to-date ({current_count} rows, all have comments), skipping")
                continue

            new_count = len(votes) - current_count
            if current_count < len(votes):
                logger.info(f"    {new_count} new votes to upsert (DB={current_count}, Koios={len(votes)})")
            else:
                logger.info(f"    Upserting {len(votes)} votes (DB={current_count}, Koios={len(votes)})")
            if existing_with_comments:
                logger.info(f"    {len(existing_with_comments)} votes already have comments (will skip IPFS)")

            # Process votes
            rows = []
            skipped = 0
            for v in votes:
                block_time = v.get("block_time")
                if isinstance(block_time, (int, float)):
                    bt_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(block_time))
                else:
                    bt_iso = str(block_time)

                voter_id = v.get("voter_id")
                meta_url = v.get("meta_url")

                # Skip IPFS fetch if vote already has comment in DB
                if (voter_id, bt_iso) in existing_with_comments:
                    skipped += 1
                    continue

                # Fetch IPFS metadata for comment
                comment = ""
                if meta_url:
                    comment = fetch_ipfs_metadata(meta_url, voter_role=v.get("voter_role"))

                row = {
                    "id": gen_uuid(),
                    "block_time": bt_iso,
                    "voter_role": v.get("voter_role"),
                    "voter_id": voter_id,
                    "vote": v.get("vote"),
                    "meta_url": meta_url,
                    "comment": comment,
                    "processed_at": now_iso(),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                }
                rows.append(row)

            # Insert in batches
            inserted = 0
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                try:
                    batch_cols = [c for c in GA_TABLE_COLUMNS if all(c in row for row in batch)]
                    count = pg_upsert_batch(
                        conn, table_name, batch_cols, batch,
                        conflict_cols=["voter_id", "block_time"]
                    )
                    inserted += count
                except Exception as e:
                    logger.error(f"    Insert error at batch {i}: {e}")

            total_votes += inserted
            total_skipped += skipped
            logger.info(f"    Inserted {inserted}/{len(rows)}, skipped {skipped}")

        except Exception as e:
            errors += 1
            logger.error(f"    Error: {e}")
        finally:
            conn.close()

        time.sleep(API_DELAY)

    logger.info(f"\n[vote_activities] Total votes inserted: {total_votes}, skipped: {total_skipped}, errors: {errors}")
    return total_votes


if __name__ == "__main__":
    check_env()
    only_active = "--active-only" in sys.argv
    sync_vote_activities(only_active=only_active)