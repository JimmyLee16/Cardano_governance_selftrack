#!/usr/bin/env python3
"""Cardano Governance Sync — CLI (pure stdlib, no external deps).

Subcommands:
    sync [step]      Run sync pipeline (all or specific step)
    verify           Check DB row counts
    backup           Backup DB to .sql file
    ai               Generate AI summaries + budget extraction
    logs             View recent log files
    status           Quick DB connection + row count check

Usage:
    python cli.py sync                    # full sync
    python cli.py sync proposals          # only proposals step
    python cli.py sync --skip-delegators  # skip slow delegators
    python cli.py verify                  # verify DB
    python cli.py backup                  # full backup
    python cli.py backup --no-data        # logic only
    python cli.py ai --apply              # write AI summaries to DB
    python cli.py ai --dry-run            # preview only
    python cli.py logs                    # list log files
    python cli.py logs --tail             # tail latest log
    python cli.py status                  # quick DB status
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"
BACKUP_DIR = SCRIPT_DIR / "backups"


# ── Helpers ────────────────────────────────────────────────────────

def _run_script(script_name, extra_args=None):
    """Run a sibling Python script in the same directory."""
    script = SCRIPT_DIR / script_name
    if not script.exists():
        print(f"ERROR: {script} not found")
        sys.exit(1)
    cmd = [sys.executable, str(script)]
    if extra_args:
        cmd.extend(extra_args)
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


def _print_header(title):
    width = 60
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


# ── Subcommands ────────────────────────────────────────────────────

SYNC_STEPS = [
    "epoch",
    "proposals",
    "drep_list",
    "drep_info",
    "voting_summary",
    "vote_activities",
    "drep_delegators",
]


def cmd_sync(args):
    """Run sync pipeline (all or specific step)."""
    if args.step and args.step not in SYNC_STEPS:
        print(f"ERROR: Unknown step '{args.step}'. Valid: {', '.join(SYNC_STEPS)}")
        sys.exit(1)

    if args.step:
        _print_header(f"Sync: {args.step}")
        _run_script("sync_all.py", [f"--only={args.step}"])
    else:
        extra = []
        if args.skip_delegators:
            extra.append("--skip-delegators")
        _print_header("Full Sync Pipeline")
        _run_script("sync_all.py", extra)


def cmd_verify(args):
    """Verify DB row counts."""
    _print_header("DB Verification")
    _run_script("verify.py")


def cmd_backup(args):
    """Backup DB to .sql file."""
    _print_header("DB Backup")
    extra = []
    if args.no_data:
        extra.append("--no-data")
    if args.tables:
        extra.extend(["--tables", args.tables])
    if args.out:
        extra.extend(["--out", args.out])
    _run_script("backup_db.py", extra)


def cmd_ai(args):
    """Generate AI summaries + budget extraction."""
    _print_header("AI Summary + Budget Generation")
    extra = []
    if args.apply:
        extra.append("--apply")
    else:
        extra.append("--dry-run")
    if args.skip_existing:
        extra.append("--skip-existing")
    _run_script("generate_ai_summaries.py", extra)


def cmd_logs(args):
    """View recent log files."""
    if not LOG_DIR.exists():
        print("No logs directory found.")
        return

    log_files = sorted(LOG_DIR.glob("sync_*.log"), key=lambda f: f.stat().st_mtime, reverse=True)

    if not log_files:
        print("No log files found.")
        return

    if args.tail:
        # Tail the latest log file
        latest = log_files[0]
        print(f"--- {latest.name} (latest) ---\n")
        try:
            with open(latest, encoding="utf-8") as f:
                lines = f.readlines()
                # Show last 50 lines
                for line in lines[-50:]:
                    print(line, end="")
        except Exception as e:
            print(f"Error reading log: {e}")
    else:
        # List log files
        print(f"Log files in {LOG_DIR} ({len(log_files)} total):\n")
        print(f"{'#':<4} {'File':<40} {'Size':>10} {'Modified':>20}")
        print("-" * 78)
        for i, lf in enumerate(log_files[:20], 1):
            size = lf.stat().st_size
            mtime = lf.stat().st_mtime
            from datetime import datetime
            mod_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
            print(f"{i:<4} {lf.name:<40} {size_str:>10} {mod_str:>20}")
        if len(log_files) > 20:
            print(f"\n  ... and {len(log_files) - 20} more files")
        print(f"\nUse: python cli.py logs --tail  to view latest log")


def cmd_status(args):
    """Quick DB connection + row count check."""
    _print_header("DB Status")
    from helpers import pg_connect, pg_row_count
    from config import TABLE_COLUMNS

    try:
        conn = pg_connect()
        print("  Connected to PostgreSQL OK\n")
        print(f"  {'Table':<35} {'Rows':>10}")
        print(f"  {'-' * 47}")
        for table in sorted(TABLE_COLUMNS.keys()):
            try:
                count = pg_row_count(conn, table)
                print(f"  {table:<35} {count:>10}")
            except Exception:
                print(f"  {table:<35} {'N/A':>10}")

        # ga_* count
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE 'ga_%'"
            )
            ga_count = cur.fetchone()[0]
        print(f"\n  ga_* tables: {ga_count}")
        conn.close()
    except Exception as e:
        print(f"  DB connection failed: {e}")
        sys.exit(1)


# ── Main ───────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Cardano Governance Sync — CLI tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # sync
    p_sync = sub.add_parser("sync", help="Run sync pipeline")
    p_sync.add_argument("step", nargs="?", default=None, help=f"Specific step: {', '.join(SYNC_STEPS)}")
    p_sync.add_argument("--skip-delegators", action="store_true", help="Skip drep_delegators (slow)")
    p_sync.set_defaults(func=cmd_sync)

    # verify
    p_verify = sub.add_parser("verify", help="Verify DB row counts")
    p_verify.set_defaults(func=cmd_verify)

    # backup
    p_backup = sub.add_parser("backup", help="Backup DB to .sql file")
    p_backup.add_argument("--no-data", action="store_true", help="Logic only (skip data)")
    p_backup.add_argument("--tables", default=None, help="Comma-separated table list")
    p_backup.add_argument("--out", default=None, help="Output file path")
    p_backup.set_defaults(func=cmd_backup)

    # ai
    p_ai = sub.add_parser("ai", help="Generate AI summaries + budget extraction")
    p_ai.add_argument("--apply", action="store_true", help="Write to DB (default: dry-run)")
    p_ai.add_argument("--skip-existing", action="store_true", help="Only process rows with NULL fields")
    p_ai.set_defaults(func=cmd_ai)

    # logs
    p_logs = sub.add_parser("logs", help="View recent log files")
    p_logs.add_argument("--tail", action="store_true", help="Tail latest log file")
    p_logs.set_defaults(func=cmd_logs)

    # status
    p_status = sub.add_parser("status", help="Quick DB connection + row count check")
    p_status.set_defaults(func=cmd_status)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
