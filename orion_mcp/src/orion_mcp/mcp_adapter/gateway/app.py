from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import grpc.aio
from fastapi import FastAPI
from pydantic import BaseModel, Field

from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2 as pb2
from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2_grpc as pb2_grpc


class RunToolBody(BaseModel):
    tool_name: str = Field(min_length=1)
    args_json: str = Field(default="{}")


def create_gateway_app(*, grpc_target: str) -> FastAPI:
    """
    Encaminha pedidos HTTP para o serviço gRPC no mesmo host (ex.: 127.0.0.1:50051).
    Desligar em produção crítica ou proteger com rede isolada / autenticação forte.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        channel = grpc.aio.insecure_channel(grpc_target)
        app.state.grpc_channel = channel
        app.state.grpc_stub = pb2_grpc.AnalyticsServiceV1Stub(channel)
        yield
        await channel.close()

    app = FastAPI(title="Orion MCP HTTP Gateway", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def http_health() -> dict[str, str]:
        stub: pb2_grpc.AnalyticsServiceV1Stub = app.state.grpc_stub
        r = await stub.Health(pb2.HealthRequest(), timeout=2.0)
        return {"status": r.status}

    @app.post("/debug/run_tool")
    async def debug_run_tool(body: RunToolBody) -> dict[str, object]:
        stub: pb2_grpc.AnalyticsServiceV1Stub = app.state.grpc_stub
        resp = await stub.RunTool(
            pb2.RunToolRequest(tool_name=body.tool_name, args_json=body.args_json),
            timeout=30.0,
        )
        return {"ok": resp.ok, "envelope_json": resp.envelope_json, "error": resp.error}

    return app
