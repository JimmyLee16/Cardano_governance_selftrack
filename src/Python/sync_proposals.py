"""Sync proposals from Koios → PostgreSQL.

Koios: GET /api/v1/proposal_list
Target: proposals table
"""

import sys
import time

from config import TABLE_COLUMNS, BATCH_SIZE, PROPOSAL_TRIGGERS
from helpers import (
    get_logger, check_env, koios_get, pg_connect, pg_upsert_batch,
    pg_row_count, now_iso, gen_uuid, pg_ensure_proposal_activities_table,
    pg_drop_triggers, pg_recreate_proposal_triggers, pg_query,
)


def sync_proposals(logger=None):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: proposals (Koios → PostgreSQL) ===")
    columns = TABLE_COLUMNS["proposals"]

    # 1. Fetch from Koios
    logger.info("[proposals] Fetching from Koios...")
    raw = koios_get("proposal_list")
    logger.info(f"[proposals] Got {len(raw)} proposals from Koios")

    # 2. Transform
    rows = []
    seen_ids = set()
    for p in raw:
        pid = p.get("proposal_id")
        if not pid or pid in seen_ids:
            continue
        seen_ids.add(pid)

        body = (p.get("meta_json") or {}).get("body") or {}

        # Combine abstract, rationale, motivation
        abstract_parts = []
        if body.get("abstract"):
            abstract_parts.append(body["abstract"])
        if body.get("rationale"):
            abstract_parts.append(f"RATIONALE:\n{body['rationale']}")
        if body.get("motivation"):
            abstract_parts.append(f"MOTIVATION:\n{body['motivation']}")

        refs = body.get("references") or []
        first_uri = refs[0].get("uri") if refs and isinstance(refs, list) else None
        authors = (p.get("meta_json") or {}).get("authors") or []
        author_name = authors[0].get("name") if authors else None

        rows.append({
            "id": gen_uuid(),
            "proposal_id": pid,
            "title": body.get("title") or pid,
            "abstract": "\n\n".join(abstract_parts) or None,
            "first_reference_uri": first_uri,
            "author_name": author_name,
            "proposal_index": p.get("proposal_index"),
            "proposal_tx_hash": p.get("proposal_tx_hash"),
            "proposed_epoch": p.get("proposed_epoch"),
            "expiration": p.get("expiration"),
            "proposal_type": p.get("proposal_type"),
            "epoch_no": None,
            "status": None,
            "data_fetched_at": now_iso(),
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "activities_table_created": False,
            "activities_table_name": None,
            "abstract_summary": (body.get("abstract") or "")[:500] or None,
            "slug": None,
        })

    logger.info(f"[proposals] Transformed {len(rows)} rows")

    # 3. Connect
    conn = pg_connect()

    # 4. Find existing proposal_ids
    existing_res = pg_query(conn, "SELECT proposal_id FROM proposals")
    existing_ids = {r[0] for r in existing_res}

    # 5. Split new vs existing
    new_rows = [row for row in rows if row["proposal_id"] not in existing_ids]
    existing_rows = [row for row in rows if row["proposal_id"] in existing_ids]
    logger.info(f"[proposals] {len(new_rows)} new to insert, {len(existing_rows)} existing to update")

    # 6. Drop triggers before insert to prevent orphan ga_* tables
    triggers_dropped = False
    if new_rows:
        logger.info(f"[proposals] Dropping triggers before insert ({len(new_rows)} new)...")
        pg_drop_triggers(conn, "proposals", PROPOSAL_TRIGGERS)
        triggers_dropped = True

    # 7. Insert new proposals (no trigger = no orphan ga_* tables)
    inserted = 0
    for i in range(0, len(new_rows), BATCH_SIZE):
        batch = new_rows[i:i + BATCH_SIZE]
        try:
            count = pg_upsert_batch(
                conn, "proposals", columns, batch,
                conflict_cols=["proposal_id"], do_update=False
            )
            inserted += count
        except Exception as e:
            logger.error(f"[proposals] Error at batch {i}: {e}")
        pct = min(100, (i + len(batch)) * 100 // len(new_rows)) if new_rows else 100
        sys.stdout.write(f"\r  [proposals] Insert {pct}% (PostgreSQL={inserted})")
        sys.stdout.flush()
    logger.info(f"\n[proposals] Inserted {inserted}/{len(new_rows)} new")

    # 8. Update existing proposals (UPDATE, not INSERT → no trigger → no orphan ga_* tables)
    #    Note: do NOT update status — it is managed by sync_epoch (active vs done)
    update_fields = [
        "title", "abstract", "first_reference_uri", "author_name",
        "proposal_index", "proposal_tx_hash", "proposed_epoch", "expiration",
        "proposal_type", "data_fetched_at", "updated_at", "abstract_summary",
    ]
    updated = 0
    for i, row in enumerate(existing_rows):
        try:
            with conn.cursor() as cur:
                set_clause = ", ".join(f"{c} = %s" for c in update_fields)
                values = [row.get(c) for c in update_fields]
                cur.execute(
                    f"UPDATE proposals SET {set_clause} WHERE proposal_id = %s",
                    values + [row["proposal_id"]]
                )
                updated += 1
        except Exception as e:
            logger.error(f"[proposals] Update error for {row['proposal_id']}: {e}")
        if (i + 1) % 25 == 0 or i == len(existing_rows) - 1:
            sys.stdout.write(f"\r  [proposals] Update {i+1}/{len(existing_rows)} (PostgreSQL={updated})")
            sys.stdout.flush()
    logger.info(f"\n[proposals] Updated {updated}/{len(existing_rows)}")

    # 9. Recreate triggers for real-time inserts from the app (only if dropped)
    if triggers_dropped:
        logger.info("[proposals] Recreating triggers...")
        pg_recreate_proposal_triggers(conn, "proposals")
    else:
        logger.info("[proposals] Triggers untouched (no inserts)")

    # 10. Ensure ga_* tables exist for proposals missing them
    logger.info("[proposals] Ensuring ga_* tables for proposals missing them...")
    missing_res = pg_query(
        conn,
        "SELECT proposal_id FROM proposals "
        "WHERE activities_table_name IS NULL OR activities_table_created = FALSE"
    )
    missing = [r[0] for r in missing_res]

    created = 0
    for idx, pid in enumerate(missing):
        try:
            pg_ensure_proposal_activities_table(conn, pid)
            created += 1
        except Exception as e:
            logger.error(f"[proposals] Failed to create ga_* table for {pid}: {e}")
        sys.stdout.write(f"\r  [proposals] tables {idx+1}/{len(missing)} created={created}")
        sys.stdout.flush()
    logger.info(f"\n[proposals] Created {created}/{len(missing)} ga_* tables")

    # 11. Verify
    count = pg_row_count(conn, "proposals")
    logger.info(f"[proposals] Row count: {count}")
    conn.close()
    return count


if __name__ == "__main__":
    check_env()
    sync_proposals()