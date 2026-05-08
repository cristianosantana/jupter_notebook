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
    # Backticks — dialecto MySQL (asyncmy); aspas duplas falham em modo SQL típico.
    return f"`{name}`"


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


def _joins_from_hints(hints: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = hints.get("sql_joins")
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise SqlCompilationError("sql_joins deve ser uma sequência")
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise SqlCompilationError("cada JOIN deve ser um mapeamento")
        out.append(dict(item))
    return out


def _valid_alias(name: str) -> bool:
    return bool(name) and name.replace("_", "").isalnum()


def _column_allowed_for_qualifier(
    allowlist: SqlAllowlist,
    *,
    qualifier: str,
    column: str,
    base_table: str,
    alias_to_table: Mapping[str, str],
) -> bool:
    if qualifier == base_table:
        return column in allowlist.columns_by_table.get(base_table, frozenset())
    resolved = alias_to_table.get(qualifier)
    if not resolved:
        return False
    return column in allowlist.columns_by_table.get(resolved, frozenset())


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
    * ``sql_joins``: opcional, sequência de
      ``{join_table, alias, on_left_column, on_right_column}`` (JOIN à tabela base ``sql_table``)
    * Filtros podem ter ``qualifier`` (nome da tabela base ou alias do JOIN) para colunas qualificadas
    * ``sql_order_by`` pode ter ``qualifier`` quando há JOIN
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

    join_rows = _joins_from_hints(h)
    alias_to_table: dict[str, str] = {}
    join_sql_parts: list[str] = []
    for jr in join_rows:
        jt = jr.get("join_table")
        alias = jr.get("alias")
        left_c = jr.get("on_left_column")
        right_c = jr.get("on_right_column")
        if not isinstance(jt, str) or not isinstance(alias, str):
            raise SqlCompilationError("JOIN requer join_table e alias (strings)")
        if not isinstance(left_c, str) or not isinstance(right_c, str):
            raise SqlCompilationError("JOIN requer on_left_column e on_right_column")
        jt = _validate_table(allowlist, jt.strip())
        if not _valid_alias(alias.strip()):
            raise SqlCompilationError(f"alias de JOIN inválido: {alias!r}")
        alias = alias.strip()
        if alias == table:
            raise SqlCompilationError("alias de JOIN não pode coincidir com a tabela base")
        _validate_columns(allowlist, table, (left_c,))
        _validate_columns(allowlist, jt, (right_c,))
        if alias in alias_to_table:
            raise SqlCompilationError(f"alias duplicado no JOIN: {alias!r}")
        alias_to_table[alias] = jt
        join_sql_parts.append(
            f" JOIN {_quote_ident(jt)} AS {_quote_ident(alias)} ON "
            f"{_quote_ident(alias)}.{_quote_ident(right_c)} = {_quote_ident(table)}.{_quote_ident(left_c)}"
        )

    has_join = bool(join_sql_parts)
    if has_join:
        select_list = ", ".join(f"{_quote_ident(table)}.{_quote_ident(c)}" for c in columns)
    else:
        select_list = ", ".join(_quote_ident(c) for c in columns)

    from_clause = _quote_ident(table) + "".join(join_sql_parts)

    params: list[Any] = []
    where_parts: list[str] = []

    for filt in _filters_from_hints(h):
        col = filt.get("column")
        op = filt.get("op")
        val = filt.get("value")
        qual = filt.get("qualifier")
        if not isinstance(col, str):
            raise SqlCompilationError("filtro requer column (string)")
        if op not in ("=", "!=", "<", ">", "<=", ">=", "IN"):
            raise SqlCompilationError(f"operador SQL não suportado: {op!r}")

        if qual is not None:
            if not isinstance(qual, str) or not _valid_alias(qual.strip()):
                raise SqlCompilationError(f"qualifier inválido: {qual!r}")
            qkey = qual.strip()
            if has_join:
                if qkey != table and qkey not in alias_to_table:
                    raise SqlCompilationError(f"qualifier desconhecido: {qkey!r}")
            elif qkey != table:
                raise SqlCompilationError("qualifier só é permitido com sql_joins ou igual à tabela base")
            if not _column_allowed_for_qualifier(
                allowlist,
                qualifier=qkey,
                column=col,
                base_table=table,
                alias_to_table=alias_to_table,
            ):
                raise SqlCompilationError(f"filtro em coluna inválida para {qkey}.{col}")
            qcol = f"{_quote_ident(qkey)}.{_quote_ident(col)}"
        else:
            if has_join:
                raise SqlCompilationError("com JOIN, cada filtro deve definir qualifier (tabela base ou alias)")
            if col not in allowlist.columns_by_table.get(table, frozenset()):
                raise SqlCompilationError(f"filtro em coluna inválida: {col!r}")
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
        oqual = ob.get("qualifier")
        if direction not in ("asc", "desc"):
            raise SqlCompilationError("direction deve ser asc ou desc")
        if not isinstance(ocol, str):
            raise SqlCompilationError("ORDER BY requer column")
        if has_join:
            if oqual is None:
                raise SqlCompilationError("com JOIN, sql_order_by deve incluir qualifier")
            if not isinstance(oqual, str) or not _valid_alias(oqual.strip()):
                raise SqlCompilationError(f"ORDER BY qualifier inválido: {oqual!r}")
            oqk = oqual.strip()
            if oqk != table and oqk not in alias_to_table:
                raise SqlCompilationError(f"ORDER BY qualifier desconhecido: {oqk!r}")
            if not _column_allowed_for_qualifier(
                allowlist,
                qualifier=oqk,
                column=ocol,
                base_table=table,
                alias_to_table=alias_to_table,
            ):
                raise SqlCompilationError(f"ORDER BY coluna inválida: {oqk}.{ocol}")
            order_clause = f" ORDER BY {_quote_ident(oqk)}.{_quote_ident(ocol)} {direction.upper()}"
        else:
            if ocol not in allowlist.columns_by_table.get(table, frozenset()):
                raise SqlCompilationError(f"ORDER BY coluna inválida: {ocol!r}")
            order_clause = f" ORDER BY {_quote_ident(ocol)} {direction.upper()}"

    sql = (
        f"SELECT {select_list} FROM {from_clause}"
        f"{where_clause}{order_clause} LIMIT %s"
    )
    params.append(limit)
    return CompiledSql(sql=sql, params=tuple(params))
