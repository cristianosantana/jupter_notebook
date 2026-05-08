"""
Orquestrador: texto → Planner → compilador SQL seguro → execução MySQL (Fase 1.5).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from orion_mcp_v3.broker.planner import plan_from_natural_language
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist, compile_select
from orion_mcp_v3.connection_hub.mysql_backend import MysqlDatastoreClient
from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan

# Colunas mínimas por tabela quando o plano NL não traz `sql_columns`.
_DEFAULT_SQL_COLUMNS: dict[str, tuple[str, ...]] = {
    "vendas": ("id", "data_venda", "valor", "status"),
    "clientes": ("id", "nome", "email", "concessionaria_id"),
    "os": ("id", "data_criacao", "status", "concessionaria_id"),
    "servicos": ("id", "nome", "preco_custo", "categoria_id"),
    "funcionarios": ("id", "nome", "cargo", "concessionaria_id"),
    "concessionarias": ("id", "nome", "cidade", "estado"),
}


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
        default_sql_table: str = "vendas",
    ) -> None:
        self._mysql = mysql_client
        self._allowlist = allowlist
        self.default_limit = default_limit
        self._default_sql_table = default_sql_table

    def _merge_executable_hints(
        self,
        plan: SemanticQueryPlan,
        sql_hints: Mapping[str, Any] | None,
    ) -> SemanticQueryPlan:
        hints: dict[str, Any] = dict(plan.hints)
        if sql_hints:
            hints.update(sql_hints)

        table = hints.get("sql_table") or self._default_sql_table
        hints["sql_table"] = table

        if "sql_columns" not in hints:
            cols = _DEFAULT_SQL_COLUMNS.get(table)
            if cols is None:
                allowed = self._allowlist.columns_by_table.get(table)
                if not allowed:
                    raise ValueError(f"tabela desconhecida na allowlist: {table!r}")
                cols = tuple(sorted(allowed))[:8]
            hints["sql_columns"] = cols

        if "limit" not in hints and "sql_limit" not in hints:
            hints["limit"] = self.default_limit

        return replace(plan, hints=hints)

    async def execute(
        self,
        query_text: str,
        intent_slug: str = "analytics.generic",
        correlation_id: str | None = None,
        *,
        sql_hints: Mapping[str, Any] | None = None,
    ) -> AnalyticsResult:
        plan = plan_from_natural_language(
            query_text,
            intent_slug=intent_slug,
            correlation_id=correlation_id,
        )
        plan = self._merge_executable_hints(plan, sql_hints)
        compiled = compile_select(plan, self._allowlist, default_limit=self.default_limit)
        rows = await self._mysql.select(compiled.sql, params=compiled.params)
        return AnalyticsResult(
            plan=plan,
            sql=compiled.sql,
            rows=rows,
            row_count=len(rows),
        )
