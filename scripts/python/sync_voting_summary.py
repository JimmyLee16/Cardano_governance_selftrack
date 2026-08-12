"""Sync voting summary from Koios → Neon + Supabase (dual-write).

Koios: GET /api/v1/proposal_voting_summary?_proposal_id={id}
Target: proposal_voting_summary table
Reads proposal_ids from Neon proposals table.
"""

import sys
import time

from config import TABLE_COLUMNS, BATCH_SIZE, API_DELAY
from helpers import (
    get_logger, check_env, koios_get, neon_connect,
    neon_truncate, neon_upsert_batch, neon_row_count, now_iso, gen_uuid,
    supabase_upsert_batch, supabase_row_count,
)


def sync_voting_summary(logger=None):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: proposal_voting_summary (Koios → Neon) ===")
    columns = TABLE_COLUMNS["proposal_voting_summary"]

    # 1. Get active proposal IDs from Neon
    conn = neon_connect()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT proposal_id FROM proposals "
            "WHERE status IN ('voting','active') ORDER BY proposal_id"
        )
        proposal_ids = [r[0] for r in cur.fetchall()]
    # Skip test proposals
    proposal_ids = [pid for pid in proposal_ids if not pid.startswith("final_verify_v3")]
    logger.info(f"[voting_summary] Found {len(proposal_ids)} active proposals")

    # 2. Upsert (no truncate)
    conn = neon_connect()

    # 3. Fetch voting summary for each proposal
    all_rows = []
    errors = 0

    for i, pid in enumerate(proposal_ids):
        try:
            data = koios_get("proposal_voting_summary", params={"_proposal_id": pid})
            if not data or not isinstance(data, list) or len(data) == 0:
                continue

            d = data[0]
            all_rows.append({
                "id": gen_uuid(),
                "proposal_id": pid,
                "proposal_type": d.get("proposal_type"),
                "epoch_no": d.get("epoch_no"),
                "drep_yes_votes_cast": d.get("drep_yes_votes_cast", 0),
                "drep_active_yes_vote_power": d.get("drep_active_yes_vote_power", 0),
                "drep_yes_vote_power": d.get("drep_yes_vote_power", 0),
                "drep_yes_pct": d.get("drep_yes_pct", 0),
                "drep_no_votes_cast": d.get("drep_no_votes_cast", 0),
                "drep_active_no_vote_power": d.get("drep_active_no_vote_power", 0),
                "drep_no_vote_power": d.get("drep_no_vote_power", 0),
                "drep_no_pct": d.get("drep_no_pct", 0),
                "drep_abstain_votes_cast": d.get("drep_abstain_votes_cast", 0),
                "drep_active_abstain_vote_power": d.get("drep_active_abstain_vote_power", 0),
                "drep_abstain_vote_power": d.get("drep_abstain_vote_power", 0),
                "drep_always_abstain_vote_power": d.get("drep_always_abstain_vote_power", 0),
                "drep_always_no_confidence_vote_power": d.get("drep_always_no_confidence_vote_power", 0),
                "pool_yes_votes_cast": d.get("pool_yes_votes_cast", 0),
                "pool_active_yes_vote_power": d.get("pool_active_yes_vote_power", 0),
                "pool_yes_vote_power": d.get("pool_yes_vote_power", 0),
                "pool_yes_pct": d.get("pool_yes_pct", 0),
                "pool_no_votes_cast": d.get("pool_no_votes_cast", 0),
                "pool_active_no_vote_power": d.get("pool_active_no_vote_power", 0),
                "pool_no_vote_power": d.get("pool_no_vote_power", 0),
                "pool_no_pct": d.get("pool_no_pct", 0),
                "pool_abstain_votes_cast": d.get("pool_abstain_votes_cast", 0),
                "pool_active_abstain_vote_power": d.get("pool_active_abstain_vote_power", 0),
                "pool_passive_always_abstain_votes_assigned": d.get("pool_passive_always_abstain_votes_assigned", 0),
                "pool_passive_always_abstain_vote_power": d.get("pool_passive_always_abstain_vote_power", 0),
                "pool_passive_always_no_confidence_votes_assigned": d.get("pool_passive_always_no_confidence_votes_assigned", 0),
                "pool_passive_always_no_confidence_vote_power": d.get("pool_passive_always_no_confidence_vote_power", 0),
                "committee_yes_votes_cast": d.get("committee_yes_votes_cast", 0),
                "committee_yes_pct": d.get("committee_yes_pct", 0),
                "committee_no_votes_cast": d.get("committee_no_votes_cast", 0),
                "committee_no_pct": d.get("committee_no_pct", 0),
                "committee_abstain_votes_cast": d.get("committee_abstain_votes_cast", 0),
                "data_fetched_at": now_iso(),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })

            # Insert in batches
            if len(all_rows) >= BATCH_SIZE:
                try:
                    neon_upsert_batch(conn, "proposal_voting_summary", columns, all_rows, conflict_cols=["proposal_id"], preserve_cols=("id", "created_at"))
                except Exception as e:
                    logger.error(f"[voting_summary] Neon insert error: {e}")
                try:
                    supabase_upsert_batch("proposal_voting_summary", columns, all_rows, conflict_cols=["proposal_id"], omit_cols=("id",))
                except Exception as e:
                    logger.error(f"[voting_summary] Supabase insert error: {e}")
                all_rows = []

        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning(f"[voting_summary] Error for {pid}: {e}")

        if (i + 1) % 10 == 0 or i == len(proposal_ids) - 1:
            sys.stdout.write(f"\r  [voting_summary] {i+1}/{len(proposal_ids)}, errors={errors}")
            sys.stdout.flush()
        time.sleep(API_DELAY)

    # Insert remaining
    if all_rows:
        try:
            neon_upsert_batch(conn, "proposal_voting_summary", columns, all_rows, conflict_cols=["proposal_id"], preserve_cols=("id", "created_at"))
        except Exception as e:
            logger.error(f"[voting_summary] Neon final insert error: {e}")
        try:
            supabase_upsert_batch("proposal_voting_summary", columns, all_rows, conflict_cols=["proposal_id"], omit_cols=("id",))
        except Exception as e:
            logger.error(f"[voting_summary] Supabase final insert error: {e}")

    logger.info(f"\n[voting_summary] Done, errors={errors}")
    count = neon_row_count(conn, "proposal_voting_summary")
    logger.info(f"[voting_summary] Neon row count: {count}")
    conn.close()
    try:
        sb_count = supabase_row_count("proposal_voting_summary")
        logger.info(f"[voting_summary] Supabase row count: {sb_count}")
    except Exception as e:
        logger.warning(f"[voting_summary] Supabase count failed: {e}")
    return count


if __name__ == "__main__":
    check_env()
    sync_voting_summary()
