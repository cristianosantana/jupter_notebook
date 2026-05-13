"""Allowlists de SQL analítico (Fase 1.5) — tabelas e colunas permitidas para o compilador."""

from __future__ import annotations

from orion_mcp_v3.broker.sql_compiler import SqlAllowlist

_ANALYTICS_TABLES: frozenset[str] = frozenset(
    {
        "clientes",
        "os",
        "os_servicos",
        "os_tipos",
        "funcionarios",
        "concessionarias",
        "caixas",
        "caixa_tipos",
        "departamentos",
    }
)

_ANALYTICS_COLUMNS: dict[str, frozenset[str]] = {
    "clientes": frozenset(
        {
            "id",
            "nome",
            "created_at"
        }
    ),
    "os": frozenset(
        {
            "id",
            "cliente_id",
            "concessionaria_id",
            "os_tipo_id",
            "vendedor_id",
            "departamento_id",
            "created_at",
            "paga",
        }
    ),
    "os_servicos": frozenset(
        {
            "id",
            "os_id",
            "servico_id",
            "valor_venda_real",
            "created_at",
        }
    ),
    "funcionarios": frozenset(
        {
            "id",
            "nome",
            "created_at",
        }
    ),
    "concessionarias": frozenset(
        {
            "id",
            "nome",
            "created_at",
        }
    ),
    "os_tipos": frozenset(
        {
            "id",
            "ativo",
        }
    ),
    "caixas": frozenset(
        {
            "id",
            "os_id",
            "valor",
            "data_vencimento",
            "deleted_at",
            "caixa_tipo_id",
        }
    ),
    "caixa_tipos": frozenset(
        {
            "id",
            "nome",
        }
    ),
    "departamentos": frozenset(
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
