from __future__ import annotations

import json
import socket
from typing import Any

import grpc.aio
import pytest

from orion_mcp.core.config.settings import Settings
from orion_mcp.mcp_adapter.client.grpc_client import GrpcMcpToolClient
from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2 as pb2
from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2_grpc as pb2_grpc
from orion_mcp.mcp_adapter.server.config import McpGrpcServerSettings
from orion_mcp.mcp_adapter.server.main import start_grpc_server_pair


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


@pytest.fixture
async def mcp_grpc_server() -> Any:
    port = _free_port()
    settings = McpGrpcServerSettings(
        mcp_server_grpc_host="127.0.0.1",
        mcp_server_grpc_port=port,
        mcp_mysql_url=None,
        mcp_redis_url=None,
        redis_url=None,
    )
    server, shutdown = await start_grpc_server_pair(settings)
    try:
        yield f"127.0.0.1:{port}"
    finally:
        await shutdown()


@pytest.mark.asyncio
async def test_grpc_health_and_run_analytics_stub(mcp_grpc_server: str) -> None:
    async with grpc.aio.insecure_channel(mcp_grpc_server) as ch:
        stub = pb2_grpc.AnalyticsServiceV1Stub(ch)
        h = await stub.Health(pb2.HealthRequest(), timeout=5.0)
        assert h.status == "SERVING"
        resp = await stub.RunTool(
            pb2.RunToolRequest(
                tool_name="run_analytics_stub",
                args_json=json.dumps({"metric": "demo", "date_from": None, "date_to": None}),
            ),
            timeout=5.0,
        )
        assert resp.ok
        env = json.loads(resp.envelope_json)
        assert env["value"]["metric"] == "demo"
        assert env["value"]["sum_value"] == 42


@pytest.mark.asyncio
async def test_grpc_run_domain_query_demo_ping(mcp_grpc_server: str) -> None:
    async with grpc.aio.insecure_channel(mcp_grpc_server) as ch:
        stub = pb2_grpc.AnalyticsServiceV1Stub(ch)
        resp = await stub.RunTool(
            pb2.RunToolRequest(
                tool_name="run_domain_query",
                args_json=json.dumps({"query_id": "demo_ping", "params": {}}),
            ),
            timeout=5.0,
        )
        assert resp.ok
        env = json.loads(resp.envelope_json)
        assert env["value"]["ping"] == 1


@pytest.mark.asyncio
async def test_grpc_client_with_circuit_breaker(mcp_grpc_server: str) -> None:
    settings = Settings(
        mcp_grpc_target=mcp_grpc_server,
        mcp_grpc_deadline_seconds=5.0,
        mcp_grpc_retry_count=0,
        mcp_grpc_circuit_failure_threshold=2,
        mcp_grpc_circuit_open_seconds=60.0,
    )
    client = GrpcMcpToolClient(settings)
    try:
        out = await client.run_tool("run_analytics_stub", {"metric": "x"})
        assert out["metric"] == "x"
        assert out["sum_value"] == 42
    finally:
        await client.aclose()
