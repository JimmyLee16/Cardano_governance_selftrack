"""Helpers: Koios/Blockfrost/IPFS fetch, PostgreSQL insert, retry, logging.
Generic PostgreSQL - works with any provider (Railway, Render, local, Docker, etc.)
"""

import hashlib
import os
import re
import sys
import time
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows cp1252 console encoding for Unicode (arrows, etc.)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

from config import (
    KOIOS_BASE, BLOCKFROST_BASE, BLOCKFROST_KEY, IPFS_GATEWAY,
    DATABASE_URL, MAX_RETRIES, RETRY_DELAY, API_DELAY,
)

# ── Logging ────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name="cardano_gov_sync"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)
    log_file = LOG_DIR / f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    return logger


def check_env():
    missing = []
    if not DATABASE_URL:
        missing.append("DATABASE_URL")
    if not BLOCKFROST_KEY:
        missing.append("BLOCKFROST_PROJECT_ID")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)


# ── HTTP fetch with retry ──────────────────────────────────────────

def fetch_json(url, headers=None, params=None, retries=5):
    """Fetch JSON from URL with retry logic."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=60)
            if resp.status_code == 429:
                # Rate limited - wait longer each time
                wait = int(resp.headers.get("Retry-After", 10 * (attempt + 1)))
                time.sleep(max(wait, 10 * (attempt + 1)))
                continue
            if resp.status_code >= 500:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(RETRY_DELAY * (attempt + 1))
    raise Exception(f"Failed after {retries} retries: {url}")


# ── Koios API ──────────────────────────────────────────────────────

def koios_get(endpoint, params=None):
    """GET request to Koios API."""
    url = f"{KOIOS_BASE}/{endpoint}"
    return fetch_json(url, headers={"Accept": "application/json"}, params=params)


def koios_post(endpoint, body=None):
    """POST request to Koios API (for batch endpoints)."""
    url = f"{KOIOS_BASE}/{endpoint}"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(url, json=body or {}, headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=120)
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * 2)
                continue
            if resp.status_code >= 500:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_DELAY * (attempt + 1))
    raise Exception(f"Failed after {MAX_RETRIES} retries: {url}")


# ── Blockfrost API ─────────────────────────────────────────────────

def blockfrost_get(endpoint, params=None):
    """GET request to Blockfrost API."""
    url = f"{BLOCKFROST_BASE}/{endpoint}"
    headers = {"project_id": BLOCKFROST_KEY}
    return fetch_json(url, headers=headers, params=params)


def blockfrost_get_all_pages(endpoint, count=100, max_pages=100):
    """Paginate through all Blockfrost results."""
    all_results = []
    for page in range(1, max_pages + 1):
        data = blockfrost_get(endpoint, params={"page": page, "count": count})
        if not data:
            break
        all_results.extend(data)
        if len(data) < count:
            break
        time.sleep(API_DELAY)
    return all_results


# ── IPFS ───────────────────────────────────────────────────────────

def fetch_ipfs_metadata(meta_url, gateway=None, voter_role=None):
    """Fetch metadata from IPFS gateway.
    If voter_role is 'ConstitutionalCommittee', returns full metadata JSON string.
    Otherwise extracts comment from body.comment, body.rationale, root comment, or root rationale.
    """
    if not meta_url:
        return ""
    gw = gateway or IPFS_GATEWAY
    if meta_url.startswith("ipfs://"):
        meta_url = meta_url.replace("ipfs://", "")
    if not meta_url.startswith("http"):
        meta_url = gw + meta_url
    try:
        data = fetch_json(meta_url)

        if voter_role == "ConstitutionalCommittee":
            return json.dumps(data) if isinstance(data, dict) else str(data)

        if isinstance(data, dict):
            body = data.get("body", data)
            if isinstance(body, dict):
                comment = body.get("comment") or body.get("rationale") or ""
                if comment:
                    return comment if isinstance(comment, str) else str(comment)
            if data.get("comment"):
                comment = data["comment"]
                return comment if isinstance(comment, str) else str(comment)
            if data.get("rationale"):
                comment = data["rationale"]
                return comment if isinstance(comment, str) else str(comment)
            return str(data)
        return str(data)
    except Exception:
        return ""


# ── PostgreSQL ─────────────────────────────────────────────────────

def pg_connect():
    """Connect to PostgreSQL using DATABASE_URL."""
    return psycopg2.connect(DATABASE_URL)


def pg_truncate(conn, table):
    with conn.cursor() as cur:
        cur.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(sql.Identifier(table)))
    conn.commit()


def pg_drop_triggers(conn, table, trigger_names):
    with conn.cursor() as cur:
        for tg in trigger_names:
            cur.execute(sql.SQL("DROP TRIGGER IF EXISTS {} ON {}").format(sql.Identifier(tg), sql.Identifier(table)))
    conn.commit()


def pg_recreate_proposal_triggers(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE TRIGGER {} BEFORE INSERT ON {} FOR EACH ROW EXECUTE FUNCTION create_proposal_activities_table()").format(
                sql.Identifier("trg_create_proposal_activities_table"),
                sql.Identifier(table),
            )
        )
        cur.execute(
            sql.SQL("CREATE TRIGGER {} AFTER INSERT ON {} FOR EACH ROW EXECUTE FUNCTION create_proposal_summary_entry()").format(
                sql.Identifier("trg_create_proposal_summary_entry"),
                sql.Identifier(table),
            )
        )
    conn.commit()


def pg_ensure_proposal_activities_table(conn, proposal_id, table_columns=None):
    """Ensure the ga_* activities table exists for a proposal.
    Replicates the logic of the create_proposal_activities_table() trigger.
    Returns the generated table name.
    """
    if table_columns is None:
        from config import GA_TABLE_COLUMNS
        table_columns = GA_TABLE_COLUMNS

    # Generate table name: ga_<md5_first10>_<sanitized_id_first40>
    sanitized = re.sub(r"[^a-zA-Z0-9]", "", proposal_id)[:40]
    table_name = f"ga_{hashlib.md5(proposal_id.encode()).hexdigest()[:10]}_{sanitized}"

    create_sql = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {} (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            block_time TIMESTAMP WITH TIME ZONE NULL,
            voter_role VARCHAR(50) NULL,
            voter_id VARCHAR(255) NULL,
            vote VARCHAR(50) NULL,
            meta_url TEXT NULL,
            comment TEXT NULL,
            processed_at TIMESTAMP WITH TIME ZONE NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """).format(sql.Identifier(table_name))

    md5_short = hashlib.md5(proposal_id.encode()).hexdigest()[:8]
    index_sql = sql.SQL("""
        CREATE UNIQUE INDEX IF NOT EXISTS {} ON {}(voter_id, block_time);
        CREATE INDEX IF NOT EXISTS {} ON {}(voter_id);
        CREATE INDEX IF NOT EXISTS {} ON {}(voter_role);
        CREATE INDEX IF NOT EXISTS {} ON {}(block_time DESC);
        CREATE INDEX IF NOT EXISTS {} ON {}(vote)
    """).format(
        sql.Identifier(f"idx_{md5_short}_voter_block_time"), sql.Identifier(table_name),
        sql.Identifier(f"idx_{md5_short}_voter_id"), sql.Identifier(table_name),
        sql.Identifier(f"idx_{md5_short}_voter_role"), sql.Identifier(table_name),
        sql.Identifier(f"idx_{md5_short}_block_time"), sql.Identifier(table_name),
        sql.Identifier(f"idx_{md5_short}_vote"), sql.Identifier(table_name),
    )

    with conn.cursor() as cur:
        cur.execute(create_sql)
        cur.execute(index_sql)
        cur.execute(
            sql.SQL("UPDATE {} SET activities_table_name = %s, activities_table_created = TRUE WHERE proposal_id = %s").format(sql.Identifier("proposals")),
            (table_name, proposal_id)
        )
    conn.commit()
    return table_name


def pg_upsert_batch(conn, table, columns, rows, conflict_cols=None, do_update=True, preserve_cols=()):
    """Insert/upsert a batch of rows into PostgreSQL using execute_values.
    If conflict_cols is set, performs ON CONFLICT DO UPDATE on those columns.
    Set do_update=False to perform ON CONFLICT DO NOTHING instead.
    preserve_cols: columns excluded from the SET clause (e.g. "id") so their
    existing values are kept on conflict. Default empty = current behavior.
    """
    if not rows:
        return 0

    cols_sql = sql.SQL(", ").join(sql.Identifier(c) for c in columns)

    query = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
        sql.Identifier(table), cols_sql
    )
    if conflict_cols:
        conflict_cols_sql = sql.SQL(", ").join(sql.Identifier(c) for c in conflict_cols)
        if do_update:
            # Build SET clause = EXCLUDED.col for all columns except conflict + preserved
            conflict_set = {c.lower() for c in conflict_cols}
            preserve_set = {c.lower() for c in preserve_cols}
            update_cols = [c for c in columns if c.lower() not in conflict_set and c.lower() not in preserve_set]
            if update_cols:
                set_clause = sql.SQL(", ").join(
                    sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
                    for c in update_cols
                )
                conflict_sql = sql.SQL(" ON CONFLICT ({}) DO UPDATE SET {}").format(
                    conflict_cols_sql,
                    set_clause,
                )
            else:
                conflict_sql = sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(conflict_cols_sql)
        else:
            conflict_sql = sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(conflict_cols_sql)
        query = sql.SQL("{}{}").format(query, conflict_sql)

    # Build values tuple list
    values = []
    for row in rows:
        values.append(tuple(row.get(c) for c in columns))

    try:
        with conn.cursor() as cur:
            execute_values(cur, query, values, template=None, page_size=100)
            count = cur.rowcount
        conn.commit()
        return count if count and count > 0 else len(rows)
    except Exception as e:
        conn.rollback()
        raise


def pg_row_count(conn, table):
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
        return cur.fetchone()[0]


def pg_query(conn, query_sql, params=None):
    """Execute a raw SQL query on PostgreSQL."""
    with conn.cursor() as cur:
        cur.execute(query_sql, params)
        try:
            return cur.fetchall()
        except psycopg2.ProgrammingError:
            return []


# ── Utilities ──────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def gen_uuid():
    return str(uuid.uuid4())


def dedup_rows(rows, pk="id"):
    seen = set()
    result = []
    for row in rows:
        val = row.get(pk)
        if val in seen:
            continue
        seen.add(val)
        result.append(row)
    return result
