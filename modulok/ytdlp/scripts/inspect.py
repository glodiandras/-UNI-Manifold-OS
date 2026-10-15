#!/usr/bin/env python3
"""Thin wrapper so the pipeline runs straight from a checkout, without install.

    python3 scripts/inspect.py --help
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
SRC = PROJECT_ROOT / "src"

# Python puts the script's own directory first on sys.path, which would let
# scripts/inspect.py shadow the standard library 'inspect' module. Drop it.
sys.path[:] = [
    entry for entry in sys.path
    if entry not in ("", str(SCRIPT_DIR)) and Path(entry or ".").resolve() != SCRIPT_DIR
]
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# Anchor config/, staging/, logs/ and archive/ to this checkout, whatever the
# current working directory is.
os.environ.setdefault("MSP_PROJECT_ROOT", str(PROJECT_ROOT))

if sys.version_info < (3, 11):
    sys.exit(
        f"Python 3.11+ is required, this is {sys.version.split()[0]}.\n"
        "  -> create a virtualenv with a newer interpreter: python3 -m venv .venv"
    )

try:
    from msp.cli.inspect import main
except ImportError as exc:  # pragma: no cover - broken checkout
    sys.exit(f"Cannot import the pipeline package (src/msp): {exc}")

if __name__ == "__main__":
    raise SystemExit(main())
