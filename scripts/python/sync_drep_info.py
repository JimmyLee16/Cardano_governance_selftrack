"""Sync DRep info from Blockfrost → Neon + Supabase (dual-write, incremental).

Blockfrost: GET /api/v0/governance/dreps/{id} + /metadata
Target: drep_info table
Reads drep_id list from Neon drep_list table.

Progress is checkpointed to a local JSON file (per epoch), so each run only
processes `dreps_per_run` (default 50) DReps instead of all ~2000 every time.
"""

import sys
import time

from config import TABLE_COLUMNS, BATCH_SIZE, API_DELAY
from helpers import (
    get_logger, check_env, blockfrost_get, koios_get, neon_connect,
    neon_upsert_batch, neon_row_count, now_iso, gen_uuid,
    supabase_upsert_batch, supabase_row_count,
)
from drep_info_checkpoint import load as load_checkpoint, mark_done, save as save_ckpt

# DReps processed per run, so a single GUI click stays quick.
DREPS_PER_RUN = 50

# Rows accumulated before a neon/supabase bulk upsert.
CHUNKED_BATCH = BATCH_SIZE


def _flush(upsert_neon, upsert_sb, batch_rows, logger):
    """Upsert a batch to both DBs (best effort). Returns None."""
    try:
        upsert_neon(batch_rows)
    except Exception as e:
        logger.error(f"[drep_info] Neon insert error: {e}")
    try:
        upsert_sb(batch_rows)
    except Exception as e:
        logger.error(f"[drep_info] Supabase insert error: {e}")


def sync_drep_info(logger=None, dreps_per_run=DREPS_PER_RUN, should_cancel=None):
    if logger is None:
        logger = get_logger()

    logger.info("=== Sync: drep_info (Blockfrost → Neon, incremental) ===")
    columns = TABLE_COLUMNS["drep_info"]

    # 1. Current epoch resets the checkpoint: the full set is re-synced once
    #    per epoch. Metadata changes very rarely, so this is clean.
    try:
        tip = koios_get("tip")
        current_epoch = tip[0].get("epoch_no", 0) if tip else 0
    except Exception as e:
        logger.warning(f"[drep_info] Failed to fetch tip, assuming epoch 0: {e}")
        current_epoch = 0

    # 2. Load checkpoint + full drep_id list from Neon drep_list.
    conn = neon_connect()
    with conn.cursor() as cur:
        cur.execute("SELECT drep_id FROM drep_list ORDER BY drep_id")
        drep_ids = [r[0] for r in cur.fetchall()]
    conn.close()

    ckpt = load_checkpoint(current_epoch)
    done = set(ckpt["processed"])
    todo = [d for d in drep_ids if d not in done]
    slice_todo = todo[:dreps_per_run]
    remaining_after = len(todo) - len(slice_todo)

    logger.info(f"[drep_info] epoch={current_epoch} total={len(drep_ids)} "
                f"already_done={len(done)} processing={len(slice_todo)} "
                f"remaining={remaining_after}")
    if not slice_todo:
        logger.info("[drep_info] All DReps already synced for this epoch.")
        save_ckpt(ckpt)
        return 0

    # 3. Fresh connection per flush: Neon PgBouncer (transaction pooling)
    #    closes idle connections mid-run.
    def upsert_neon(batch_rows):
        for attempt in range(3):
            c = None
            try:
                c = neon_connect()
                neon_upsert_batch(c, "drep_info", columns, batch_rows,
                                  conflict_cols=["drep_id"])
                return
            except Exception as e:
                if attempt == 2:
                    raise
                logger.warning(f"[drep_info] Neon retry {attempt + 1}: {e}")
                time.sleep(2 * (attempt + 1))
            finally:
                if c is not None:
                    try:
                        c.close()
                    except Exception:
                        pass

    def upsert_sb(batch_rows):
        supabase_upsert_batch("drep_info", columns, batch_rows,
                              conflict_cols=["drep_id"])

    # 4. Fetch + build rows for this run's slice, flush in chunks.
    all_rows = []
    processed_now = 0
    errors = 0

    for i, did in enumerate(slice_todo):
        if should_cancel is not None and should_cancel():
            logger.warning(f"[drep_info] Cancel requested — flushing "
                           f"{len(all_rows)} rows and saving progress.")
            break
        try:
            info = blockfrost_get(f"governance/dreps/{did}")
            try:
                meta = blockfrost_get(f"governance/dreps/{did}/metadata")
            except Exception:
                meta = {}

            body = (meta.get("json_metadata") or {}).get("body") or {}

            def normalize(val):
                if isinstance(val, dict):
                    return val.get("@value") or val.get("contentUrl")
                return val

            # Extract https URIs from references
            uris = []
            refs = body.get("references") or []
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, dict) and isinstance(ref.get("uri"), str):
                        if ref["uri"].startswith("https://"):
                            uris.append(ref["uri"])
            elif isinstance(refs, dict):
                uri = refs.get("uri")
                if isinstance(uri, str) and uri.startswith("https://"):
                    uris.append(uri)

            # Amount: lovelace → ADA
            amount_raw = info.get("amount", "0")
            try:
                amount_ada = round(int(amount_raw) * 1e-6, 2)
            except (ValueError, TypeError):
                amount_ada = 0

            row = {
                "id": gen_uuid(),
                "drep_id": did,
                "amount": amount_ada,
                "active_epoch": info.get("active_epoch"),
                "last_active_epoch": info.get("last_active_epoch"),
                "url": meta.get("url"),
                "payment_address": normalize(body.get("paymentAddress")),
                "given_name": normalize(body.get("givenName")),
                "content_url": None,
                "https_uris": ", ".join(uris) or None,
                "metadata_fetched_at": now_iso(),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }

            # Extract content_url from image
            img = body.get("image")
            if isinstance(img, dict):
                row["content_url"] = img.get("contentUrl") or img.get("@value")
            elif isinstance(img, str):
                row["content_url"] = img

            all_rows.append(row)
            processed_now += 1

        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning(f"[drep_info] Error for {did}: {e}")

        # Flush when chunk full, then persist checkpoint.
        if len(all_rows) >= CHUNKED_BATCH:
            _flush(upsert_neon, upsert_sb, all_rows, logger)
            mark_done(ckpt, [r["drep_id"] for r in all_rows])
            all_rows = []
            sys.stdout.write(f"\r  [drep_info] {i+1}/{len(slice_todo)} "
                             f"(-{remaining_after} left)")
            sys.stdout.flush()

        time.sleep(API_DELAY)

    # Flush remainder
    if all_rows:
        _flush(upsert_neon, upsert_sb, all_rows, logger)
        mark_done(ckpt, [r["drep_id"] for r in all_rows])

    logger.info(f"\n[drep_info] Processed {processed_now} this run. "
                f"Remaining {remaining_after} in this epoch.")
    save_ckpt(ckpt)

    # Verify
    count = -1
    c = None
    try:
        c = neon_connect()
        count = neon_row_count(c, "drep_info")
        logger.info(f"[drep_info] Neon row count: {count}")
    except Exception as e:
        logger.warning(f"[drep_info] Neon count failed: {e}")
    finally:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
    try:
        sb_count = supabase_row_count("drep_info")
        logger.info(f"[drep_info] Supabase row count: {sb_count}")
    except Exception as e:
        logger.warning(f"[drep_info] Supabase count failed: {e}")
    return count


if __name__ == "__main__":
    check_env()
    sync_drep_info()