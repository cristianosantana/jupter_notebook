"""
Servidor MCP legado (stdio / FastMCP) — apenas desenvolvimento ou integrações Cursor.
O contrato de produção API↔dados de negócio é **gRPC** (`orion_mcp.mcp_adapter.server.main`).
"""

from __future__ import annotations

import json

from fastmcp import FastMCP

from orion_mcp.core.tools.stub_analytics import AnalyticsStubArgs, AnalyticsStubTool

mcp = FastMCP("OrionMCP")
_tool = AnalyticsStubTool()


@mcp.tool(name=_tool.name, description=_tool.description)
async def run_analytics_stub(metric: str = "demo") -> str:
    args = AnalyticsStubArgs(metric=metric)
    out = await _tool.run(args)
    return json.dumps(out, ensure_ascii=False)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
