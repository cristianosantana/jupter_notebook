"""
Orquestrador: texto → Planner → compilador SQL seguro → execução MySQL (Fase 1.5).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from orion_mcp_v3.broker.planner import build_query_plan
from orion_mcp_v3.runtime.intent_resolver import IntentResolver
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist, compile_select
from orion_mcp_v3.connection_hub.mysql_backend import MysqlDatastoreClient
from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan

# Colunas mínimas por tabela quando o plano NL não traz `sql_columns`.
_DEFAULT_SQL_COLUMNS: dict[str, tuple[str, ...]] = {
    "clientes": ("id", "nome", "created_at"),
    "os": ("id", "cliente_id", "concessionaria_id", "created_at"),
    "os_servicos": ("id", "os_id", "servico_id", "valor_venda_real", "created_at"),
    "funcionarios": ("id", "nome", "created_at"),
    "concessionarias": ("id", "nome", "created_at"),
}

# SELECT por defeito em ``os``: JOIN clientes + ``os.paga = 1``, ORDER BY ``os.id`` DESC (compilador SQL seguro).
_DEFAULT_OS_SQL_HINTS: dict[str, Any] = {
    "sql_joins": (
        {
            "join_table": "clientes",
            "alias": "cli",
            "on_left_column": "cliente_id",
            "on_right_column": "id",
        },
    ),
    "sql_filters": (
        {"qualifier": "os", "column": "paga", "op": "=", "value": 1},
    ),
    "sql_order_by": {"column": "id", "direction": "desc", "qualifier": "os"},
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
        default_sql_table: str = "os",
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

        if table == "os" and "sql_joins" not in hints:
            hints.update(_DEFAULT_OS_SQL_HINTS)

        if "limit" not in hints and "sql_limit" not in hints:
            hints["limit"] = self.default_limit

        return replace(plan, hints=hints)

    def prepare_execution_plan(
        self,
        plan: SemanticQueryPlan,
        sql_hints: Mapping[str, Any] | None = None,
    ) -> SemanticQueryPlan:
        """Funde hints executáveis (tabela/colunas/limit) para :func:`~compile_select`."""
        return self._merge_executable_hints(plan, sql_hints)

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
        plan = self._merge_executable_hints(plan, sql_hints)
        compiled = compile_select(plan, self._allowlist, default_limit=self.default_limit)
        rows = await self._mysql.select(compiled.sql, params=compiled.params)
        return AnalyticsResult(
            plan=plan,
            sql=compiled.sql,
            rows=rows,
            row_count=len(rows),
        )
