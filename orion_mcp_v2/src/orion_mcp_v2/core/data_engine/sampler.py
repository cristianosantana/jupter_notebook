from __future__ import annotations

from typing import Any

from orion_mcp_v2.core.data_engine.summary_builder import _to_float


def build_sample(
    rows: list[dict[str, Any]],
    schema: dict[str, Any],
    *,
    max_total: int = 18,
    edge_each: int = 5,
) -> dict[str, Any]:
    pm = schema.get("primary_metric")
    if not isinstance(pm, str) or not rows:
        head = rows[: min(max_total, len(rows))]
        return {"top": head, "bottom": [], "outliers": [], "note": "sem métrica primária — top=primeiras linhas"}

    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        x = _to_float(r.get(pm))
        if x is None:
            continue
        scored.append((x, r))
    if not scored:
        head = rows[: min(max_total, len(rows))]
        return {"top": head, "bottom": [], "outliers": [], "note": "sem valores numéricos na métrica primária"}

    scored.sort(key=lambda t: t[0], reverse=True)
    top = [dict(r) for _, r in scored[:edge_each]]
    bottom = [dict(r) for _, r in scored[-edge_each:]]

    vals = [s for s, _ in scored]
    avg = sum(vals) / len(vals)
    var = sum((v - avg) ** 2 for v in vals) / max(1, len(vals))
    std = var**0.5
    thr = avg + 2 * std if std > 0 else avg * 2
    top_ids = {id(r) for _, r in scored[:edge_each]}
    outliers: list[dict[str, Any]] = []
    for v, r in scored:
        if id(r) in top_ids:
            continue
        if v >= thr:
            outliers.append(dict(r))
        if len(outliers) >= max(0, max_total - 2 * edge_each):
            break

    return {
        "top": top,
        "bottom": bottom,
        "outliers": outliers[: max(0, max_total - 2 * edge_each)],
        "primary_metric": pm,
    }
