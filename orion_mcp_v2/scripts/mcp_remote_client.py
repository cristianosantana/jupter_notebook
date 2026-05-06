#!/usr/bin/env python3
"""
Cliente MCP remoto (Serviço C): apenas SDK cliente FastMCP — não importa o servidor.

Variáveis:
  MCP_SERVER_URL — URL SSE do servidor (ex.: http://localhost:8765/sse)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = str(ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


async def _run() -> int:
    from fastmcp import Client
    from fastmcp.client.transports import SSETransport

    raw = (os.environ.get("MCP_SERVER_URL") or "").strip()
    if not raw:
        print("MCP_SERVER_URL não definido", file=sys.stderr)
        return 2
    transport = SSETransport(url=raw.rstrip("/"))
    async with Client(transport) as client:
        tools = await client.list_tools()
        names = [getattr(t, "name", str(t)) for t in tools]
        print(json.dumps({"tools": names}, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
