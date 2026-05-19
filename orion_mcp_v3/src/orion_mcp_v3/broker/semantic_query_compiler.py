"""
Compilador DSL do :class:`~SemanticQueryPlan` (§13 ORDEM_IMPLEMENTAÇÃO).

Funde *hints* executáveis, valida contra :class:`~SqlAllowlist` via :func:`compile_select`
(sem execução SQL) e devolve o plano fundido + SQL parametrizado.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from orion_mcp_v3.broker.sql_compiler import CompiledSql, SqlAllowlist, SqlCompilationError, compile_select
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy, SemanticQueryPlan

# Colunas mínimas por tabela quando o plano não traz ``sql_columns`` (alinhado ao executor).
_DEFAULT_SQL_COLUMNS: dict[str, tuple[str, ...]] = {
    "clientes": ("id", "nome", "created_at"),
    "os": ("id", "cliente_id", "concessionaria_id", "created_at"),
    "os_servicos": ("id", "os_id", "servico_id", "valor_venda_real", "created_at"),
    "funcionarios": ("id", "nome", "created_at"),
    "concessionarias": ("id", "nome", "created_at"),
}

_DEFAULT_OS_SQL_HINTS: dict[str, Any] = {
    "sql_joins": (
        {
            "join_table": "clientes",
            "alias": "cli",
            "on_left_column": "cliente_id",
            "on_right_column": "id",
        },
        {
            "join_table": "os_servicos",
            "alias": "svc",
            "on_left_column": "id",
            "on_right_column": "os_id",
        },
    ),
    "sql_columns": (
        {"qualifier": "os", "column": "cliente_id"},
        {
            "agg": "SUM",
            "qualifier": "svc",
            "column": "valor_venda_real",
            "alias": "total_faturamento",
        },
    ),
    "sql_group_by": ({"qualifier": "os", "column": "cliente_id"},),
    "sql_filters": (
        {"qualifier": "os", "column": "paga", "op": "=", "value": 1},
        {"qualifier": "os", "column": "created_at", "op": ">=", "value": "2026-01-01"},
    ),
    "sql_order_by": {"direction": "desc", "alias": "total_faturamento"},
    "sql_omit_limit": False,
}


def merge_executable_hints(
    plan: SemanticQueryPlan,
    allowlist: SqlAllowlist,
    sql_hints: Mapping[str, Any] | None = None,
    *,
    default_limit: int = 1000,
    default_sql_table: str = "os",
) -> SemanticQueryPlan:
    """
    Injeta tabela/colunas/limit por defeito para o compilador SQL — mesmo contrato que
    :meth:`AnalyticsExecutor.prepare_execution_plan`.
    """
    hints: dict[str, Any] = dict(plan.hints)
    if sql_hints:
        hints.update(sql_hints)

    table = hints.get("sql_table") or default_sql_table
    hints["sql_table"] = table

    if "sql_columns" not in hints:
        cols = _DEFAULT_SQL_COLUMNS.get(table)
        if cols is None:
            allowed = allowlist.columns_by_table.get(table)
            if not allowed:
                raise ValueError(f"tabela desconhecida na allowlist: {table!r}")
            cols = tuple(sorted(allowed))[:8]
        hints["sql_columns"] = cols

    if table == "os" and "sql_joins" not in hints:
        hints.update(_DEFAULT_OS_SQL_HINTS)
        tn = hints.get("top_n")
        if tn is not None:
            try:
                hints["limit"] = max(1, int(tn))
            except (TypeError, ValueError):
                hints["limit"] = 5
        else:
            hints.setdefault("limit", 5)

    if "limit" not in hints and "sql_limit" not in hints and not hints.get("sql_omit_limit"):
        hints["limit"] = default_limit

    return replace(plan, hints=hints)


def validate_semantic_hints_surface(
    hints: Mapping[str, Any],
    allowlist: SqlAllowlist,
    *,
    default_sql_table: str = "os",
) -> None:
    """
    Validação superficial pré-compilação: tabelas referenciadas existem na allowlist.

    Regras completas de colunas/JOIN ficam em :func:`compile_select`.
    """
    table = hints.get("sql_table") or default_sql_table
    if table not in allowlist.tables:
        raise SqlCompilationError(f"tabela base não permitida: {table!r}")

    joins = hints.get("sql_joins") or ()
    for j in joins:
        if not isinstance(j, Mapping):
            continue
        jt = j.get("join_table")
        if jt and jt not in allowlist.tables:
            raise SqlCompilationError(f"JOIN para tabela não permitida: {jt!r}")

    if hints.get("aggregation_kind") == "ranking" or hints.get("analytics_strategy") == AnalyticsStrategy.RANKING.value:
        if not hints.get("rank_dimension"):
            raise SqlCompilationError("ranking requer hint rank_dimension")


@dataclass(frozen=True, slots=True)
class SemanticQueryCompilationResult:
    """Plano fundido + SQL compilado (validação via compilador allowlisted)."""

    merged_plan: SemanticQueryPlan
    compiled: CompiledSql


def compile_semantic_query_plan(
    plan: SemanticQueryPlan,
    allowlist: SqlAllowlist,
    *,
    default_limit: int = 1000,
    default_sql_table: str = "os",
    sql_hints: Mapping[str, Any] | None = None,
) -> SemanticQueryCompilationResult:
    """
    Merge → validação superficial → :func:`compile_select` (camada de validação + allowlist).
    """
    merged = merge_executable_hints(
        plan,
        allowlist,
        sql_hints,
        default_limit=default_limit,
        default_sql_table=default_sql_table,
    )
    validate_semantic_hints_surface(merged.hints, allowlist, default_sql_table=default_sql_table)
    compiled = compile_select(merged, allowlist, default_limit=default_limit)
    return SemanticQueryCompilationResult(merged_plan=merged, compiled=compiled)
