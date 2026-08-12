"""Backup PostgreSQL DB: data + SQL logic (functions, triggers, views, indexes, sequences).

No pg_dump required — uses psycopg2 directly. Writes a single .sql file that
captures:
  * Functions / procedures  (pg_get_functiondef)
  * Triggers                (pg_get_triggerdef)
  * Views / materialized views (pg_get_viewdef)
  * Indexes (non-primary)   (pg_get_indexdef)
  * Sequences               (setval)
  * Table data              (COPY ... FROM STDIN, pg_dump-compatible)

Usage:
    python backup_db.py                     # full dump -> backups/db_backup_<ts>.sql
    python backup_db.py --tables proposals,ga_950cd4f78d_govaction122wue2k65qq8gmpz795z2axt8apka6
    python backup_db.py --no-data           # logic only
    python backup_db.py --out path.sql

Restore (with psql):
    psql "$DATABASE_URL" -f backup.sql
NOTE: data uses COPY, so tables must already exist at restore time (tables are
created by your sync scripts / triggers). Set session_replication_role=replica
before restore if you do NOT want triggers to re-fire during load.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from psycopg2 import sql
from psycopg2.extras import DictCursor

from helpers import pg_connect


def _fmt_ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def dump_ddl(conn, f, tables_filter):
    """Write functions, procedures, triggers, views, matviews, indexes, sequences."""
    f.write(b"-- ============================================================\n")
    f.write(b"--  SQL LOGIC (functions, procedures, triggers, views, indexes)\n")
    f.write(b"-- ============================================================\n\n")

    # ---- Functions / procedures ----
    f.write(b"-- ---- FUNCTIONS / PROCEDURES ----\n")
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT p.prokind, p.proname, pg_get_functiondef(p.oid) AS def "
            "FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.prokind IN ('f','p') "
            "ORDER BY p.proname"
        )
        for r in cur.fetchall():
            f.write(r["def"].encode("utf-8"))
            if not r["def"].rstrip().endswith(";"):
                f.write(b";")
            f.write(b"\n\n")
    f.write(b"\n")

    # ---- Triggers ----
    f.write(b"-- ---- TRIGGERS ----\n")
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid, true) AS def "
            "FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND NOT t.tgisinternal "
            "ORDER BY c.relname, t.tgname"
        )
        for r in cur.fetchall():
            f.write(r["def"].encode("utf-8"))
            if not r["def"].rstrip().endswith(";"):
                f.write(b";")
            f.write(b"\n\n")
    f.write(b"\n")

    # ---- Views ----
    f.write(b"-- ---- VIEWS ----\n")
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT c.relname, pg_get_viewdef(c.oid, true) AS def "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'v' "
            "ORDER BY c.relname"
        )
        for r in cur.fetchall():
            f.write(f'CREATE OR REPLACE VIEW public.{r["relname"]} AS\n'.encode("utf-8"))
            f.write(r["def"].encode("utf-8"))
            f.write(b";\n\n")
    f.write(b"\n")

    # ---- Materialized views (DDL only; refresh note) ----
    f.write(b"-- ---- MATERIALIZED VIEWS ----\n")
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT c.relname, pg_get_viewdef(c.oid, true) AS def "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'm' "
            "ORDER BY c.relname"
        )
        for r in cur.fetchall():
            f.write(f'CREATE MATERIALIZED VIEW public.{r["relname"]} AS\n'.encode("utf-8"))
            f.write(r["def"].encode("utf-8"))
            f.write(b";\n")
            f.write(f'REFRESH MATERIALIZED VIEW public.{r["relname"]};\n\n'.encode("utf-8"))
    f.write(b"\n")

    # ---- Indexes (non-primary) ----
    f.write(b"-- ---- INDEXES ----\n")
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT pg_get_indexdef(i.indexrelid) AS def "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r','p') "
            "AND NOT i.indisprimary AND NOT i.indisclustered "
            "ORDER BY c.relname"
        )
        for r in cur.fetchall():
            f.write(r["def"].encode("utf-8"))
            f.write(b";\n\n")
    f.write(b"\n")


def dump_sequences(conn, f):
    f.write(b"-- ---- SEQUENCES (setval) ----\n")
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'S' ORDER BY c.relname"
        )
        for r in cur.fetchall():
            seq = sql.Identifier("public", r["relname"])
            cur.execute(sql.SQL("SELECT last_value, is_called FROM {}").format(seq))
            last, is_called = cur.fetchone()
            f.write(
                sql.SQL("SELECT setval({}, {}, {});\n").format(
                    sql.Literal(f"public.{r['relname']}"),
                    sql.Literal(last),
                    sql.Literal(is_called),
                ).as_string(conn).encode("utf-8")
            )
    f.write(b"\n")


def get_tables(conn, only):
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r','p') "
            "ORDER BY c.relname"
        )
        all_tables = [r["relname"] for r in cur.fetchall()]
    if only:
        only = {t.strip() for t in only.split(",") if t.strip()}
        return [t for t in all_tables if t in only]
    return all_tables


def get_columns(conn, table):
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s "
            "ORDER BY ordinal_position",
            (table,),
        )
        return [r["column_name"] for r in cur.fetchall()]


def dump_data(conn, f, tables):
    f.write(b"-- ============================================================\n")
    f.write(b"--  DATA (COPY FROM STDIN)\n")
    f.write(b"-- ============================================================\n\n")
    with conn.cursor(cursor_factory=DictCursor) as cur:
        for t in tables:
            cols = get_columns(conn, t)
            col_list = ", ".join(cols)
            f.write(f"COPY public.{t} ({col_list}) FROM stdin;\n".encode("utf-8"))
            sel = sql.SQL("SELECT {} FROM public.{}").format(
                sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                sql.Identifier(t),
            )
            try:
                cur.copy_expert(sql.SQL("COPY ({}) TO STDOUT").format(sel), f)
            except Exception as e:
                f.write(b"\\.\n")
                print(f"  !! COPY failed for {t}: {e}")
                continue
            f.write(b"\\.\n")
    f.write(b"\n")


def main():
    ap = argparse.ArgumentParser(description="Backup PostgreSQL DB (data + SQL logic)")
    ap.add_argument("--tables", help="comma-separated table list to dump data for")
    ap.add_argument("--no-data", action="store_true", help="skip data, logic only")
    ap.add_argument("--out", help="output file path")
    args = ap.parse_args()

    conn = pg_connect()
    tables = get_tables(conn, args.tables)

    out_dir = Path(__file__).parent / "backups"
    out_dir.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else out_dir / f"db_backup_{_fmt_ts()}.sql"

    print(f"Tables to dump ({len(tables)}):")
    for t in tables:
        print(f"   - {t}")

    with open(out_path, "wb") as f:
        f.write(b"-- PostgreSQL DB backup generated at %s\n" % datetime.now(timezone.utc).isoformat().encode())
        f.write(b"SET client_encoding = 'UTF8';\n")
        f.write(b"SET standard_conforming_strings = on;\n")
        f.write(b"BEGIN;\n\n")

        dump_ddl(conn, f, args.tables)

        if not args.no_data:
            dump_sequences(conn, f)
            dump_data(conn, f, tables)

        f.write(b"COMMIT;\n")

    conn.close()
    size = out_path.stat().st_size / (1024 * 1024)
    print(f"\nBackup written: {out_path}  ({size:.2f} MB)")


if __name__ == "__main__":
    main()
