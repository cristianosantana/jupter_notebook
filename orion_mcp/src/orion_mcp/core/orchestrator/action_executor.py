from __future__ import annotations

from orion_mcp.core.state.models import State
from orion_mcp.core.tools.registry import (
    ToolRegistry,
    merge_tool_result_into_state,
    mcp_stdout,
    pop_domain_query_flags,
)


class ActionExecutor:
    def __init__(self, tools: ToolRegistry):
        self._tools = tools

    async def run_call_tool(self, state: State) -> State:
        mcp_stdout(self._tools.settings, "[ORION_MCP] ActionExecutor.run_call_tool: ANTES execute_default_tool")
        try:
            key, raw = await self._tools.execute_default_tool(state)
            mcp_stdout(self._tools.settings, "[ORION_MCP] ActionExecutor.run_call_tool: DEPOIS execute_default_tool")
            merged = merge_tool_result_into_state(
                state, key, raw, settings=self._tools.settings
            )
            mcp_stdout(
                self._tools.settings,
                "[ORION_MCP] ActionExecutor.run_call_tool: DEPOIS merge_tool_result_into_state",
            )
            return merged
        except RuntimeError as e:
            cause = e.__cause__
            if not isinstance(cause, TimeoutError) and "tool_timeout" not in str(e).lower():
                raise
            mcp_stdout(
                self._tools.settings,
                "[ORION_MCP] ActionExecutor.run_call_tool: tool_timeout — degradação perf",
            )
            s = pop_domain_query_flags(state.model_copy(deep=True))
            s.flags.pop("force_refresh", None)
            cur = s.flags.get("perf")
            base: dict[str, bool] = {str(k): bool(v) for k, v in cur.items()} if isinstance(cur, dict) else {}
            base["tool_timeout"] = True
            s.flags = {**s.flags, "perf": base}
            return s
