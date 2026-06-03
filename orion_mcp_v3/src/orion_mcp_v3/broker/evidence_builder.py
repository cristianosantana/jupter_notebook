"""
EvidenceBuilder: resultado SQL → :class:`~EvidenceBlock` com trends, baseline, variation,
anomalies, comparisons e pontuações de confiança/cobertura (Fase 2.4).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from orion_mcp_v3.broker.aggregators import time_series
from orion_mcp_v3.contracts.cognitive_artifact import (
    artifact_provenance_anchor,
    heuristic_confidence_from_volume,
)
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.evidence_contract import (
    EvidenceContract,
    EvidencePriority,
    OperationalConfidence,
)
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


def _rows_have_usable_key(rows: Sequence[Mapping[str, Any]], key: str | None) -> bool:
    if not key:
        return False
    for row in rows:
        if not isinstance(row, Mapping) or key not in row:
            continue
        if row[key] is None:
            continue
        if isinstance(row[key], str) and not row[key].strip():
            continue
        return True
    return False


def _parse_row_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _format_br_currency(value: float) -> str:
    """Formata valor monetário em estilo pt-BR (milhares com ponto, decimais com vírgula)."""
    neg = "-" if value < 0 else ""
    v = abs(value)
    s = f"{v:,.2f}"  # ex.: 93,895,363.63 (grupo milhar en-US)
    whole, frac = s.rsplit(".", 1)
    whole_br = whole.replace(",", ".")
    return f"{neg}R$ {whole_br},{frac}"


def _format_br_percent(pct: float) -> str:
    return f"{pct:.1f}".replace(".", ",") + "%"


def _format_metric_value(value: float, kind: str) -> str:
    if kind == "money":
        return _format_br_currency(value)
    if kind == "percent":
        return f"{value:.2f}%".replace(".", ",")
    if kind == "count":
        return f"{value:,.0f}".replace(",", ".")
    return f"{value:.2f}".replace(".", ",")


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
        label_key: str | None = None,
        time_key: str | None = None,
        grain: str = "month",
        id_key: str | None = "id",
        ranking_top_n: int = 5,
        value_kind: str = "money",
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
            try:
                periods_snapshot = time_series(rows, time_key=time_key, value_key=value_key, grain=grain)
                trends = self._compute_trends(periods_snapshot)
            except (KeyError, ValueError):
                pass

        comparisons = self._compute_comparisons(periods_snapshot)

        anomalies = self._compute_anomalies(rows, value_key, id_key)

        ranking: list[dict[str, Any]] | None = None
        dominant: dict[str, Any] | None = None
        concentration: dict[str, Any] | None = None
        ranking_omitted = 0
        if label_key is not None and _rows_have_usable_key(rows, label_key):
            sums_map = self._sums_by_label(rows, value_key=value_key, label_key=label_key)
            total_labeled = sum(sums_map.values())
            if sums_map and total_labeled > 0:
                ranking = self._ranking_from_sums(sums_map, top_n=ranking_top_n)
                if ranking:
                    dominant = self._compute_dominant(ranking)
                    concentration = self._compute_concentration(list(sums_map.values()))
                    ranking_omitted = max(0, len(sums_map) - len(ranking))

        period_coverage: dict[str, Any] | None = None
        if time_key is not None and _rows_have_usable_key(rows, time_key):
            period_coverage = self._compute_period_coverage(rows, time_key=time_key)

        insights: dict[str, Any] = {
            "trends": trends,
            "baseline": baseline,
            "variation": variation,
            "anomalies": anomalies,
            "comparisons": comparisons,
        }
        if ranking:
            insights["ranking"] = ranking
            if ranking_omitted > 0:
                insights["ranking_omitted_count"] = ranking_omitted
        if dominant is not None:
            insights["dominant"] = dominant
        if concentration is not None:
            insights["concentration"] = concentration
        if period_coverage is not None:
            insights["period_coverage"] = period_coverage

        summary = self._compose_summary_pt(insights, value_key=value_key, value_kind=value_kind)

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
        conf_dom = 0.0
        if dominant is not None:
            sp = float(dominant.get("share_pct") or 0.0)
            if sp > 40.0:
                conf_dom = 0.06
        confidence = min(0.95, conf_base + conf_signal + conf_anom + conf_cmp + conf_dom)

        coverage_scoring = min(
            1.0,
            (n / max(row_total, 1)) * 0.65 + min(1.0, len(periods_snapshot) / 12.0) * 0.35,
        )

        metrics: dict[str, Any] = {
            "value_key": value_key,
            "value_kind": value_kind,
            "label_key": label_key,
            "time_key": time_key,
            "grain": grain if time_key else None,
            "numeric_samples": n,
            "input_rows": row_total,
            "confidence_scoring": {
                "volume_component": conf_base,
                "trend_component": conf_signal,
                "anomaly_component": conf_anom,
                "comparison_component": conf_cmp,
                "dominance_component": conf_dom,
                "combined": confidence,
            },
            "coverage_scoring": coverage_scoring,
        }
        evidence_contract = (
            EvidenceContract.empty_result(row_count=0)
            if row_total == 0
            else EvidenceContract.present(
                row_count=row_total,
                source_priority=EvidencePriority.FRESH_SQL_EVIDENCE,
                operational_confidence=OperationalConfidence(
                    data_coverage=coverage_scoring,
                    aggregation_reliability=0.9 if n > 0 else 0.5,
                    pipeline_integrity=1.0,
                    narrative_confidence=confidence,
                ),
                safe_for_record_level_claims=True,
            )
        )
        metrics["evidence_contract"] = evidence_contract.as_dict()

        refs = tuple(str(a.get("ref", "")) for a in anomalies.get("examples", []) if a.get("ref") is not None)

        supporting = {"evidence_contract": evidence_contract.as_dict()}
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

    def _sums_by_label(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        value_key: str,
        label_key: str,
    ) -> dict[str, float]:
        sums: defaultdict[str, float] = defaultdict(float)
        for row in rows:
            if not isinstance(row, Mapping) or label_key not in row or value_key not in row:
                continue
            raw_l = row[label_key]
            if raw_l is None:
                continue
            label = str(raw_l).strip()
            if not label:
                continue
            try:
                sums[label] += float(row[value_key])
            except (TypeError, ValueError):
                continue
        return dict(sums)

    def _ranking_from_sums(self, sums: Mapping[str, float], *, top_n: int) -> list[dict[str, Any]]:
        total = float(sum(sums.values()))
        if total <= 0:
            return []
        ordered = sorted(sums.items(), key=lambda kv: kv[1], reverse=True)
        out: list[dict[str, Any]] = []
        for i, (lab, val) in enumerate(ordered[: max(0, top_n)], start=1):
            share = 100.0 * float(val) / total
            out.append({"rank": i, "label": lab, "value": float(val), "share_pct": share})
        return out

    def _compute_dominant(self, ranking: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
        if not ranking:
            return None
        top = dict(ranking[0])
        top["is_majority"] = float(top.get("share_pct") or 0.0) > 50.0
        return top

    def _compute_concentration(self, vals: Sequence[float]) -> dict[str, Any] | None:
        if not vals:
            return None
        total = float(sum(vals))
        if total <= 0:
            return None
        hhi = sum((float(v) / total) ** 2 for v in vals)
        if hhi < 0.15:
            interpretation = "baixa"
        elif hhi <= 0.25:
            interpretation = "moderada"
        else:
            interpretation = "alta"
        return {"hhi": hhi, "interpretation": interpretation}

    def _compute_period_coverage(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        time_key: str,
    ) -> dict[str, Any] | None:
        dates: list[date] = []
        for row in rows:
            if not isinstance(row, Mapping) or time_key not in row:
                continue
            d = _parse_row_date(row[time_key])
            if d is not None:
                dates.append(d)
        if not dates:
            return None
        dmin, dmax = min(dates), max(dates)
        days_span = (dmax - dmin).days + 1
        return {
            "date_min": dmin.isoformat(),
            "date_max": dmax.isoformat(),
            "days_span": days_span,
        }

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

    def _compose_summary_pt(self, insights: Mapping[str, Any], *, value_key: str, value_kind: str) -> str:
        base = insights["baseline"]
        var = insights["variation"]
        tr = insights["trends"]
        an = insights["anomalies"]
        cmp_ = insights.get("comparisons", {})
        ranking = insights.get("ranking")
        dominant = insights.get("dominant")
        concentration = insights.get("concentration")
        period_cov = insights.get("period_coverage")

        parts: list[str] = []

        if isinstance(ranking, list) and ranking:
            lines = [f"Ranking por `{value_key}`:"]
            for item in ranking:
                lab = str(item.get("label", ""))
                val = float(item.get("value") or 0.0)
                sp = float(item.get("share_pct") or 0.0)
                rk = int(item.get("rank") or 0)
                lines.append(
                    f"  {rk}. {lab}  {_format_metric_value(val, value_kind)}  ({_format_br_percent(sp)})",
                )
            n_extra = int(insights.get("ranking_omitted_count") or 0)
            if n_extra > 0:
                lines.append(f"  ... (+ {n_extra} categorias)")
            parts.append("\n".join(lines))
            if isinstance(dominant, Mapping):
                dl = str(dominant.get("label", ""))
                dsp = float(dominant.get("share_pct") or 0.0)
                dom_line = f"Dominante: {dl} ({_format_br_percent(dsp)} do total)."
                if isinstance(concentration, Mapping):
                    hhi = float(concentration.get("hhi") or 0.0)
                    interp = str(concentration.get("interpretation", ""))
                    hhi_s = f"{hhi:.2f}".replace(".", ",")
                    dom_line += f" Concentração: {interp} (HHI={hhi_s})."
                parts.append(dom_line)
            elif isinstance(concentration, Mapping):
                hhi = float(concentration.get("hhi") or 0.0)
                interp = str(concentration.get("interpretation", ""))
                hhi_s = f"{hhi:.2f}".replace(".", ",")
                parts.append(f"Concentração: {interp} (HHI={hhi_s}).")

        if isinstance(period_cov, Mapping) and period_cov.get("date_min"):
            d0 = period_cov.get("date_min")
            d1 = period_cov.get("date_max")
            span = period_cov.get("days_span")
            parts.append(f"Período dos dados: {d0} a {d1} ({span} dias).")

        if base.get("count"):
            mean = base.get("mean")
            median = base.get("median")
            mean_s = _format_metric_value(float(mean), value_kind) if mean is not None else "n/d"
            median_s = _format_metric_value(float(median), value_kind) if median is not None else "n/d"
            parts.append(
                f"Métrica `{value_key}`: média {mean_s}, mediana {median_s} (n={base.get('count')}).",
            )
        else:
            parts.append(f"Sem valores numéricos para `{value_key}`.")

        if var.get("coefficient_of_variation") is not None:
            parts.append(f"Coeficiente de variação ≈ {var['coefficient_of_variation']:.4f}.")

        if tr.get("status") == "ok" and tr.get("direction") != "unknown":
            pop = tr.get("period_over_period_change")
            pop_s = f"{100.0 * pop:.1f}%" if isinstance(pop, (int, float)) and pop is not None else "n/d"
            parts.append(
                f"Tendência mensal: {tr.get('direction')} (último vs penúltimo período: {pop_s}).",
            )

        ac = int(an.get("count") or 0)
        if ac:
            parts.append(f"{ac} valor(es) com |z| ≥ {self._z_threshold} (possíveis anomalias).")

        if cmp_.get("status") == "ok" and cmp_.get("delta_rel") is not None:
            dr = float(cmp_["delta_rel"])
            parts.append(
                f"Comparação {cmp_.get('first_period', {}).get('period')!s} → {cmp_.get('last_period', {}).get('period')!s}: variação relativa {100.0 * dr:.1f}%.",
            )

        return "\n\n".join(parts)


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
