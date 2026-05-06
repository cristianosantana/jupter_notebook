#!/usr/bin/env python3
"""Arranque local com PYTHONPATH=src."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
src_str = str(SRC)
prev_pp = os.environ.get("PYTHONPATH", "")
if src_str not in prev_pp.split(os.pathsep):
    os.environ["PYTHONPATH"] = src_str + (os.pathsep + prev_pp if prev_pp else "")

if __name__ == "__main__":
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "orion_mcp_v2.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8010",
        "--reload",
    ]
    raise SystemExit(subprocess.call(cmd, env=os.environ))
