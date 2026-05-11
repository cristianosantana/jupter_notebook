"""
EvidenceBuilder: resultado SQL → :class:`~EvidenceBlock` com trends, baseline, variation,
anomalies, comparisons e pontuações de confiança/cobertura (Fase 2.4).
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from typing import Any

from orion_mcp_v3.broker.aggregators import time_series
from orion_mcp_v3.contracts.cognitive_artifact import (
    artifact_provenance_anchor,
    heuristic_confidence_from_volume,
)
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.runtime.provenance import CoverageInfo


def _float_values(rows: Sequence[Mapping[str, Any]], value_key: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        if value_key not in row:
            continue
        try:
            out.append(float(row[value_key]))
        except (TypeError, ValueError):
            continue
    return out


def _z_scores(values: Sequence[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mu = statistics.fmean(values)
    sigma = statistics.pstdev(values)
    if sigma <= 0:
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]


class EvidenceBuilder:
    """
    Constrói :class:`EvidenceBlock` a partir de linhas tabulares (ex.: saída MySQL).

    ``insights`` inclui ``trends``, ``baseline``, ``variation``, ``anomalies``, ``comparisons``;
    ``metrics`` inclui ``confidence_scoring`` e ``coverage_scoring``. ``time_key`` opcional
    habilita tendência temporal (grain mensal).
    """

    def __init__(
        self,
        *,
        z_threshold: float = 2.5,
        flat_relative_threshold: float = 0.02,
        source: str = "broker.evidence_builder",
    ) -> None:
        self._z_threshold = z_threshold
        self._flat_threshold = flat_relative_threshold
        self._source = source

    def build(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        value_key: str,
        time_key: str | None = None,
        grain: str = "month",
        id_key: str | None = "id",
    ) -> EvidenceBlock:
        vals = _float_values(rows, value_key)
        n = len(vals)
        row_total = len(rows)

        baseline: dict[str, Any]
        if not vals:
            baseline = {"mean": None, "median": None, "count": 0, "status": "no_numeric_values"}
        elif n == 1:
            baseline = {"mean": vals[0], "median": vals[0], "count": 1}
        else:
            baseline = {
                "mean": statistics.fmean(vals),
                "median": statistics.median(vals),
                "count": n,
            }

        variation: dict[str, Any]
        if n < 2:
            variation = {
                "stdev": 0.0,
                "coefficient_of_variation": None,
                "status": "insufficient_sample",
            }
        else:
            sd = statistics.pstdev(vals)
            mu = baseline.get("mean")
            cv = (sd / abs(mu)) if mu not in (None, 0.0) else None
            variation = {
                "stdev": sd,
                "coefficient_of_variation": cv,
                "min": min(vals),
                "max": max(vals),
            }

        trends: dict[str, Any] = {"status": "no_time_key"}
        periods_snapshot: list[dict[str, Any]] = []
        if time_key is not None and row_total > 0:
            periods_snapshot = time_series(rows, time_key=time_key, value_key=value_key, grain=grain)
            trends = self._compute_trends(periods_snapshot)

        comparisons = self._compute_comparisons(periods_snapshot)

        anomalies = self._compute_anomalies(rows, value_key, id_key)

        insights: dict[str, Any] = {
            "trends": trends,
            "baseline": baseline,
            "variation": variation,
            "anomalies": anomalies,
            "comparisons": comparisons,
        }

        summary = self._compose_summary_pt(insights, value_key)

        labels = {
            "rows_in": row_total,
            "numeric_values": n,
            "periods": len(periods_snapshot),
            "anomaly_hits": anomalies.get("count", 0),
        }
        cov = CoverageInfo(labels=labels, notes="evidence_builder.sql_rows")

        prov = (
            artifact_provenance_anchor(
                kind="evidence.block",
                step="build",
                source=self._source,
            ),
        )

        conf_base = heuristic_confidence_from_volume(n if n else row_total)
        conf_signal = 0.05 if trends.get("direction") in {"up", "down"} else 0.0
        conf_anom = min(0.05, 0.01 * float(anomalies.get("count", 0)))
        conf_cmp = 0.04 if comparisons.get("status") == "ok" else 0.0
        confidence = min(0.95, conf_base + conf_signal + conf_anom + conf_cmp)

        coverage_scoring = min(
            1.0,
            (n / max(row_total, 1)) * 0.65 + min(1.0, len(periods_snapshot) / 12.0) * 0.35,
        )

        metrics: dict[str, Any] = {
            "value_key": value_key,
            "time_key": time_key,
            "grain": grain if time_key else None,
            "numeric_samples": n,
            "input_rows": row_total,
            "confidence_scoring": {
                "volume_component": conf_base,
                "trend_component": conf_signal,
                "anomaly_component": conf_anom,
                "comparison_component": conf_cmp,
                "combined": confidence,
            },
            "coverage_scoring": coverage_scoring,
        }

        refs = tuple(str(a.get("ref", "")) for a in anomalies.get("examples", []) if a.get("ref") is not None)

        supporting = {}
        if periods_snapshot:
            supporting["periods_tail"] = periods_snapshot[-min(6, len(periods_snapshot)) :]

        return EvidenceBlock(
            summary=summary,
            insights=insights,
            metrics=metrics,
            confidence=confidence,
            coverage=cov,
            provenance=prov,
            sample_refs=refs,
            supporting_data=supporting,
        )

    def _compute_trends(self, periods: list[dict[str, Any]]) -> dict[str, Any]:
        if len(periods) < 2:
            return {
                "status": "insufficient_periods",
                "period_count": len(periods),
                "direction": "unknown",
            }

        totals = [float(p["total"]) for p in periods]
        last = totals[-1]
        prev = totals[-2]
        if prev == 0:
            pop = None
        else:
            pop = (last - prev) / abs(prev)

        direction = "flat"
        if pop is not None:
            if abs(pop) < self._flat_threshold:
                direction = "flat"
            elif pop > 0:
                direction = "up"
            else:
                direction = "down"

        first_half = statistics.fmean(totals[: len(totals) // 2]) if len(totals) >= 4 else None
        second_half = statistics.fmean(totals[len(totals) // 2 :]) if len(totals) >= 4 else None
        structural_shift = None
        if first_half is not None and second_half is not None and first_half != 0:
            structural_shift = (second_half - first_half) / abs(first_half)

        return {
            "status": "ok",
            "period_count": len(periods),
            "direction": direction,
            "period_over_period_change": pop,
            "last_period": periods[-1].get("period"),
            "previous_period": periods[-2].get("period"),
            "structural_shift_first_vs_second_half": structural_shift,
        }

    def _compute_comparisons(self, periods: list[dict[str, Any]]) -> dict[str, Any]:
        """Comparação extremo-a-extremo da série agregada (primeiro vs último período)."""
        if len(periods) < 2:
            return {"status": "insufficient_periods", "period_count": len(periods)}
        first, last = periods[0], periods[-1]
        a, b = float(first["total"]), float(last["total"])
        delta_abs = b - a
        delta_rel = (b - a) / abs(a) if a else None
        return {
            "status": "ok",
            "first_period": dict(first),
            "last_period": dict(last),
            "delta_abs": delta_abs,
            "delta_rel": delta_rel,
            "span_periods": len(periods),
        }

    def _compute_anomalies(
        self,
        rows: Sequence[Mapping[str, Any]],
        value_key: str,
        id_key: str | None,
    ) -> dict[str, Any]:
        indexed: list[tuple[int, float]] = []
        for i, row in enumerate(rows):
            if value_key not in row:
                continue
            try:
                indexed.append((i, float(row[value_key])))
            except (TypeError, ValueError):
                continue
        vals = [v for _, v in indexed]
        if len(vals) < 3:
            return {"count": 0, "examples": [], "status": "insufficient_sample"}

        zs = _z_scores(vals)
        hits: list[dict[str, Any]] = []
        for (row_idx, _), z in zip(indexed, zs):
            if abs(z) < self._z_threshold:
                continue
            row = dict(rows[row_idx])
            ref = row.get(id_key) if id_key and id_key in row else row_idx
            hits.append({"ref": ref, "z_score": round(z, 4), "value": row.get(value_key)})
            if len(hits) >= 8:
                break

        return {
            "count": len(hits),
            "examples": hits,
            "z_threshold": self._z_threshold,
            "status": "ok",
        }

    def _compose_summary_pt(self, insights: Mapping[str, Any], value_key: str) -> str:
        base = insights["baseline"]
        var = insights["variation"]
        tr = insights["trends"]
        an = insights["anomalies"]
        cmp_ = insights.get("comparisons", {})

        parts: list[str] = []
        if base.get("count"):
            parts.append(
                f"Métrica `{value_key}`: média {base.get('mean')!s}, mediana {base.get('median')!s} (n={base.get('count')})."
            )
        else:
            parts.append(f"Sem valores numéricos para `{value_key}`.")

        if var.get("coefficient_of_variation") is not None:
            parts.append(f"Coeficiente de variação ≈ {var['coefficient_of_variation']:.4f}.")

        if tr.get("status") == "ok" and tr.get("direction") != "unknown":
            pop = tr.get("period_over_period_change")
            pop_s = f"{100.0 * pop:.1f}%" if isinstance(pop, (int, float)) and pop is not None else "n/d"
            parts.append(
                f"Tendência mensal: {tr.get('direction')} (último vs penúltimo período: {pop_s})."
            )

        ac = int(an.get("count") or 0)
        if ac:
            parts.append(f"{ac} valor(es) com |z| ≥ {self._z_threshold} (possíveis anomalias).")

        if cmp_.get("status") == "ok" and cmp_.get("delta_rel") is not None:
            dr = float(cmp_["delta_rel"])
            parts.append(
                f"Comparação {cmp_.get('first_period', {}).get('period')!s} → {cmp_.get('last_period', {}).get('period')!s}: variação relativa {100.0 * dr:.1f}%."
            )

        return " ".join(parts)


def evidence_block_to_digest(block: EvidenceBlock, *, aggregation_logic: str = "evidence_builder_v1") -> AnalyticalDigest:
    """Projecção mínima para :class:`AnalyticalDigest` (contexto LLM)."""
    flat_sample: tuple[Mapping[str, Any], ...] = (
        {"insights": dict(block.insights), "metrics": dict(block.metrics)},
    )
    return AnalyticalDigest(
        summary=block.summary,
        volume=int(block.metrics.get("input_rows", 0) or 0),
        sample=flat_sample,
        coverage=block.coverage,
        source_refs=tuple(block.sample_refs),
        aggregation_logic=aggregation_logic,
        confidence=block.confidence,
    )
