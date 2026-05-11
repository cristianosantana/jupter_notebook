from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orion_mcp.core.tools.base import Tool


class AnalyticsStubArgs(BaseModel):
    metric: str = Field(default="demo", description="Nome lógico da métrica")
    date_from: str | None = Field(default=None, description="YYYY-MM-DD")
    date_to: str | None = Field(default=None, description="YYYY-MM-DD")


class AnalyticsStubTool(Tool):
    name = "run_analytics_stub"
    description = "Tool read-only de demonstração; devolve agregados fictícios idempotentes."

    @property
    def input_model(self) -> type[BaseModel]:
        return AnalyticsStubArgs

    async def run(self, args: BaseModel) -> dict[str, Any]:
        a = AnalyticsStubArgs.model_validate(args.model_dump())
        return {
            "metric": a.metric,
            "rows": 3,
            "sum_value": 42,
            "note": "stub deterministico",
        }
