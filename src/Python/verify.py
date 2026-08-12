"""Verify PostgreSQL DB row counts.

Usage:
    python verify.py
"""

import sys

from config import TABLE_COLUMNS
from helpers import get_logger, check_env, pg_connect, pg_row_count, pg_query


def main():
    check_env()
    logger = get_logger()

    logger.info("=" * 55)
    logger.info("  PostgreSQL DB Verification")
    logger.info("=" * 55)
    logger.info(f"{'Table':<35} {'Rows':>10}")
    logger.info("-" * 55)

    conn = pg_connect()

    tables = list(TABLE_COLUMNS.keys()) + ["drep_voting_cache", "drep_epoch_stats", "drep_voting_patterns", "proposal_report_insights"]

    for table in sorted(tables):
        try:
            count = pg_row_count(conn, table)
            logger.info(f"{table:<35} {count:>10}")
        except Exception as e:
            logger.info(f"{table:<35} {'ERROR':>10}")

    # Also count ga_* tables
    with conn.cursor() as cur:
        cur.execute(
            "SELECT relname, n_live_tup FROM pg_stat_user_tables "
            "WHERE relname LIKE 'ga_%' ORDER BY relname"
        )
        ga_tables = cur.fetchall()

    if ga_tables:
        logger.info(f"\n--- ga_* tables ({len(ga_tables)}) ---")
        ga_total = 0
        for table_name, row_count in ga_tables:
            logger.info(f"  {table_name:<33} {row_count:>10}")
            ga_total += row_count
        logger.info(f"  {'TOTAL':<33} {ga_total:>10}")

    conn.close()
    logger.info("=" * 55)


if __name__ == "__main__":
    main()