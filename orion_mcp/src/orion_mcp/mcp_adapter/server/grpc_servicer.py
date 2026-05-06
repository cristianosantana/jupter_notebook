from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import grpc
import redis.asyncio as redis
from redis.exceptions import RedisError

from orion_mcp.core.tools.stub_analytics import AnalyticsStubArgs, AnalyticsStubTool
from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2 as pb2
from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2_grpc as pb2_grpc
from orion_mcp.mcp_adapter.models.response_envelope import tool_envelope
from orion_mcp.mcp_adapter.server.query_executor import QueryExecutor, parse_json_object

_logger = logging.getLogger(__name__)

STUB_TOOL = AnalyticsStubTool()


@dataclass
class McpServerRuntime:
    mysql_pool: Any | None
    redis: redis.Redis | None
    l2_ttl_seconds: int
    semaphore: Any  # asyncio.Semaphore
    query_executor: QueryExecutor


def _l2_key(tool_name: str, args_json: str) -> str:
    h = hashlib.sha256(f"{tool_name}\n{args_json}".encode()).hexdigest()[:32]
    return f"orion:mcp:l2:{tool_name}:{h}"


class AnalyticsServiceServicer(pb2_grpc.AnalyticsServiceV1Servicer):
    def __init__(self, runtime: McpServerRuntime):
        self._rt = runtime

    async def Health(self, request: pb2.HealthRequest, context: grpc.aio.ServicerContext) -> pb2.HealthResponse:
        _ = request
        return pb2.HealthResponse(status="SERVING")

    async def ListTools(self, request: pb2.ListToolsRequest, context: grpc.aio.ServicerContext) -> pb2.ListToolsResponse:
        _ = request
        return pb2.ListToolsResponse(tool_names=[STUB_TOOL.name, "run_domain_query"])

    async def RunTool(
        self,
        request: pb2.RunToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb2.RunToolResponse:
        print("[ORION_MCP] Servicer.RunTool: ANTES semaphore.acquire", flush=True)
        async with self._rt.semaphore:
            print("[ORION_MCP] Servicer.RunTool: DENTRO semaphore — ANTES _run_tool_inner", flush=True)
            out = await self._run_tool_inner(request, context)
            print("[ORION_MCP] Servicer.RunTool: DEPOIS _run_tool_inner — sai semaphore", flush=True)
            return out

    async def _run_tool_inner(
        self,
        request: pb2.RunToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb2.RunToolResponse:
        tool_name = (request.tool_name or "").strip()
        args_json = request.args_json or "{}"
        print(
            f"[ORION_MCP] Servicer._run_tool_inner: INÍCIO tool_name={tool_name!r} "
            f"args_json_len={len(args_json)}",
            flush=True,
        )
        r = self._rt.redis
        cache_key = _l2_key(tool_name, args_json)
        if r is not None:
            try:
                print("[ORION_MCP] Servicer: ANTES Redis L2 get", flush=True)
                cached = await r.get(cache_key)
                print("[ORION_MCP] Servicer: DEPOIS Redis L2 get", flush=True)
                if cached:
                    print("[ORION_MCP] Servicer: L2 HIT — retorno sem executar tool", flush=True)
                    return pb2.RunToolResponse(ok=True, envelope_json=cached.decode(), error="")
            except RedisError as e:
                _logger.warning("mcp_l2_get_failed", extra={"err": str(e)})

        try:
            print("[ORION_MCP] Servicer: ANTES _execute_tool", flush=True)
            inner = await self._execute_tool(tool_name, args_json)
            print("[ORION_MCP] Servicer: DEPOIS _execute_tool", flush=True)
        except ValueError as e:
            _ = context
            print(f"[ORION_MCP] Servicer: ValueError _execute_tool {e!r}", flush=True)
            return pb2.RunToolResponse(ok=False, envelope_json="{}", error=str(e))
        except Exception:
            _logger.exception("mcp_run_tool_failed", extra={"tool": tool_name})
            print("[ORION_MCP] Servicer: Exception _execute_tool — abort INTERNAL", flush=True)
            await context.abort(grpc.StatusCode.INTERNAL, "run_tool_failed")
            raise

        env = tool_envelope(tool_name=tool_name, value=inner)
        out_json = json.dumps(env, ensure_ascii=False)
        if r is not None:
            try:
                print("[ORION_MCP] Servicer: ANTES Redis L2 set", flush=True)
                await r.set(cache_key, out_json, ex=self._rt.l2_ttl_seconds)
                print("[ORION_MCP] Servicer: DEPOIS Redis L2 set", flush=True)
            except RedisError as e:
                _logger.warning("mcp_l2_set_failed", extra={"err": str(e)})

        print("[ORION_MCP] Servicer._run_tool_inner: FIM ok", flush=True)
        return pb2.RunToolResponse(ok=True, envelope_json=out_json, error="")

    async def _execute_tool(self, tool_name: str, args_json: str) -> dict[str, Any]:
        print(f"[ORION_MCP] Servicer._execute_tool: ANTES parse_json tool_name={tool_name!r}", flush=True)
        payload = parse_json_object(args_json)
        print("[ORION_MCP] Servicer._execute_tool: DEPOIS parse_json", flush=True)

        if tool_name == "run_domain_query":
            qid = str(payload.get("query_id") or "").strip()
            if not qid:
                raise ValueError("query_id obrigatório para run_domain_query")
            nested = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            flat = {k: v for k, v in payload.items() if k not in ("query_id", "params")}
            params = {**flat, **nested}
            print(f"[ORION_MCP] Servicer._execute_tool: ANTES query_executor.run query_id={qid!r}", flush=True)
            out = await self._rt.query_executor.run(qid, params)
            print("[ORION_MCP] Servicer._execute_tool: DEPOIS query_executor.run", flush=True)
            return out

        if tool_name == STUB_TOOL.name:
            print("[ORION_MCP] Servicer._execute_tool: ANTES STUB_TOOL.run", flush=True)
            args = AnalyticsStubArgs.model_validate(payload)
            out = await STUB_TOOL.run(args)
            print("[ORION_MCP] Servicer._execute_tool: DEPOIS STUB_TOOL.run", flush=True)
            return out

        raise ValueError(f"tool_name desconhecido: {tool_name}")
