#!/usr/bin/env python3
"""Entrypoint fino: python3 scripts/run_senna_replica.py <case| --suite ...>."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from senna_replica.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
