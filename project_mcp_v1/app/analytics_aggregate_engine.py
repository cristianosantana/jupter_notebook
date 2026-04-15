"""
Agregação determinística sobre listas de dict (resultados de run_analytics_query).
Executada no host — sem SQL dinâmico a partir do LLM.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def _as_float(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return float(x)
    s = str(x).strip().replace(" ", "")
    try:
        return float(s)
    except ValueError:
        pass
    try:
        if "," in s and s.count(",") == 1:
            return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        pass
    return None


def _row_passes_filters(row: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    for f in filters:
        col = str(f.get("column") or "")
        op = str(f.get("op") or "").lower()
        if not col or col not in row:
            return False
        val = row.get(col)
        fv = f.get("value")
        if op == "eq":
            if val != fv:
                return False
        elif op == "ne":
            if val == fv:
                return False
        elif op in ("gt", "gte", "lt", "lte"):
            a = _as_float(val)
            b = _as_float(fv)
            if a is None or b is None:
                return False
            if op == "gt" and not (a > b):
                return False
            if op == "gte" and not (a >= b):
                return False
            if op == "lt" and not (a < b):
                return False
            if op == "lte" and not (a <= b):
                return False
        elif op == "in":
            if not isinstance(fv, list):
                return False
            if val not in fv:
                return False
        else:
            return False
    return True


def _agg_name(op: str, column: str) -> str:
    o = op.lower().strip()
    c = column.strip()
    if o == "count" and not c:
        return "count_rows"
    return f"{o}_{c}"


def run_analytics_aggregate(
    rows: list[dict[str, Any]],
    *,
    group_by: list[str],
    aggregations: list[dict[str, str]],
    filters: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_dir: str = "desc",
    top_k: int | None = None,
    sample_only: bool = False,
    query_id: str = "",
) -> dict[str, Any]:
    """
    Agrega linhas em memória. `aggregations`: [{"column": "qtd_os", "op": "sum"}, ...].
    Ops: sum, mean, min, max, count (count com column vazio = linhas por grupo).
    """
    filters = filters or []
    if not rows:
        return {
            "ok": False,
            "error": "dataset_vazio",
            "rows": [],
        }
    sample_row = rows[0]
    for g in group_by:
        if g not in sample_row:
            return {"ok": False, "error": f"group_by_desconhecido:{g}"}
    for agg in aggregations:
        op = str(agg.get("op") or "").lower()
        col = str(agg.get("column") or "")
        if op not in ("sum", "mean", "min", "max", "count"):
            return {"ok": False, "error": f"op_invalida:{op}"}
        if op != "count" or col:
            if op == "count" and col and col not in sample_row:
                return {"ok": False, "error": f"coluna_agg_desconhecida:{col}"}
            if op != "count" and (not col or col not in sample_row):
                return {"ok": False, "error": f"coluna_agg_desconhecida:{col}"}
    for f in filters:
        c = str(f.get("column") or "")
        if not c or c not in sample_row:
            return {"ok": False, "error": f"filtro_coluna_desconhecida:{c}"}

    filtered = [r for r in rows if _row_passes_filters(r, filters)]

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in filtered:
        key = tuple(r.get(g) for g in group_by)
        groups[key].append(r)

    out_rows: list[dict[str, Any]] = []
    for key, g_rows in groups.items():
        out: dict[str, Any] = {}
        for i, g in enumerate(group_by):
            out[g] = key[i]
        for agg in aggregations:
            op = str(agg.get("op") or "").lower()
            col = str(agg.get("column") or "")
            name = _agg_name(op, col)
            if op == "count" and not col:
                out[name] = len(g_rows)
                continue
            if op == "count":
                out[name] = sum(1 for r in g_rows if r.get(col) is not None)
                continue
            nums = [_as_float(r.get(col)) for r in g_rows]
            nums_valid = [x for x in nums if x is not None]
            if op == "sum":
                out[name] = sum(nums_valid) if nums_valid else None
            elif op == "mean":
                out[name] = (
                    sum(nums_valid) / len(nums_valid) if nums_valid else None
                )
            elif op == "min":
                out[name] = min(nums_valid) if nums_valid else None
            elif op == "max":
                out[name] = max(nums_valid) if nums_valid else None
        out_rows.append(out)

    sd = (sort_dir or "desc").lower()
    rev = sd != "asc"
    if sort_by and sort_by in (out_rows[0] if out_rows else {}):
        try:
            out_rows.sort(
                key=lambda r: (r.get(sort_by) is None, r.get(sort_by)),
                reverse=rev,
            )
        except TypeError:
            out_rows.sort(key=lambda r: str(r.get(sort_by)), reverse=rev)
    elif aggregations:
        first_name = _agg_name(
            str(aggregations[0].get("op") or ""),
            str(aggregations[0].get("column") or ""),
        )
        if first_name in (out_rows[0] if out_rows else {}):
            out_rows.sort(
                key=lambda r: (r.get(first_name) is None, r.get(first_name)),
                reverse=rev,
            )

    if top_k is not None and top_k > 0:
        out_rows = out_rows[:top_k]

    result_columns = list(out_rows[0].keys()) if out_rows else list(group_by)
    note = (
        f"Agregação host sobre {len(filtered)} linhas (de {len(rows)} no dataset)"
        f"{'; amostra apenas (sample_only)' if sample_only else ''}."
    )
    return {
        "ok": True,
        "query_id": query_id,
        "group_by": group_by,
        "result_columns": result_columns,
        "rows": out_rows,
        "row_count": len(out_rows),
        "method_note": note,
        "sample_only": sample_only,
        "filtered_source_rows": len(filtered),
        "source_rows": len(rows),
    }
