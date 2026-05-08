"""
Compilador mínimo SELECT → SQL (Fase 3.2).

SELECT seguro com identificadores validados por allowlist; LIMIT por defeito,
ou omitido quando ``sql_omit_limit`` está activo e não há ``limit`` / ``sql_limit`` explícitos.
Filtros só via estruturas (sem SQL cru do utilizador).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan

SqlOperator = Literal["=", "!=", "<", ">", "<=", ">=", "IN"]

_AGG_FUNCS: frozenset[str] = frozenset({"SUM", "COUNT", "AVG", "MIN", "MAX"})


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


def _qualified_pair_from_mapping(
    item: Mapping[str, Any],
    *,
    base_table: str,
    alias_to_table: Mapping[str, str],
    allowlist: SqlAllowlist,
) -> tuple[str, str]:
    qual = item.get("qualifier")
    col = item.get("column")
    if not isinstance(qual, str) or not isinstance(col, str):
        raise SqlCompilationError("coluna qualificada requer qualifier e column (strings)")
    qk = qual.strip()
    ck = col.strip()
    if not qk or not ck:
        raise SqlCompilationError("qualifier ou column vazio")
    if qk != base_table and qk not in alias_to_table:
        raise SqlCompilationError(f"qualifier desconhecido: {qk!r}")
    if not _column_allowed_for_qualifier(
        allowlist,
        qualifier=qk,
        column=ck,
        base_table=base_table,
        alias_to_table=alias_to_table,
    ):
        raise SqlCompilationError(f"coluna não permitida: {qk}.{ck}")
    return qk, ck


def _group_by_entries_from_hints(
    raw: Any,
    *,
    base_table: str,
    alias_to_table: Mapping[str, str],
    allowlist: SqlAllowlist,
) -> list[tuple[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise SqlCompilationError("sql_group_by deve ser uma sequência de mapeamentos")
    out: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise SqlCompilationError("sql_group_by: cada entrada deve ser mapeamento qualifier/column")
        out.append(_qualified_pair_from_mapping(item, base_table=base_table, alias_to_table=alias_to_table, allowlist=allowlist))
    return out


def _format_plain_select(
    qual: str,
    col: str,
    *,
    has_join: bool,
) -> str:
    if has_join:
        return f"{_quote_ident(qual)}.{_quote_ident(col)}"
    return _quote_ident(col)


def _build_select_list_sql(
    cols_raw: Sequence[Any],
    *,
    base_table: str,
    alias_to_table: Mapping[str, str],
    allowlist: SqlAllowlist,
    has_join: bool,
    group_keys: frozenset[tuple[str, str]],
) -> tuple[str, frozenset[tuple[str, str]]]:
    """
    Devolve o texto do SELECT e o conjunto de pares (qual, col) em colunas simples
    (sem agregação), para validação contra ``sql_group_by``.
    """
    has_join_effective = has_join or bool(alias_to_table)
    fragments: list[str] = []
    plain_selected: set[tuple[str, str]] = set()
    has_aggregate = False

    for item in cols_raw:
        if isinstance(item, str):
            col = item.strip()
            if not col:
                raise SqlCompilationError("nome de coluna vazio em sql_columns")
            _validate_columns(allowlist, base_table, (col,))
            plain_selected.add((base_table, col))
            fragments.append(_format_plain_select(base_table, col, has_join=has_join_effective))
        elif isinstance(item, Mapping):
            agg_raw = item.get("agg") or item.get("aggregate")
            if agg_raw is not None:
                has_aggregate = True
                fn = str(agg_raw).strip().upper()
                if fn not in _AGG_FUNCS:
                    raise SqlCompilationError(f"agregação não suportada: {fn!r}")
                alias_raw = item.get("alias") or item.get("as")
                if not isinstance(alias_raw, str) or not _valid_alias(alias_raw.strip()):
                    raise SqlCompilationError("agregação requer alias (identificador SQL válido)")
                alias = alias_raw.strip()
                if fn == "COUNT" and item.get("column") in (None, "*"):
                    raise SqlCompilationError("COUNT(*) não suportado neste compilador")
                qk, ck = _qualified_pair_from_mapping(item, base_table=base_table, alias_to_table=alias_to_table, allowlist=allowlist)
                inner = f"{_quote_ident(qk)}.{_quote_ident(ck)}"
                fragments.append(f"{fn}({inner}) AS {_quote_ident(alias)}")
            else:
                qk, ck = _qualified_pair_from_mapping(item, base_table=base_table, alias_to_table=alias_to_table, allowlist=allowlist)
                if not has_join_effective:
                    raise SqlCompilationError("colunas qualificadas em sql_columns exigem sql_joins")
                plain_selected.add((qk, ck))
                fragments.append(_format_plain_select(qk, ck, has_join=has_join_effective))
        else:
            raise SqlCompilationError(
                "sql_columns: cada entrada deve ser string, mapeamento qualifier/column ou agregação"
            )

    if group_keys:
        if plain_selected != set(group_keys):
            raise SqlCompilationError(
                "sql_group_by e colunas simples do SELECT devem coincidir exactamente"
            )
        if not has_aggregate:
            raise SqlCompilationError("GROUP BY exige pelo menos uma agregação no SELECT")

    return ", ".join(fragments), frozenset(plain_selected)


def compile_select(
    plan: SemanticQueryPlan,
    allowlist: SqlAllowlist,
    *,
    default_limit: int = 1000,
) -> CompiledSql:
    """
    Gera ``SELECT ... FROM ... WHERE ... ORDER BY ...`` e opcionalmente ``LIMIT n``.

    ``plan.hints`` esperados (MVP):

    * ``sql_table``: nome da tabela (allowlist)
    * ``sql_columns``: sequência de nomes da tabela base (strings) e/ou
      ``{"qualifier": "<alias ou tabela>", "column": "<nome>"}`` para colunas de JOINs
    * ``sql_filters``: opcional, lista de ``{column, op, value}`` com ``op`` em
      ``=``, ``!=``, ``<``, ``>``, ``<=``, ``>=``, ``IN`` (valor lista para IN)
    * ``sql_order_by``: opcional, ``{column, direction}`` com direction ``asc``/``desc``
    * ``sql_joins``: opcional, sequência de
      ``{join_table, alias, on_left_column, on_right_column}`` (JOIN à tabela base ``sql_table``)
    * Filtros podem ter ``qualifier`` (nome da tabela base ou alias do JOIN) para colunas qualificadas
    * ``sql_order_by`` pode ter ``qualifier`` quando há JOIN
    * ``limit`` ou ``sql_limit``: inteiro positivo (senão ``default_limit``)
    * ``sql_omit_limit``: se verdadeiro **e** não existir ``limit`` nem ``sql_limit`` nos hints,
      não gera cláusula ``LIMIT``
    * ``sql_group_by``: sequência de ``{qualifier, column}`` (deve coincidir com as colunas simples do SELECT)
    * agregação em ``sql_columns``: ``{agg, qualifier, column, alias}`` com ``agg`` ∈ SUM, COUNT, AVG, MIN, MAX
    * ``sql_order_by``: pode usar ``alias`` (nome do ``AS`` de uma agregação) em vez de ``column``/``qualifier``
    """
    h = dict(plan.hints)
    table_raw = h.get("sql_table")
    if not isinstance(table_raw, str) or not table_raw.strip():
        raise SqlCompilationError("hints['sql_table'] é obrigatório (string)")
    table = _validate_table(allowlist, table_raw.strip())

    cols_raw = h.get("sql_columns")
    if not isinstance(cols_raw, Sequence) or isinstance(cols_raw, (str, bytes)):
        raise SqlCompilationError("hints['sql_columns'] deve ser uma sequência")
    if not cols_raw:
        raise SqlCompilationError("hints['sql_columns'] não pode ser vazio")

    explicit_limit = "limit" in h or "sql_limit" in h
    omit_limit = bool(h.get("sql_omit_limit")) and not explicit_limit
    limit = 0
    if not omit_limit:
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

    group_entries = _group_by_entries_from_hints(
        h.get("sql_group_by"),
        base_table=table,
        alias_to_table=alias_to_table,
        allowlist=allowlist,
    )
    group_keys = frozenset(group_entries)

    select_list, _ = _build_select_list_sql(
        cols_raw,
        base_table=table,
        alias_to_table=alias_to_table,
        allowlist=allowlist,
        has_join=has_join,
        group_keys=group_keys,
    )

    hj = has_join or bool(alias_to_table)
    group_clause = ""
    if group_keys:
        gb_frags = [_format_plain_select(q, c, has_join=hj) for q, c in group_entries]
        group_clause = " GROUP BY " + ", ".join(gb_frags)

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
        direction = str(ob.get("direction", "asc")).lower()
        if direction not in ("asc", "desc"):
            raise SqlCompilationError("direction deve ser asc ou desc")
        oalias = ob.get("alias") or ob.get("as")
        if oalias is not None:
            if not isinstance(oalias, str) or not _valid_alias(oalias.strip()):
                raise SqlCompilationError("ORDER BY alias inválido")
            order_clause = f" ORDER BY {_quote_ident(oalias.strip())} {direction.upper()}"
        else:
            ocol = ob.get("column")
            oqual = ob.get("qualifier")
            if not isinstance(ocol, str):
                raise SqlCompilationError("ORDER BY requer column ou alias")
            if has_join:
                if oqual is None:
                    raise SqlCompilationError("com JOIN, sql_order_by deve incluir qualifier (ou alias)")
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

    sql = f"SELECT {select_list} FROM {from_clause}{where_clause}{group_clause}{order_clause}"
    if omit_limit:
        return CompiledSql(sql=sql, params=tuple(params))
    sql = f"{sql} LIMIT %s"
    params.append(limit)
    return CompiledSql(sql=sql, params=tuple(params))
