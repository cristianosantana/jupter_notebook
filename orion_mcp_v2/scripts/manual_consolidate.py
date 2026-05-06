#!/usr/bin/env python3
"""Teste manual: `PYTHONPATH=src ORION_V2_DATABASE_URL=... python scripts/manual_consolidate.py user_id`"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from orion_mcp_v2.memory.consolidator import consolidate_user_memory


async def main() -> None:
    if len(sys.argv) < 2:
        print("usage: manual_consolidate.py <user_id>", file=sys.stderr)
        sys.exit(2)
    out = await consolidate_user_memory(sys.argv[1])
    print(out)


if __name__ == "__main__":
    asyncio.run(main())
