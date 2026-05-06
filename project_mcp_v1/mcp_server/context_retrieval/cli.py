"""CLI do worker: ``python -m mcp_server.context_retrieval.cli`` (com PYTHONPATH na raiz do projecto)."""

from __future__ import annotations

import asyncio

from .worker import _main


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
