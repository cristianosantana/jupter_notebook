from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_NUMERIC_HINT = re.compile(
    r"(receita|faturamento|valor|total|quantidade|qtd|count|sum|media|ticket|volume|taxa|percent)",
    re.I,
)
_TEMPORAL_HINT = re.compile(
    r"(data|date|periodo|period|mes|ano|timestamp|hora|time)",
    re.I,
)


def _is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str) and v.strip():
        try:
            float(v.replace(",", "."))
            return True
        except ValueError:
            return False
    return False


def _is_temporal_value(v: Any) -> bool:
    if isinstance(v, (datetime, date)):
        return True
    if not isinstance(v, str) or not v.strip():
        return False
    s = v.strip()[:32]
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return True
    if re.match(r"^\d{2}/\d{2}/\d{4}", s):
        return True
    return False


def infer_schema(rows: list[dict[str, Any]], *, sample_size: int = 200) -> dict[str, Any]:
    if not rows:
        return {
            "numeric": [],
            "categorical": [],
            "temporal": [],
            "primary_metric": None,
        }
    keys = list(rows[0].keys())
    n = min(len(rows), sample_size)
    sample = rows[:n]

    numeric: list[str] = []
    categorical: list[str] = []
    temporal: list[str] = []

    for col in keys:
        vals = [r.get(col) for r in sample if r.get(col) is not None]
        if not vals:
            categorical.append(col)
            continue
        t_temp = sum(1 for v in vals if _is_temporal_value(v))
        t_num = sum(1 for v in vals if _is_number(v))
        ratio_temp = t_temp / len(vals)
        ratio_num = t_num / len(vals)
        if ratio_temp >= 0.6 or (_TEMPORAL_HINT.search(col) and ratio_temp >= 0.3):
            temporal.append(col)
        elif ratio_num >= 0.7:
            numeric.append(col)
        else:
            categorical.append(col)

    primary: str | None = None
    for col in numeric:
        if _NUMERIC_HINT.search(col):
            primary = col
            break
    if primary is None and numeric:
        primary = numeric[0]

    return {
        "numeric": numeric,
        "categorical": categorical,
        "temporal": temporal,
        "primary_metric": primary,
    }
