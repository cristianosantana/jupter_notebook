from __future__ import annotations

import asyncio
import logging
from typing import Any

from orion_mcp.core.config.settings import Settings, get_settings
from orion_mcp.core.state.models import DataCacheEntry, State
from orion_mcp.core.tools.base import Tool
from orion_mcp.core.tools.data_interpreter import tool_result_to_llm_summary
from orion_mcp.core.tools.stub_analytics import AnalyticsStubArgs, AnalyticsStubTool
from orion_mcp.infra.cache.tool_cache import MemoryToolCache, ToolCache, tool_key
from orion_mcp.mcp_adapter.client.grpc_client import GrpcMcpToolClient

_logger = logging.getLogger(__name__)


def mcp_stdout(settings: Settings, msg: str) -> None:
    if settings.mcp_debug_stdout:
        print(msg, flush=True)


STUB_TOOL_NAME = AnalyticsStubTool().name
DOMAIN_TOOL_NAME = "run_domain_query"


def pop_domain_query_flags(state: State) -> State:
    """Remove hints one-shot de consulta catalogada (sucesso, erro ou timeout)."""
    s = state.model_copy(deep=True)
    s.flags.pop("domain_query_id", None)
    s.flags.pop("domain_query_extra", None)
    return s


def merge_tool_result_into_state(
    state: State,
    cache_key: str,
    raw: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> State:
    cfg = settings or get_settings()
    state = pop_domain_query_flags(state)
    if raw.get("cached"):
        summary = str(raw.get("cached_summary", ""))
    else:
        summary = tool_result_to_llm_summary(
            raw,
            preview_rows=cfg.tool_llm_preview_rows,
            max_chars=cfg.effective_tool_llm_summary_max_chars(),
            catalog_full_rows=cfg.tool_llm_catalog_full_rows,
        )
    state.data_cache[cache_key] = DataCacheEntry(summary=summary)
    if isinstance(raw.get("metric"), str):
        state.current_metric = raw["metric"]
    if raw.get("mcp_degraded"):
        cur = state.flags.get("perf")
        base: dict[str, bool] = {str(k): bool(v) for k, v in cur.items()} if isinstance(cur, dict) else {}
        base["mcp_unavailable"] = True
        state.flags = {**state.flags, "perf": base}
    state.flags.pop("force_refresh", None)
    return state


class ToolRegistry:
    def __init__(self, settings: Settings, cache: ToolCache | None = None):
        self._settings = settings
        self._cache = cache or MemoryToolCache()
        self._tools: dict[str, Tool] = {
            AnalyticsStubTool().name: AnalyticsStubTool(),
        }
        self._grpc: GrpcMcpToolClient | None = None
        if (settings.mcp_grpc_target or "").strip():
            self._grpc = GrpcMcpToolClient(settings)

    @property
    def settings(self) -> Settings:
        return self._settings

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def _llm_summary(self, raw: dict[str, Any]) -> str:
        return tool_result_to_llm_summary(
            raw,
            preview_rows=self._settings.tool_llm_preview_rows,
            max_chars=self._settings.effective_tool_llm_summary_max_chars(),
            catalog_full_rows=self._settings.tool_llm_catalog_full_rows,
        )

    def _domain_payload(self, state: State) -> dict[str, Any]:
        raw_extra = state.flags.get("domain_query_extra")
        extra: dict[str, Any] = raw_extra if isinstance(raw_extra, dict) else {}
        qid = str(state.flags.get("domain_query_id") or "").strip()
        lim = extra.get("limit", self._settings.tool_domain_default_limit)
        off = extra.get("offset", 0)
        if lim is None:
            lim = self._settings.tool_domain_default_limit
        if off is None:
            off = 0
        lim_i = max(1, min(10000, int(lim)))
        off_i = max(0, int(off))
        if "summarize" in extra:
            summarize = bool(extra["summarize"])
        else:
            summarize = self._settings.tool_domain_default_summarize
        payload: dict[str, Any] = {
            "query_id": qid,
            "limit": lim_i,
            "offset": off_i,
            "summarize": summarize,
        }
        date_from = str(state.filters.get("date_from") or "").strip()
        date_to = str(state.filters.get("date_to") or "").strip()
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to
        return payload

    async def execute_default_tool(self, state: State) -> tuple[str, dict[str, Any]]:
        """
        Executa run_domain_query (gRPC) quando há hint de domínio + cliente gRPC;
        caso contrário run_analytics_stub (comportamento anterior).
        """
        mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry.execute_default_tool: INÍCIO")
        domain_id = str(state.flags.get("domain_query_id") or "").strip()
        use_domain = bool(domain_id and self._grpc is not None)

        if use_domain:
            tool_name = DOMAIN_TOOL_NAME
            payload = self._domain_payload(state)
            mcp_stdout(
                self._settings,
                f"[ORION_MCP] ToolRegistry: ramo domain tool={tool_name!r} payload={payload!r}",
            )
        else:
            tool_name = STUB_TOOL_NAME
            tool = self._tools[STUB_TOOL_NAME]
            args = AnalyticsStubArgs(
                metric=state.current_metric or "demo",
                date_from=str(state.filters.get("date_from") or "") or None,
                date_to=str(state.filters.get("date_to") or "") or None,
            )
            payload = args.model_dump()
            mcp_stdout(
                self._settings,
                f"[ORION_MCP] ToolRegistry: ramo stub tool={tool.name!r} payload={payload!r}",
            )

        key = tool_key(tool_name, payload)
        mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry: ANTES cache.get")
        cached = await self._cache.get(key)
        mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry: DEPOIS cache.get")
        if cached is not None:
            _logger.info("tool_cache_hit", extra={"tool": tool_name, "key": key[:16]})
            mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry: cache HIT — retorno sem gRPC/exec")
            return key, {"cached_summary": cached, "cached": True}

        use_grpc = self._grpc is not None
        mcp_stdout(
            self._settings,
            f"[ORION_MCP] ToolRegistry: cache MISS — ANTES exec "
            f"(grpc={'sim' if use_grpc else 'não (in-process)'})",
        )

        async def _run() -> dict[str, Any]:
            if use_domain:
                assert self._grpc is not None
                mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry._run: ANTES grpc.run_tool domain")
                out = await self._grpc.run_tool(tool_name, payload)
                mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry._run: DEPOIS grpc.run_tool domain")
                return out
            if self._grpc is not None:
                mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry._run: ANTES grpc.run_tool stub")
                out = await self._grpc.run_tool(tool_name, payload)
                mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry._run: DEPOIS grpc.run_tool stub")
                return out
            stub_tool = self._tools[STUB_TOOL_NAME]
            stub_args = AnalyticsStubArgs.model_validate(payload)
            mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry._run: ANTES tool.run in-process")
            out = await stub_tool.run(stub_args)
            mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry._run: DEPOIS tool.run in-process")
            return out

        try:
            mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry: ANTES asyncio.wait_for(_run)")
            raw = await asyncio.wait_for(_run(), timeout=self._settings.tool_timeout_seconds)
            mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry: DEPOIS asyncio.wait_for(_run)")
        except TimeoutError as e:
            mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry: TimeoutError — tool_timeout")
            raise RuntimeError("tool_timeout") from e

        summary = self._llm_summary(raw)
        l1_ttl = (
            self._settings.mcp_l1_tool_cache_ttl_seconds
            if self._grpc is not None
            else 3600
        )
        mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry: ANTES cache.set (L1)")
        await self._cache.set(key, summary, ttl_seconds=l1_ttl)
        mcp_stdout(self._settings, "[ORION_MCP] ToolRegistry: DEPOIS cache.set — FIM execute_default_tool")
        return key, raw

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)
