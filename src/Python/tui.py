#!/usr/bin/env python3
"""Cardano Governance Sync — TUI (full-screen, pure stdlib).

Arrow keys to navigate, Enter to select, q/Esc to quit.
Works on Windows (msvcrt) and Unix (termios/tty).

Usage:
    python tui.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

# Fix Windows cp1252 console encoding for Unicode (arrows, box-drawing, etc.)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"
BACKUP_DIR = SCRIPT_DIR / "backups"

# ── ANSI Colors ────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    BG_BLUE = "\033[44m"
    BG_CYAN = "\033[46m"
    BG_GREEN= "\033[42m"
    BG_RED  = "\033[41m"
    # 256-color
    ORANGE  = "\033[38;5;208m"
    GRAY    = "\033[38;5;240m"
    BRIGHT  = "\033[38;5;250m"

# ── Terminal helpers ───────────────────────────────────────────────

def _enable_ansi_windows():
    """Enable ANSI escape codes on Windows 10+."""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

def _get_terminal_size():
    cols, rows = shutil.get_terminal_size((80, 24))
    return cols, rows

def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

def hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

def show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

def move_to(row, col):
    sys.stdout.write(f"\033[{row};{col}H")
    sys.stdout.flush()

# ── Input (cross-platform) ─────────────────────────────────────────

class _Input:
    """Cross-platform single-key input."""

    def __init__(self):
        self._is_windows = sys.platform == "win32"

    def __enter__(self):
        if not self._is_windows:
            import termios, tty
            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setraw(self._fd)
        return self

    def getkey(self):
        if self._is_windows:
            import msvcrt
            ch = msvcrt.getwch()
            if ch == "\x00" or ch == "\xe0":  # Special key prefix
                ch2 = msvcrt.getwch()
                keys = {
                    "H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT",
                    "G": "HOME", "O": "END", "I": "PGUP", "Q": "PGDN",
                    "R": "F2", "S": "F4", "T": "F5", "U": "F6",
                }
                return keys.get(ch2, f"UNK_{ch2}")
            if ch == "\r":
                return "ENTER"
            if ch == "\x1b":
                return "ESC"
            if ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            if ch == "\x04":  # Ctrl+D
                return "ESC"
            return ch
        else:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                # Read escape sequence
                import select
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    ch2 = sys.stdin.read(2)
                    if ch2 == "[A": return "UP"
                    if ch2 == "[B": return "DOWN"
                    if ch2 == "[C": return "RIGHT"
                    if ch2 == "[D": return "LEFT"
                return "ESC"
            if ch == "\r" or ch == "\n":
                return "ENTER"
            if ch == "\x03":
                raise KeyboardInterrupt
            return ch

    def __exit__(self, *args):
        if not self._is_windows:
            import termios
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)


# ── UI Components ──────────────────────────────────────────────────

def draw_box(row, col, width, height, title=""):
    """Draw a box with optional title using Unicode box-drawing chars."""
    top    = f"┌{'─' * (width - 2)}┐"
    bottom = f"└{'─' * (width - 2)}┘"
    if title:
        title_str = f" {title} "
        top = f"┌{'─' * (width - 2 - len(title_str))}{title_str}┐"
    mid = f"│{' ' * (width - 2)}│"
    lines = [top] + [mid] * (height - 2) + [bottom]
    for i, line in enumerate(lines):
        move_to(row + i, col)
        sys.stdout.write(line)
    sys.stdout.flush()


def draw_header(width):
    """Draw the app header banner."""
    title = "  ◆ Cardano Governance Sync  "
    subtitle = " PostgreSQL · Koios · Blockfrost · IPFS "
    padding = (width - len(title)) // 2
    move_to(1, 1)
    sys.stdout.write(f"{C.CYAN}{C.BOLD}{' ' * padding}{title}{C.RESET}")
    move_to(2, 1)
    padding2 = (width - len(subtitle)) // 2
    sys.stdout.write(f"{C.GRAY}{' ' * padding2}{subtitle}{C.RESET}")
    sys.stdout.flush()


def draw_menu(items, selected, start_row, col, width):
    """Draw menu items with highlight on selected."""
    for i, (label, desc, enabled) in enumerate(items):
        move_to(start_row + i, col)
        if not enabled:
            line = f"  {C.GRAY}{label}{C.RESET}"
            desc_str = f"  {C.GRAY}{desc}{C.RESET}"
        elif i == selected:
            line = f"  {C.BG_CYAN}{C.BOLD}{C.WHITE}▶ {label}{C.RESET}"
            desc_str = f"  {C.CYAN}{desc}{C.RESET}"
        else:
            line = f"  {C.BRIGHT}  {label}{C.RESET}"
            desc_str = f"  {C.GRAY}{desc}{C.RESET}"
        # Pad to width
        visible_len = len(label) + 4
        sys.stdout.write(line + " " * max(0, width - visible_len - 2))
        # Description on same line if fits, else skip
        if len(desc) + visible_len + 4 < width:
            sys.stdout.write(desc_str)
    sys.stdout.flush()


def draw_footer(width, rows):
    """Draw footer with key hints."""
    hints = " ↑↓ Navigate · ENTER Select · q Quit "
    move_to(rows, 1)
    sys.stdout.write(f"{C.GRAY}{'─' * width}{C.RESET}")
    move_to(rows + 1, 1)
    padding = (width - len(hints)) // 2
    sys.stdout.write(f"{C.GRAY}{' ' * padding}{hints}{C.RESET}")
    sys.stdout.flush()


def draw_status_bar(msg, width, row, color=C.YELLOW):
    """Draw a status message bar."""
    move_to(row, 1)
    sys.stdout.write(" " * width)
    move_to(row, 1)
    sys.stdout.write(f"{color}{msg}{C.RESET}")
    sys.stdout.flush()


# ── Menu definitions ───────────────────────────────────────────────

MAIN_MENU = [
    ("Full Sync",             "Run all 7 sync steps + verify",          True),
    ("Sync: Step",            "Choose a specific sync step",            True),
    ("Verify DB",             "Check row counts across all tables",     True),
    ("DB Status",             "Quick connection + row count check",     True),
    ("Backup DB",             "Export DB to .sql file",                 True),
    ("AI Summaries",          "Generate AI summaries + budget extract", True),
    ("View Logs",             "Browse sync log files",                  True),
    ("Quit",                  "Exit",                                   True),
]

SYNC_STEPS = [
    ("epoch",           "Update current epoch from Koios tip"),
    ("proposals",       "Fetch proposal list from Koios"),
    ("drep_list",       "Fetch DRep registry from Blockfrost"),
    ("drep_info",       "Fetch DRep metadata + stake from Blockfrost"),
    ("voting_summary",  "Fetch voting summary from Koios"),
    ("vote_activities", "Fetch votes + IPFS comments → ga_* tables"),
    ("drep_delegators", "Fetch delegators from Koios (slow)"),
]

AI_MENU = [
    ("Dry Run (preview)",     "Preview without writing to DB",          True),
    ("Apply (write to DB)",   "Write summaries + budget to DB",         True),
    ("Apply + Skip Existing", "Only process rows with NULL fields",     True),
    ("Back",                  "Return to main menu",                    True),
]

BACKUP_MENU = [
    ("Full Backup",           "Data + SQL logic (functions, triggers)", True),
    ("Logic Only",            "Skip data, export DDL only",             True),
    ("Back",                  "Return to main menu",                    True),
]


# ── Actions ────────────────────────────────────────────────────────

def _run_script(script_name, extra_args=None, cwd=None):
    """Run a Python script, blocking, with output to terminal."""
    show_cursor()
    script = SCRIPT_DIR / script_name
    if not script.exists():
        print(f"{C.RED}ERROR: {script} not found{C.RESET}")
        input("\nPress Enter to continue...")
        return
    cmd = [sys.executable, str(script)]
    if extra_args:
        cmd.extend(extra_args)
    try:
        subprocess.run(cmd, check=False, cwd=cwd or str(SCRIPT_DIR))
    except KeyboardInterrupt:
        print("\nInterrupted.")
    input(f"\n{C.GRAY}Press Enter to return to TUI...{C.RESET}")


def action_full_sync():
    _run_script("sync_all.py")


def action_sync_step():
    # Sub-menu: pick step
    selected = 0
    items = [(name, desc, True) for name, desc in SYNC_STEPS] + [("Back", "Return to main menu", True)]
    while True:
        clear_screen()
        cols, rows = _get_terminal_size()
        draw_header(cols)
        draw_box(4, max(1, (cols - 50) // 2), 50, len(items) + 4, "Sync Step")
        draw_menu(items, selected, 6, max(1, (cols - 50) // 2) + 1, 48)
        draw_footer(cols, rows - 2)

        with _Input() as inp:
            key = inp.getkey()

        if key == "UP":
            selected = (selected - 1) % len(items)
        elif key == "DOWN":
            selected = (selected + 1) % len(items)
        elif key == "ENTER":
            if selected < len(SYNC_STEPS):
                step = SYNC_STEPS[selected][0]
                _run_script("sync_all.py", [f"--only={step}"])
            return
        elif key in ("ESC", "q"):
            return


def action_verify():
    _run_script("verify.py")


def action_status():
    show_cursor()
    clear_screen()
    cols, rows = _get_terminal_size()
    print(f"{C.CYAN}{C.BOLD}{'=' * 60}")
    print(f"  DB Status")
    print(f"{'=' * 60}{C.RESET}\n")

    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from helpers import pg_connect, pg_row_count
        from config import TABLE_COLUMNS

        conn = pg_connect()
        print(f"  {C.GREEN}✓ Connected to PostgreSQL{C.RESET}\n")
        print(f"  {C.BOLD}{'Table':<35} {'Rows':>10}{C.RESET}")
        print(f"  {'-' * 47}")
        for table in sorted(TABLE_COLUMNS.keys()):
            try:
                count = pg_row_count(conn, table)
                color = C.GREEN if count > 0 else C.YELLOW
                print(f"  {table:<35} {color}{count:>10}{C.RESET}")
            except Exception:
                print(f"  {table:<35} {C.RED}{'N/A':>10}{C.RESET}")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE 'ga_%'"
            )
            ga_count = cur.fetchone()[0]
        print(f"\n  {C.CYAN}ga_* tables: {ga_count}{C.RESET}")
        conn.close()
    except Exception as e:
        print(f"  {C.RED}✗ DB connection failed: {e}{C.RESET}")

    input(f"\n{C.GRAY}Press Enter to return to TUI...{C.RESET}")


def action_backup():
    selected = 0
    items = BACKUP_MENU
    while True:
        clear_screen()
        cols, rows = _get_terminal_size()
        draw_header(cols)
        draw_box(4, max(1, (cols - 50) // 2), 50, len(items) + 4, "Backup DB")
        draw_menu(items, selected, 6, max(1, (cols - 50) // 2) + 1, 48)
        draw_footer(cols, rows - 2)

        with _Input() as inp:
            key = inp.getkey()

        if key == "UP":
            selected = (selected - 1) % len(items)
        elif key == "DOWN":
            selected = (selected + 1) % len(items)
        elif key == "ENTER":
            if selected == 0:
                _run_script("backup_db.py")
            elif selected == 1:
                _run_script("backup_db.py", ["--no-data"])
            return
        elif key in ("ESC", "q"):
            return


def action_ai():
    selected = 0
    items = AI_MENU
    while True:
        clear_screen()
        cols, rows = _get_terminal_size()
        draw_header(cols)
        draw_box(4, max(1, (cols - 55) // 2), 55, len(items) + 4, "AI Summaries")
        draw_menu(items, selected, 6, max(1, (cols - 55) // 2) + 1, 53)
        draw_footer(cols, rows - 2)

        with _Input() as inp:
            key = inp.getkey()

        if key == "UP":
            selected = (selected - 1) % len(items)
        elif key == "DOWN":
            selected = (selected + 1) % len(items)
        elif key == "ENTER":
            if selected == 0:
                _run_script("generate_ai_summaries.py", ["--dry-run"])
            elif selected == 1:
                _run_script("generate_ai_summaries.py", ["--apply"])
            elif selected == 2:
                _run_script("generate_ai_summaries.py", ["--apply", "--skip-existing"])
            return
        elif key in ("ESC", "q"):
            return


def action_logs():
    show_cursor()
    clear_screen()
    cols, rows = _get_terminal_size()
    print(f"{C.CYAN}{C.BOLD}{'=' * 60}")
    print(f"  Log Files")
    print(f"{'=' * 60}{C.RESET}\n")

    if not LOG_DIR.exists():
        print(f"  {C.YELLOW}No logs directory found.{C.RESET}")
        input(f"\n{C.GRAY}Press Enter to return...{C.RESET}")
        return

    log_files = sorted(LOG_DIR.glob("sync_*.log"), key=lambda f: f.stat().st_mtime, reverse=True)

    if not log_files:
        print(f"  {C.YELLOW}No log files found.{C.RESET}")
        input(f"\n{C.GRAY}Press Enter to return...{C.RESET}")
        return

    print(f"  {'#':<4} {'File':<40} {'Size':>10} {'Modified':>20}")
    print(f"  {'-' * 78}")
    for i, lf in enumerate(log_files[:20], 1):
        size = lf.stat().st_size
        mtime = lf.stat().st_mtime
        mod_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
        print(f"  {i:<4} {lf.name:<40} {size_str:>10} {mod_str:>20}")

    if len(log_files) > 20:
        print(f"\n  {C.GRAY}... and {len(log_files) - 20} more files{C.RESET}")

    print(f"\n  {C.BOLD}Enter file number to view (or Enter to go back):{C.RESET} ", end="")
    try:
        choice = input().strip()
        if choice.isdigit() and 1 <= int(choice) <= min(20, len(log_files)):
            lf = log_files[int(choice) - 1]
            clear_screen()
            print(f"{C.CYAN}--- {lf.name} ---{C.RESET}\n")
            content = lf.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            # Show last 80 lines
            for line in lines[-80:]:
                print(line)
            input(f"\n{C.GRAY}Press Enter to return...{C.RESET}")
    except (ValueError, KeyboardInterrupt):
        pass


# ── Main TUI loop ──────────────────────────────────────────────────

def main():
    _enable_ansi_windows()
    selected = 0
    items = MAIN_MENU

    try:
        hide_cursor()
        while True:
            clear_screen()
            cols, rows = _get_terminal_size()
            draw_header(cols)
            menu_width = 52
            menu_col = max(1, (cols - menu_width) // 2)
            draw_box(4, menu_col, menu_width, len(items) + 4, "Main Menu")
            draw_menu(items, selected, 6, menu_col + 1, menu_width - 2)
            draw_footer(cols, rows - 2)

            with _Input() as inp:
                key = inp.getkey()

            if key == "UP":
                selected = (selected - 1) % len(items)
            elif key == "DOWN":
                selected = (selected + 1) % len(items)
            elif key == "ENTER":
                action = items[selected][0]
                if action == "Quit":
                    break
                elif action == "Full Sync":
                    action_full_sync()
                elif action == "Sync: Step":
                    action_sync_step()
                elif action == "Verify DB":
                    action_verify()
                elif action == "DB Status":
                    action_status()
                elif action == "Backup DB":
                    action_backup()
                elif action == "AI Summaries":
                    action_ai()
                elif action == "View Logs":
                    action_logs()
            elif key in ("ESC", "q"):
                break

    except KeyboardInterrupt:
        pass
    finally:
        show_cursor()
        clear_screen()
        print(f"{C.CYAN}Bye!{C.RESET}")


if __name__ == "__main__":
    main()
