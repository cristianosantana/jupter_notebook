"""
Compilador mínimo SELECT → SQL (Fase 3.2).

Apenas SELECT, LIMIT obrigatório, identificadores validados por allowlist.
Filtros só via estruturas (sem SQL cru do utilizador).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan

SqlOperator = Literal["=", "!=", "<", ">", "<=", ">=", "IN"]


class SqlCompilationError(ValueError):
    """Erro de validação ou construção segura de SQL."""


@dataclass(frozen=True, slots=True)
class SqlAllowlist:
    """Tabelas e colunas permitidas por tabela."""

    tables: frozenset[str]
    columns_by_table: Mapping[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class CompiledSql:
    sql: str
    params: tuple[Any, ...]


def _quote_ident(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise SqlCompilationError(f"identificador inválido: {name!r}")
    return f'"{name}"'


def _validate_table(allowlist: SqlAllowlist, table: str) -> str:
    if table not in allowlist.tables:
        raise SqlCompilationError(f"tabela não permitida: {table!r}")
    return table


def _validate_columns(allowlist: SqlAllowlist, table: str, columns: Sequence[str]) -> tuple[str, ...]:
    allowed = allowlist.columns_by_table.get(table)
    if not allowed:
        raise SqlCompilationError(f"sem colunas allowlisted para {table!r}")
    if not columns:
        raise SqlCompilationError("pelo menos uma coluna SELECT é obrigatória")
    out: list[str] = []
    for c in columns:
        if c not in allowed:
            raise SqlCompilationError(f"coluna não permitida: {table}.{c}")
        out.append(c)
    return tuple(out)


def _filters_from_hints(hints: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = hints.get("sql_filters")
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise SqlCompilationError("sql_filters deve ser uma sequência de filtros")
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise SqlCompilationError("cada filtro deve ser um mapeamento")
        out.append(dict(item))
    return out


def compile_select(
    plan: SemanticQueryPlan,
    allowlist: SqlAllowlist,
    *,
    default_limit: int = 1000,
) -> CompiledSql:
    """
    Gera ``SELECT ... FROM ... WHERE ... ORDER BY ... LIMIT n``.

    ``plan.hints`` esperados (MVP):

    * ``sql_table``: nome da tabela (allowlist)
    * ``sql_columns``: sequência de nomes de colunas
    * ``sql_filters``: opcional, lista de ``{column, op, value}`` com ``op`` em
      ``=``, ``!=``, ``<``, ``>``, ``<=``, ``>=``, ``IN`` (valor lista para IN)
    * ``sql_order_by``: opcional, ``{column, direction}`` com direction ``asc``/``desc``
    * ``limit`` ou ``sql_limit``: inteiro positivo (senão ``default_limit``)
    """
    h = dict(plan.hints)
    table_raw = h.get("sql_table")
    if not isinstance(table_raw, str) or not table_raw.strip():
        raise SqlCompilationError("hints['sql_table'] é obrigatório (string)")
    table = _validate_table(allowlist, table_raw.strip())

    cols_raw = h.get("sql_columns")
    if not isinstance(cols_raw, Sequence) or isinstance(cols_raw, (str, bytes)):
        raise SqlCompilationError("hints['sql_columns'] deve ser uma sequência de strings")
    columns = _validate_columns(allowlist, table, [str(c) for c in cols_raw])

    limit_val = h.get("limit", h.get("sql_limit", default_limit))
    try:
        limit = int(limit_val)
    except (TypeError, ValueError) as e:
        raise SqlCompilationError("limit deve ser inteiro") from e
    if limit <= 0:
        raise SqlCompilationError("LIMIT deve ser > 0")

    select_list = ", ".join(_quote_ident(c) for c in columns)
    from_clause = _quote_ident(table)

    params: list[Any] = []
    where_parts: list[str] = []

    for filt in _filters_from_hints(h):
        col = filt.get("column")
        op = filt.get("op")
        val = filt.get("value")
        if not isinstance(col, str) or col not in allowlist.columns_by_table.get(table, frozenset()):
            raise SqlCompilationError(f"filtro em coluna inválida: {col!r}")
        if op not in ("=", "!=", "<", ">", "<=", ">=", "IN"):
            raise SqlCompilationError(f"operador SQL não suportado: {op!r}")
        qcol = _quote_ident(col)
        if op == "IN":
            if not isinstance(val, Sequence) or isinstance(val, (str, bytes)):
                raise SqlCompilationError("valor IN deve ser sequência")
            placeholders = ", ".join(["%s"] * len(val))
            params.extend(val)
            where_parts.append(f"{qcol} IN ({placeholders})")
        else:
            params.append(val)
            where_parts.append(f"{qcol} {op} %s")

    where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    order_clause = ""
    ob = h.get("sql_order_by")
    if ob is not None:
        if not isinstance(ob, Mapping):
            raise SqlCompilationError("sql_order_by deve ser um mapeamento")
        ocol = ob.get("column")
        direction = str(ob.get("direction", "asc")).lower()
        if direction not in ("asc", "desc"):
            raise SqlCompilationError("direction deve ser asc ou desc")
        if not isinstance(ocol, str) or ocol not in allowlist.columns_by_table.get(table, frozenset()):
            raise SqlCompilationError(f"ORDER BY coluna inválida: {ocol!r}")
        order_clause = f" ORDER BY {_quote_ident(ocol)} {direction.upper()}"

    sql = (
        f"SELECT {select_list} FROM {from_clause}"
        f"{where_clause}{order_clause} LIMIT %s"
    )
    params.append(limit)
    return CompiledSql(sql=sql, params=tuple(params))
