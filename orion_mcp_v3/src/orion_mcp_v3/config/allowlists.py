"""Allowlists de SQL analítico (Fase 1.5) — tabelas e colunas permitidas para o compilador."""

from __future__ import annotations

from orion_mcp_v3.broker.sql_compiler import SqlAllowlist

_ANALYTICS_TABLES: frozenset[str] = frozenset(
    {
        "vendas",
        "clientes",
        "os",
        "servicos",
        "funcionarios",
        "concessionarias",
    }
)

_ANALYTICS_COLUMNS: dict[str, frozenset[str]] = {
    "vendas": frozenset(
        {
            "id",
            "os_id",
            "concessionaria_id",
            "vendedor_id",
            "servico_id",
            "valor",
            "data_venda",
            "status",
        }
    ),
    "clientes": frozenset(
        {
            "id",
            "nome",
            "email",
            "telefone",
            "concessionaria_id",
            "created_at",
        }
    ),
    "os": frozenset(
        {
            "id",
            "concessionaria_id",
            "vendedor_id",
            "status",
            "data_criacao",
            "reaberta",
        }
    ),
    "servicos": frozenset(
        {
            "id",
            "nome",
            "categoria_id",
            "preco_custo",
            "descricao",
        }
    ),
    "funcionarios": frozenset(
        {
            "id",
            "nome",
            "email",
            "cargo",
            "concessionaria_id",
            "ativo",
        }
    ),
    "concessionarias": frozenset(
        {
            "id",
            "nome",
            "cidade",
            "estado",
            "cnpj",
        }
    ),
}

ANALYTICS_ALLOWLIST = SqlAllowlist(
    tables=_ANALYTICS_TABLES,
    columns_by_table={k: v for k, v in _ANALYTICS_COLUMNS.items()},
)
