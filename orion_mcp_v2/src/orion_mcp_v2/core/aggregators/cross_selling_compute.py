from __future__ import annotations

from typing import Any

import pandas as pd


def compute_cross_selling_aggregate(rows: list[dict[str, Any]], *, top_n: int = 20) -> dict[str, Any]:
    """
    Agrega pares (servico_A_id, servico_B_id) com SUM de frequência e receita,
    ordena por receita desc e devolve top-N + totais e concentração da receita no top-N.
    """
    if not rows:
        return {
            "top_pairs": [],
            "totals": {
                "pairs_distinct": 0,
                "receita_total": 0.0,
                "frequencia_total": 0,
            },
            "concentration_top_n_pct_receita": 0.0,
            "top_n": top_n,
        }

    df = pd.DataFrame(rows)
    g = (
        df.groupby(["servico_A_id", "servico_B_id"], as_index=False)
        .agg(frequencia_combo=("frequencia_combo", "sum"), receita_combo=("receita_combo", "sum"))
        .sort_values("receita_combo", ascending=False)
    )

    receita_total = float(g["receita_combo"].sum())
    freq_total = int(g["frequencia_combo"].sum())
    pairs_distinct = int(len(g))

    cap = max(1, min(500, int(top_n)))
    head = g.head(cap)
    receita_top = float(head["receita_combo"].sum())
    conc_pct = (100.0 * receita_top / receita_total) if receita_total > 0 else 0.0

    top_pairs: list[dict[str, Any]] = []
    for _, row in head.iterrows():
        top_pairs.append(
            {
                "servico_A_id": int(row["servico_A_id"]),
                "servico_B_id": int(row["servico_B_id"]),
                "frequencia_combo": int(row["frequencia_combo"]),
                "receita_combo": float(row["receita_combo"]),
            }
        )

    return {
        "top_pairs": top_pairs,
        "totals": {
            "pairs_distinct": pairs_distinct,
            "receita_total": receita_total,
            "frequencia_total": freq_total,
        },
        "concentration_top_n_pct_receita": round(conc_pct, 2),
        "top_n": cap,
    }
