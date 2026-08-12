"""Sync vote activities from Koios + IPFS → Neon + Supabase ga_* tables (dual-write).

Koios: GET /api/v1/proposal_votes?_proposal_id={id}
IPFS: Fetch metadata for comment
Target: ga_* tables (one per proposal) in both Neon and Supabase
Reads proposals with activities_table_name from Neon proposals table.
"""

import sys
import time

from config import GA_TABLE_COLUMNS, BATCH_SIZE, API_DELAY
from helpers import (
    get_logger, check_env, koios_get, fetch_ipfs_metadata,
    neon_connect, neon_truncate, neon_upsert_batch, neon_row_count,
    now_iso, gen_uuid,
    supabase_upsert_batch, supabase_table_exists, supabase_select,
)


def sync_vote_activities(logger=None, only_active=False):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: vote_activities (Koios+IPFS → ga_* tables) ===")

    # 1. Get proposals with activities_table_name from Neon
    conn = neon_connect()
    with conn.cursor() as cur:
        if only_active:
            cur.execute(
                "SELECT proposal_id, activities_table_name FROM proposals "
                "WHERE activities_table_name IS NOT NULL "
                "AND status IN ('voting','active') ORDER BY proposal_id"
            )
        else:
            cur.execute(
                "SELECT proposal_id, activities_table_name FROM proposals "
                "WHERE activities_table_name IS NOT NULL ORDER BY proposal_id"
            )
        proposals = [(r[0], r[1]) for r in cur.fetchall()]
    # Skip test proposals
    proposals = [(pid, tbl) for pid, tbl in proposals if not pid.startswith("final_verify_v3")]

    logger.info(f"[vote_activities] Found {len(proposals)} proposals with ga_* tables")

    # 2. Process each proposal
    total_votes = 0
    errors = 0
    total_skipped = 0

    for idx, (pid, table_name) in enumerate(proposals):
        logger.info(f"\n  [{idx+1}/{len(proposals)}] {pid} → {table_name}")

        # Get Supabase activities_table_name (may differ from Neon's)
        sb_table_name = None
        try:
            sb_rows = supabase_select("proposals", columns="activities_table_name",
                                       filters={"proposal_id": pid})
            if sb_rows:
                sb_table_name = sb_rows[0].get("activities_table_name")
        except Exception as e:
            logger.warning(f"    Could not fetch activities_table_name from Supabase: {e}")

        if sb_table_name and sb_table_name != table_name:
            logger.info(f"    Supabase table name differs: {sb_table_name} (Neon: {table_name})")
        elif not sb_table_name:
            sb_table_name = table_name  # fallback to Neon's
            logger.info(f"    Supabase has no activities_table_name, using Neon's: {table_name}")

        try:
            # Fetch votes from Koios
            votes = koios_get("proposal_votes", params={"_proposal_id": pid})
            if not votes:
                logger.info(f"    No votes found")
                continue

            logger.info(f"    Got {len(votes)} votes from Koios")

            # Check if there are new votes (compare row count)
            with conn.cursor() as cur:
                cur.execute(f'SELECT count(*) FROM "{table_name}"')
                current_count = cur.fetchone()[0]

            # Build a set of (voter_id, block_time) that already have comments
            existing_with_comments = set()
            if current_count > 0:
                with conn.cursor() as cur:
                    cur.execute(
                        f'SELECT voter_id, block_time FROM "{table_name}" '
                        f'WHERE comment IS NOT NULL AND comment != \'\''
                    )
                    for r in cur.fetchall():
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
            sb_inserted = 0
            # Check if ga_* table exists in Supabase (cache per proposal)
            sb_table_exists = supabase_table_exists(sb_table_name)
            if not sb_table_exists:
                logger.info(f"    Supabase: table {sb_table_name} does not exist, skipping SB write")
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                try:
                    # Use only columns that are present in all rows of this batch
                    batch_cols = [c for c in GA_TABLE_COLUMNS if all(c in row for row in batch)]
                    count = neon_upsert_batch(
                        conn, table_name, batch_cols, batch,
                        conflict_cols=["voter_id", "block_time"]
                    )
                    inserted += count
                except Exception as e:
                    logger.error(f"    Neon insert error at batch {i}: {e}")
                # Supabase insert (only if table exists)
                if sb_table_exists:
                    try:
                        batch_cols = [c for c in GA_TABLE_COLUMNS if all(c in row for row in batch)]
                        sb_inserted += supabase_upsert_batch(
                            sb_table_name, batch_cols, batch,
                            conflict_cols=["voter_id", "block_time"]
                        )
                    except Exception as e:
                        logger.error(f"    Supabase insert error at batch {i}: {e}")

            total_votes += inserted
            total_skipped += skipped
            logger.info(f"    Inserted {inserted}/{len(rows)} (Neon), {sb_inserted} (Supabase), skipped {skipped}")

        except Exception as e:
            errors += 1
            logger.error(f"    Error: {e}")

        time.sleep(API_DELAY)

    logger.info(f"\n[vote_activities] Total votes inserted: {total_votes}, skipped: {total_skipped}, errors: {errors}")
    conn.close()
    return total_votes


if __name__ == "__main__":
    check_env()
    only_active = "--active-only" in sys.argv
    sync_vote_activities(only_active=only_active)
