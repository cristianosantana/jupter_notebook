"""
Entrypoint de desenvolvimento: `orion-api` (após `pip install -e .`).

Garante `PYTHONPATH` com a pasta `src/` antes de delegar ao uvicorn em **subprocesso**,
para o worker do `--reload` herdar o ambiente (evita `ModuleNotFoundError: orion_mcp`).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _src_dir() -> Path:
    # .../src/orion_mcp/cli.py -> .../src
    return Path(__file__).resolve().parent.parent


def bootstrap_pythonpath() -> None:
    src = _src_dir()
    s = str(src)
    if s not in sys.path:
        sys.path.insert(0, s)
    prev = os.environ.get("PYTHONPATH", "")
    if s not in prev.split(os.pathsep):
        os.environ["PYTHONPATH"] = s + (os.pathsep + prev if prev else "")


def main() -> None:
    bootstrap_pythonpath()
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "orion_mcp.api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload",
    ]
    raise SystemExit(subprocess.call(cmd, env=os.environ))
