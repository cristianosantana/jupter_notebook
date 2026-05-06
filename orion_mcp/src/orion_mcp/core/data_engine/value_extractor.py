from __future__ import annotations

from typing import Any


def extract_insights(summary: dict[str, Any], *, max_insights: int = 5) -> list[str]:
    insights: list[str] = []
    row_count = int(summary.get("row_count") or 0)
    if row_count == 0:
        return ["Dataset vazio (row_count=0)."]

    metrics = summary.get("metrics") or {}
    groupings = summary.get("groupings") or {}
    distribution = summary.get("distribution") or {}

    for gcol, items in groupings.items():
        if not isinstance(items, list) or len(items) < 2:
            continue
        total_val = sum(float(x.get("value") or 0) for x in items if isinstance(x, dict))
        if total_val <= 0:
            tops = [x for x in items if isinstance(x, dict)][:3]
            if tops and all("count" in x for x in tops):
                s = sum(int(x["count"]) for x in tops)
                if row_count > 0 and s > 0:
                    pct = 100.0 * s / row_count
                    insights.append(
                        f"Top 3 em {gcol} concentram ~{pct:.1f}% das linhas (por contagem)."
                    )
            break
        top3 = items[:3]
        t3 = sum(float(x.get("value") or 0) for x in top3 if isinstance(x, dict))
        if total_val > 0:
            insights.append(
                f"Top 3 em {gcol} representam ~{100.0 * t3 / total_val:.1f}% do total agregado (value)."
            )
        break

    for gcol, items in groupings.items():
        if not isinstance(items, list) or not items:
            continue
        first = float(items[0].get("value") or items[0].get("count") or 0)
        rest = items[1:]
        if not rest:
            continue
        denom = sum(float(x.get("value") or x.get("count") or 0) for x in items if isinstance(x, dict)) or 1.0
        if first / denom >= 0.65:
            insights.append(f"Dominância: {gcol}={items[0].get('key')} concentra a maior parte (~{100*first/denom:.0f}%).")
            break

    for col, m in metrics.items():
        if not isinstance(m, dict):
            continue
        avg = float(m.get("avg") or 0)
        mx = float(m.get("max") or 0)
        if avg > 0 and mx / avg >= 3.0:
            insights.append(f"Outliers em {col}: máximo {mx:.4g} é {mx/avg:.1f}x a média.")
            break

    if len(groupings) == 1:
        items = next(iter(groupings.values()))
        if isinstance(items, list) and len(items) >= 3:
            shares = []
            total = sum(float(x.get("count") or 0) for x in items if isinstance(x, dict)) or 1
            for x in items[:5]:
                if isinstance(x, dict) and "count" in x:
                    shares.append(int(x["count"]) / total)
            if shares and shares[0] >= 0.5:
                insights.append("Distribuição concentrada: o primeiro grupo domina a contagem.")

    for col, dist in distribution.items():
        if isinstance(dist, dict):
            sp = float(dist.get("spread") or 0)
            av = float(dist.get("avg") or 0)
            if av != 0 and sp / abs(av) < 0.05 and sp >= 0:
                insights.append(f"{col}: dispersão baixa face à média (pouca variabilidade).")
            break

    if len(insights) < max_insights and metrics:
        col = next(iter(metrics.keys()))
        m = metrics[col]
        if isinstance(m, dict):
            insights.append(
                f"Resumo numérico {col}: min={m.get('min')} max={m.get('max')} avg={m.get('avg')}."
            )

    return insights[:max_insights]
