"""Entrypoint: `python -m orion_mcp_v2.mcp_server_standalone` (transport SSE por defeito)."""

from __future__ import annotations

import os

from orion_mcp_v2.mcp_server_standalone.server import build_mcp_server


def main() -> None:
    mcp = build_mcp_server()
    host = os.environ.get("ORION_V2_MCP_SRV_HOST", "0.0.0.0")
    port = int(os.environ.get("ORION_V2_MCP_SRV_PORT", "8765"))
    transport = os.environ.get("ORION_V2_MCP_SRV_TRANSPORT", "sse")
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport in ("sse", "http", "streamable-http"):
        mcp.run(transport=transport, host=host, port=port)
    else:
        raise ValueError(f"transport inválido: {transport}")


if __name__ == "__main__":
    main()
