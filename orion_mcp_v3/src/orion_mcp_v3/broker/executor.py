"""
Orquestrador: texto → Planner → compilador SQL seguro → execução MySQL (Fase 1.5).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from orion_mcp_v3.broker.planner import build_query_plan
from orion_mcp_v3.broker.query_templates import QueryTemplate
from orion_mcp_v3.broker.semantic_query_compiler import merge_executable_hints
from orion_mcp_v3.runtime.intent_resolver import IntentResolver
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist, compile_select
from orion_mcp_v3.connection_hub.mysql_backend import MysqlDatastoreClient
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan


@dataclass(frozen=True, slots=True)
class AnalyticsResult:
    plan: SemanticQueryPlan
    sql: str
    rows: list[dict[str, Any]]
    row_count: int


class AnalyticsExecutor:
    """
    Orquestra: consulta em linguagem natural → plano → SQL (allowlist) → MySQL.
    """

    def __init__(
        self,
        mysql_client: MysqlDatastoreClient,
        allowlist: SqlAllowlist,
        *,
        default_limit: int = 1000,
        default_sql_table: str = "os",
    ) -> None:
        self._mysql = mysql_client
        self._allowlist = allowlist
        self.default_limit = default_limit
        self._default_sql_table = default_sql_table

    def prepare_execution_plan(
        self,
        plan: SemanticQueryPlan,
        sql_hints: Mapping[str, Any] | None = None,
    ) -> SemanticQueryPlan:
        """Funde hints executáveis (tabela/colunas/limit) para :func:`~compile_select`."""
        return merge_executable_hints(
            plan,
            self._allowlist,
            sql_hints,
            default_limit=self.default_limit,
            default_sql_table=self._default_sql_table,
        )

    async def execute_plan(
        self,
        plan: SemanticQueryPlan,
        *,
        sql_hints: Mapping[str, Any] | None = None,
    ) -> AnalyticsResult:
        """Executa um :class:`SemanticQueryPlan` já construído (sem ``IntentResolver``)."""
        plan = self.prepare_execution_plan(plan, sql_hints)
        compiled = compile_select(plan, self._allowlist, default_limit=self.default_limit)
        rows = await self._mysql.select(compiled.sql, params=compiled.params)
        return AnalyticsResult(
            plan=plan,
            sql=compiled.sql,
            rows=rows,
            row_count=len(rows),
        )

    async def execute_template(
        self,
        template: QueryTemplate,
        params: dict[str, Any],
        *,
        plan: SemanticQueryPlan | None = None,
    ) -> AnalyticsResult:
        """Executa um QueryTemplate parametrizado directamente (sem compilador)."""
        param_values = tuple(params[k] for k in template.parameters)
        rows = await self._mysql.select(template.sql, params=param_values)
        if plan is None:
            plan = SemanticQueryPlan(
                intent_slug=f"template.{template.slug}",
                strategy=RetrievalStrategy.BROKER_FANOUT,
                hints={"template_slug": template.slug, "template_params": params},
            )
        else:
            plan = replace(
                plan,
                hints={
                    **dict(plan.hints),
                    "template_slug": template.slug,
                    "template_params": params,
                },
            )
        return AnalyticsResult(
            plan=plan,
            sql=template.sql,
            rows=rows,
            row_count=len(rows),
        )

    async def execute(
        self,
        query_text: str,
        intent_slug: str = "analytics.generic",
        correlation_id: str | None = None,
        *,
        sql_hints: Mapping[str, Any] | None = None,
    ) -> AnalyticsResult:
        cognitive = IntentResolver().resolve(query_text)
        plan = build_query_plan(
            cognitive,
            query_text=query_text,
            intent_slug=intent_slug,
            correlation_id=correlation_id,
        )
        plan = self.prepare_execution_plan(plan, sql_hints)
        compiled = compile_select(plan, self._allowlist, default_limit=self.default_limit)
        rows = await self._mysql.select(compiled.sql, params=compiled.params)
        return AnalyticsResult(
            plan=plan,
            sql=compiled.sql,
            rows=rows,
            row_count=len(rows),
        )
