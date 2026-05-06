from __future__ import annotations

from dataclasses import dataclass

from orion_mcp.core.config.settings import Settings


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class RequestBudget:
    settings: Settings
    llm_calls: int = 0
    tool_calls: int = 0

    def record_llm(self) -> None:
        self.llm_calls += 1
        if self.llm_calls > self.settings.max_llm_calls_per_request:
            raise BudgetExceeded("max_llm_calls_per_request exceeded")

    def record_tool(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.settings.max_tool_calls_per_request:
            raise BudgetExceeded("max_tool_calls_per_request exceeded")

    def snapshot(self) -> dict[str, int]:
        return {"llm_calls": self.llm_calls, "tool_calls": self.tool_calls}
