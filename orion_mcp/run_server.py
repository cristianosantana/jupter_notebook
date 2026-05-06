"""
Arranque sem `pip install -e .`: delega ao uvicorn em **subprocesso** com PYTHONPATH=.../src,
para o processo do `--reload` herdar o módulo `orion_mcp`.

Uso: na raiz do repo `orion_mcp/`, executar `python3 run_server.py`.
"""
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
        "orion_mcp.api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload",
    ]
    raise SystemExit(subprocess.call(cmd, env=os.environ))
