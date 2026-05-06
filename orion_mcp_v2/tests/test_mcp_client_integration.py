"""C3: integração opcional contra MCP_SERVER_URL (Serviço B em execução)."""

from __future__ import annotations

import os

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remote_client_lists_tools_smoke() -> None:
    url = (os.environ.get("MCP_SERVER_URL") or "").strip()
    if not url:
        pytest.skip("MCP_SERVER_URL não definido — smoke manual ou CI com servidor MCP")

    from fastmcp import Client
    from fastmcp.client.transports import SSETransport

    transport = SSETransport(url=url.rstrip("/"))
    async with Client(transport) as client:
        tools = await client.list_tools()
        names = sorted({t.name for t in tools})
        assert "run_analytics_query" in names
        assert "list_analytics_queries" in names
