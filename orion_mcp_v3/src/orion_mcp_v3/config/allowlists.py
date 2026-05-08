"""Allowlists de SQL analítico (Fase 1.5) — tabelas e colunas permitidas para o compilador."""

from __future__ import annotations

from orion_mcp_v3.broker.sql_compiler import SqlAllowlist

_ANALYTICS_TABLES: frozenset[str] = frozenset(
    {
        "clientes",
        "os",
        "os_servicos",
        "funcionarios",
        "concessionarias",
    }
)

_ANALYTICS_COLUMNS: dict[str, frozenset[str]] = {
    "clientes": frozenset(
        {
            "id",
            "nome",
            "created_at",
            "paga",
        }
    ),
    "os": frozenset(
        {
            "id",
            "cliente_id",
            "concessionaria_id",
            "created_at",
            "paga",
        }
    ),
    "os_servicos": frozenset(
        {
            "id",
            "valor_venda_real",
        }
    ),
    "funcionarios": frozenset(
        {
            "id",
            "nome",
        }
    ),
    "concessionarias": frozenset(
        {
            "id",
            "nome",
        }
    ),
}

ANALYTICS_ALLOWLIST = SqlAllowlist(
    tables=_ANALYTICS_TABLES,
    columns_by_table={k: v for k, v in _ANALYTICS_COLUMNS.items()},
)
