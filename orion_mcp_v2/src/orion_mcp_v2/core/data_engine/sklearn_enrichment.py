"""
Pré-processamento opcional (Fase E): agregados para insumo textual ao LLM.

Uso recomendado em worker Celery para cargas pesadas; na API síncrona apenas resumos leves.
Nunca devolver matrizes completas ao prompt — só contagens, médias por grupo, top features.
"""

from __future__ import annotations

from typing import Any


def tabular_summary_light(rows: list[dict[str, Any]], *, max_columns: int = 32) -> dict[str, Any]:
    """Resumo mínimo sem sklearn; útil quando pandas não está instalado."""
    if not rows:
        return {"row_count": 0, "note": "sem linhas"}
    keys: set[str] = set()
    for r in rows[: min(500, len(rows))]:
        keys.update(r.keys())
    cols = sorted(keys)[:max_columns]
    return {"row_count": len(rows), "columns": cols, "sample_keys_only": True}


def tabular_summary_pandas(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Agregados compactos via pandas (opcional). Falha graciosamente sem dependência.
    """
    try:
        import pandas as pd
    except ImportError:
        return {**tabular_summary_light(rows), "pandas": False}

    if not rows:
        return {"row_count": 0, "pandas": True}
    df = pd.DataFrame(rows)
    try:
        desc = df.describe(include="all", datetime_is_numeric=True)
        desc_txt = desc.to_string(max_cols=12, max_rows=12)[:8000]
    except Exception:
        desc_txt = "(describe indisponível para este schema)"
    return {
        "row_count": int(len(df)),
        "pandas": True,
        "describe_excerpt": desc_txt,
        "dtypes": {c: str(t) for c, t in list(df.dtypes.items())[:24]},
    }


def isolation_forest_outlier_counts(rows: list[dict[str, Any]], *, column: str) -> dict[str, Any]:
    """
    Exemplo de uso sklearn em worker: contagens de outliers, não scores por linha completos.
    """
    try:
        import numpy as np
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return {"available": False, "note": "scikit-learn não instalado"}

    try:
        import pandas as pd
    except ImportError:
        return {"available": False, "note": "pandas não instalado"}

    if not rows or column not in rows[0]:
        return {"available": True, "outliers": 0, "note": "coluna ausente ou sem dados"}
    df = pd.DataFrame(rows)
    s = pd.to_numeric(df[column], errors="coerce").dropna()
    if len(s) < 5:
        return {"available": True, "outliers": 0, "note": "amostra numérica insuficiente"}
    X = np.asarray(s.values).reshape(-1, 1)
    pred = IsolationForest(random_state=0, contamination="auto").fit_predict(X)
    n_out = int((pred == -1).sum())
    return {"available": True, "outliers": n_out, "column": column, "n_numeric": int(len(s))}
