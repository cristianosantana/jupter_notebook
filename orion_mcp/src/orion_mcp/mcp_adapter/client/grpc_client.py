from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import grpc
import grpc.aio

from orion_mcp.core.config.settings import Settings
from orion_mcp.mcp_adapter.client.circuit_breaker import CircuitBreaker, CircuitOpenError
from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2 as pb2
from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2_grpc as pb2_grpc
from orion_mcp.mcp_adapter.models.response_envelope import envelope_value

_logger = logging.getLogger(__name__)


class GrpcMcpToolClient:
    """Cliente assíncrono gRPC para `AnalyticsServiceV1` (tools de negócio no serviço MCP)."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._channel: grpc.aio.Channel | None = None
        self._stub: pb2_grpc.AnalyticsServiceV1Stub | None = None
        self._lock = asyncio.Lock()
        self._breaker = CircuitBreaker(
            failure_threshold=settings.mcp_grpc_circuit_failure_threshold,
            open_seconds=settings.mcp_grpc_circuit_open_seconds,
        )

    async def aclose(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def _ensure(self) -> pb2_grpc.AnalyticsServiceV1Stub:
        async with self._lock:
            if self._stub is not None:
                return self._stub
            target = (self._settings.mcp_grpc_target or "").strip()
            if not target:
                raise RuntimeError("mcp_grpc_target não configurado")
            print(f"[ORION_MCP] GrpcMcpToolClient._ensure: ANTES criar canal gRPC target={target!r}", flush=True)
            if self._settings.mcp_grpc_use_tls:
                creds = grpc.ssl_channel_credentials()
                self._channel = grpc.aio.secure_channel(target, creds)
            else:
                self._channel = grpc.aio.insecure_channel(target)
            self._stub = pb2_grpc.AnalyticsServiceV1Stub(self._channel)
            print("[ORION_MCP] GrpcMcpToolClient._ensure: DEPOIS criar canal + stub", flush=True)
            return self._stub

    async def run_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        print(f"[ORION_MCP] GrpcMcpToolClient.run_tool: INÍCIO tool_name={tool_name!r}", flush=True)
        try:
            print("[ORION_MCP] GrpcMcpToolClient.run_tool: ANTES circuit_breaker.before_call", flush=True)
            self._breaker.before_call()
            print("[ORION_MCP] GrpcMcpToolClient.run_tool: DEPOIS circuit_breaker.before_call", flush=True)
        except CircuitOpenError:
            print("[ORION_MCP] GrpcMcpToolClient.run_tool: circuit OPEN — degradação", flush=True)
            return _degraded(tool_name, args, note="mcp_grpc_circuit_open")
        print("[ORION_MCP] GrpcMcpToolClient.run_tool: ANTES _ensure", flush=True)
        stub = await self._ensure()
        print("[ORION_MCP] GrpcMcpToolClient.run_tool: DEPOIS _ensure", flush=True)
        payload = json.dumps(args, ensure_ascii=False)
        req = pb2.RunToolRequest(tool_name=tool_name, args_json=payload)
        timeout = float(self._settings.mcp_grpc_deadline_seconds)
        for attempt in range(self._settings.mcp_grpc_retry_count + 1):
            try:
                print(
                    f"[ORION_MCP] GrpcMcpToolClient.run_tool: ANTES stub.RunTool "
                    f"(tentativa {attempt + 1}/{self._settings.mcp_grpc_retry_count + 1} timeout={timeout}s)",
                    flush=True,
                )
                resp = await stub.RunTool(req, timeout=timeout)
                print(
                    f"[ORION_MCP] GrpcMcpToolClient.run_tool: DEPOIS stub.RunTool ok={resp.ok!r}",
                    flush=True,
                )
                if resp.ok:
                    env = json.loads(resp.envelope_json or "{}")
                    self._breaker.record_success()
                    print("[ORION_MCP] GrpcMcpToolClient.run_tool: FIM sucesso", flush=True)
                    return envelope_value(env)
                _logger.warning("mcp_grpc_tool_error", extra={"error": resp.error})
                self._breaker.record_failure()
                print(f"[ORION_MCP] GrpcMcpToolClient.run_tool: FIM resp.ok=false err={resp.error!r}", flush=True)
                return _degraded(tool_name, args, note="mcp_grpc_tool_rejected", err=resp.error)
            except grpc.aio.AioRpcError as e:
                code = e.code()
                print(f"[ORION_MCP] GrpcMcpToolClient.run_tool: AioRpcError code={code}", flush=True)
                if attempt < self._settings.mcp_grpc_retry_count and code in (
                    grpc.StatusCode.UNAVAILABLE,
                    grpc.StatusCode.DEADLINE_EXCEEDED,
                ):
                    print("[ORION_MCP] GrpcMcpToolClient.run_tool: retry...", flush=True)
                    continue
                self._breaker.record_failure()
                _logger.warning("mcp_grpc_rpc_failed", extra={"code": str(code), "details": e.details()})
                return _degraded(tool_name, args, note="mcp_grpc_rpc_error", err=str(e))
            except Exception as e:
                self._breaker.record_failure()
                _logger.exception("mcp_grpc_unexpected")
                print(f"[ORION_MCP] GrpcMcpToolClient.run_tool: excepção inesperada {e!r}", flush=True)
                return _degraded(tool_name, args, note="mcp_grpc_unexpected", err=str(e))
        print("[ORION_MCP] GrpcMcpToolClient.run_tool: FIM falha genérica", flush=True)
        return _degraded(tool_name, args, note="mcp_grpc_failed")


def _degraded(
    tool_name: str,
    args: dict[str, Any],
    *,
    note: str,
    err: str | None = None,
) -> dict[str, Any]:
    metric = str(args.get("metric") or "demo")
    out: dict[str, Any] = {
        "metric": metric,
        "rows": 0,
        "sum_value": 0,
        "note": note,
        "mcp_degraded": True,
        "tool_name": tool_name,
    }
    if err:
        out["mcp_error"] = err[:500]
    return out
