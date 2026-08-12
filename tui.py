#!/usr/bin/env python3
"""Root entry point — launches the TUI from src/Python/tui.py.

Run from repo root:
    python tui.py
"""

import os
import sys
from pathlib import Path

_repo_root = Path(__file__).parent
_tui_script = _repo_root / "src" / "Python" / "tui.py"

if not _tui_script.exists():
    print(f"ERROR: TUI script not found at {_tui_script}")
    sys.exit(1)

# Add src/Python to sys.path so tui.py can import helpers/config
sys.path.insert(0, str(_repo_root / "src" / "Python"))
os.chdir(str(_repo_root / "src" / "Python"))

# Execute tui.py
exec(open(_tui_script, encoding="utf-8").read())
