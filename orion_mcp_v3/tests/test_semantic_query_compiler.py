"""§13 — compilador SemanticQueryPlan + allowlist + validação superficial."""

from __future__ import annotations

import pytest

from orion_mcp_v3.broker import (
    SqlAllowlist,
    SqlCompilationError,
    compile_semantic_query_plan,
    validate_semantic_hints_surface,
)
from orion_mcp_v3.broker.planner import build_query_plan
from orion_mcp_v3.runtime.intent_resolver import IntentResolver


def _allowlist() -> SqlAllowlist:
    return SqlAllowlist(
        tables=frozenset({"clientes", "os", "os_servicos", "funcionarios", "concessionarias"}),
        columns_by_table={
            "clientes": frozenset({"id", "nome", "paga", "created_at"}),
            "os": frozenset({"id", "cliente_id", "concessionaria_id", "created_at", "paga"}),
            "os_servicos": frozenset({"id", "os_id", "servico_id", "valor_venda_real", "created_at"}),
            "funcionarios": frozenset({"id", "nome", "created_at"}),
            "concessionarias": frozenset({"id", "nome", "created_at"}),
        },
    )


def test_compile_semantic_query_plan_emits_select() -> None:
    cognitive = IntentResolver().resolve("mostre o top 5 clientes por faturamento")
    plan = build_query_plan(cognitive, query_text="mostre o top 5 clientes por faturamento")
    r = compile_semantic_query_plan(plan, _allowlist(), default_limit=1000)
    assert "SELECT" in r.compiled.sql.upper()
    assert len(r.compiled.params) >= 0


def test_validate_semantic_hints_surface_rejects_unknown_join_table() -> None:
    bad_hints = {
        "sql_table": "os",
        "sql_joins": ({"join_table": "tabela_inexistente", "alias": "x", "on_left_column": "id", "on_right_column": "id"},),
    }
    with pytest.raises(SqlCompilationError):
        validate_semantic_hints_surface(bad_hints, _allowlist())
