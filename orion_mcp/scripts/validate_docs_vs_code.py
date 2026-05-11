#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    required = [
        root / "ARCHITECTURE.md",
        root / "docs" / "TRACEABILITY.md",
        root / "docs" / "architecture.md",
        root / "docs" / "modules.md",
        root / "docs" / "api.md",
        root / "src" / "orion_mcp" / "api" / "main.py",
        root / "src" / "orion_mcp" / "core" / "orchestrator" / "orchestrator.py",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise SystemExit("Ficheiros em falta:\n" + "\n".join(missing))
    print("validate_docs_vs_code: OK")


if __name__ == "__main__":
    main()
