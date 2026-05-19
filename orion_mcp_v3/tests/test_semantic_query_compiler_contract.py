"""Contratos do compilador ``SemanticQueryPlan`` → SQL allowlisted."""

from __future__ import annotations

import pytest

from orion_mcp_v3.broker.planner import build_query_plan
from orion_mcp_v3.broker.semantic_query_compiler import (
    compile_semantic_query_plan,
    validate_semantic_hints_surface,
)
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist, SqlCompilationError
from orion_mcp_v3.runtime.intent_resolver import IntentResolver


def _allowlist() -> SqlAllowlist:
    return SqlAllowlist(
        tables=frozenset({"os", "clientes", "os_servicos", "concessionarias"}),
        columns_by_table={
            "os": frozenset({"id", "cliente_id", "created_at", "paga"}),
            "clientes": frozenset({"id", "nome"}),
            "os_servicos": frozenset({"id", "os_id", "valor_venda_real"}),
            "concessionarias": frozenset({"id", "nome"}),
        },
    )


def test_compile_ranking_plan_produces_sql() -> None:
    cognitive = IntentResolver().resolve("top 5 clientes por faturamento últimos 3 meses")
    plan = build_query_plan(cognitive, query_text="top 5 clientes por faturamento últimos 3 meses")
    al = _allowlist()
    result = compile_semantic_query_plan(plan, al, default_limit=100)
    assert result.compiled.sql
    assert "os" in result.compiled.sql.lower() or "clientes" in result.compiled.sql.lower()
    assert result.merged_plan.hints.get("rank_dimension") == "client"


def test_validate_rejects_unknown_join_table() -> None:
    cognitive = IntentResolver().resolve("faturamento")
    plan = build_query_plan(cognitive, query_text="faturamento")
    bad = {**dict(plan.hints), "sql_joins": ({"join_table": "tabela_inexistente", "alias": "x"},)}
    from dataclasses import replace

    from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan

    patched = replace(plan, hints=bad)
    with pytest.raises(SqlCompilationError, match="não permitida"):
        validate_semantic_hints_surface(patched.hints, _allowlist())
