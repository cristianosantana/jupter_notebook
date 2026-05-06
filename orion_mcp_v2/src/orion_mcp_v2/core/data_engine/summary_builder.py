from __future__ import annotations

from typing import Any


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.strip():
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None
    return None


def _group_key(v: Any) -> str:
    if v is None:
        return "(null)"
    return str(v)[:120]


def build_summary(
    rows: list[dict[str, Any]],
    schema: dict[str, Any],
    *,
    top_n: int = 5,
    max_groupings: int = 3,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "row_count": len(rows),
        "metrics": {},
        "groupings": {},
        "distribution": {},
    }
    if not rows:
        return out

    numeric = [c for c in schema.get("numeric", []) if isinstance(c, str)]
    categorical = [c for c in schema.get("categorical", []) if isinstance(c, str)]
    primary = schema.get("primary_metric")

    metrics: dict[str, Any] = {}
    for col in numeric:
        vals: list[float] = []
        for r in rows:
            x = _to_float(r.get(col))
            if x is not None:
                vals.append(x)
        if not vals:
            continue
        metrics[col] = {
            "sum": round(sum(vals), 6),
            "avg": round(sum(vals) / len(vals), 6),
            "min": round(min(vals), 6),
            "max": round(max(vals), 6),
        }
    out["metrics"] = metrics

    pm = primary if isinstance(primary, str) and primary in numeric else (numeric[0] if numeric else None)
    group_cols = [c for c in categorical if c != pm][:max_groupings]

    groupings: dict[str, list[dict[str, Any]]] = {}
    for gcol in group_cols:
        agg: dict[str, list[float]] = {}
        counts: dict[str, int] = {}
        for r in rows:
            k = _group_key(r.get(gcol))
            counts[k] = counts.get(k, 0) + 1
            if pm:
                x = _to_float(r.get(pm))
                if x is not None:
                    agg.setdefault(k, []).append(x)
        if pm:
            ranked = sorted(
                counts.keys(),
                key=lambda kk: sum(agg.get(kk, []) or [0.0]),
                reverse=True,
            )[:top_n]
            groupings[gcol] = [
                {
                    "key": kk,
                    "count": counts[kk],
                    "value": round(sum(agg.get(kk, [])), 6) if agg.get(kk) else 0.0,
                }
                for kk in ranked
            ]
        else:
            ranked = sorted(counts.keys(), key=lambda kk: counts[kk], reverse=True)[:top_n]
            groupings[gcol] = [{"key": kk, "count": counts[kk]} for kk in ranked]
    out["groupings"] = groupings

    if pm and pm in metrics:
        vals = []
        for r in rows:
            x = _to_float(r.get(pm))
            if x is not None:
                vals.append(x)
        if len(vals) > 1:
            avg = sum(vals) / len(vals)
            var = sum((x - avg) ** 2 for x in vals) / len(vals)
            spread = var**0.5
            out["distribution"][pm] = {"avg": round(avg, 6), "spread": round(spread, 6)}
        elif vals:
            out["distribution"][pm] = {"avg": round(vals[0], 6), "spread": 0.0}

    return out
