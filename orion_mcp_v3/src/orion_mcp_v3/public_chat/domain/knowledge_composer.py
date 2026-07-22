"""Knowledge Composer — Computed Objects a partir do grafo + evidências."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.public_chat.domain.analytical_plan import AnalyticalGoal, AnalyticalPlan
from orion_mcp_v3.public_chat.domain.fact_cell import FactCell, cell_from_extracted_fact
from orion_mcp_v3.public_chat.domain.fact_engine.confidence import confidence_for_path
from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType
from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import ResolvedMemoryHit
from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap, GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.models import ExtractedFact, FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.trace import (
    ExtractionPath,
    FactTrace,
    ResolutionRule,
)
from orion_mcp_v3.public_chat.domain.fact_extractor import (
    PARTIAL_RANKING_CONFIDENCE,
    _growth_by_label,
    _key_metrics_truncated,
    _rows_for_requirement,
)
from orion_mcp_v3.public_chat.domain.intent_contract import PublicOperationType
from orion_mcp_v3.public_chat.domain.requirements_graph import RequirementsGraph


@dataclass(frozen=True, slots=True)
class LeaderComparison:
    leader_before: dict[str, Any]
    leader_after: dict[str, Any]
    changed: bool
    confidence: float
    coverage: dict[str, Any]

    def as_mapping(self) -> dict[str, Any]:
        return {
            "kind": "LeaderComparison",
            "leader_before": self.leader_before,
            "leader_after": self.leader_after,
            "changed": self.changed,
            "confidence": round(self.confidence, 4),
            "coverage": self.coverage,
        }


@dataclass(frozen=True, slots=True)
class PeriodDelta:
    label: str
    value: float
    unit: str
    period_from: str
    period_to: str
    ascending: bool
    confidence: float
    comparable_rows: int
    truncated: bool

    def as_mapping(self) -> dict[str, Any]:
        return {
            "kind": "PeriodDelta",
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "period_from": self.period_from,
            "period_to": self.period_to,
            "ascending": self.ascending,
            "confidence": round(self.confidence, 4),
            "comparable_rows": self.comparable_rows,
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class RankingObject:
    label: str
    value: str
    unit: str | None
    period: str | None
    confidence: float
    fact_key: str

    def as_mapping(self) -> dict[str, Any]:
        return {
            "kind": "Ranking",
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "period": self.period,
            "confidence": round(self.confidence, 4),
            "fact_key": self.fact_key,
        }


@dataclass(frozen=True, slots=True)
class TimeSeries:
    label: str
    points: tuple[dict[str, Any], ...]
    unit: str | None
    confidence: float
    crossover_months: tuple[str, ...] = ()
    missing_periods: tuple[str, ...] = ()

    def as_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": "TimeSeries",
            "label": self.label,
            "points": list(self.points),
            "unit": self.unit,
            "confidence": round(self.confidence, 4),
            "missing_periods": list(self.missing_periods),
        }
        if self.crossover_months:
            payload["crossover_months"] = list(self.crossover_months)
        return payload


@dataclass(frozen=True, slots=True)
class CumulativeSum:
    label: str
    value: float
    unit: str | None
    periods: tuple[str, ...]
    missing_periods: tuple[str, ...]
    confidence: float

    def as_mapping(self) -> dict[str, Any]:
        return {
            "kind": "CumulativeSum",
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "periods": list(self.periods),
            "missing_periods": list(self.missing_periods),
            "confidence": round(self.confidence, 4),
        }


@dataclass(frozen=True, slots=True)
class CompositionResult:
    computed: tuple[dict[str, Any], ...]
    facts: tuple[ExtractedFact, ...]
    cells: tuple[FactCell, ...]
    gaps: tuple[FactGap, ...]
    ranking_base_rows: int | None = None
    source_truncated: bool = False
    narrative_instructions: tuple[str, ...] = ()


def compose_knowledge(
    *,
    graph: RequirementsGraph,
    leaf_facts: tuple[ExtractedFact, ...],
    resolved: dict[str, ResolvedMemoryHit],
    semantics_version: str = "v1",
) -> CompositionResult:
    plan = graph.plan
    cells = tuple(
        cell_from_extracted_fact(
            fact,
            period=_period_for_fact(fact, graph.nodes),
            dimension=_dimension_for_fact(fact, graph.nodes),
            matched_key=_matched_for_fact(fact, graph.nodes),
        )
        for fact in leaf_facts
    )

    if plan.goal == AnalyticalGoal.LEADER_COMPARISON:
        return _compose_leader_comparison(
            graph=graph,
            leaf_facts=leaf_facts,
            cells=cells,
            semantics_version=semantics_version,
        )
    if plan.goal == AnalyticalGoal.PERIOD_DELTA:
        return _compose_period_delta(
            graph=graph,
            leaf_facts=leaf_facts,
            cells=cells,
            resolved=resolved,
            semantics_version=semantics_version,
        )
    if plan.goal == AnalyticalGoal.TIME_SERIES:
        return _compose_time_series(
            graph=graph,
            leaf_facts=leaf_facts,
            cells=cells,
            resolved=resolved,
            semantics_version=semantics_version,
        )
    if plan.goal == AnalyticalGoal.CUMULATIVE:
        return _compose_cumulative(
            graph=graph,
            leaf_facts=leaf_facts,
            cells=cells,
            resolved=resolved,
            semantics_version=semantics_version,
        )
    if plan.goal == AnalyticalGoal.RANKING:
        rankings = tuple(
            RankingObject(
                label=fact.label,
                value=fact.value,
                unit=fact.unit,
                period=_period_for_fact(fact, graph.nodes),
                confidence=fact.confidence,
                fact_key=fact.fact_key,
            ).as_mapping()
            for fact in leaf_facts
        )
        return CompositionResult(
            computed=rankings,
            facts=leaf_facts,
            cells=cells,
            gaps=(),
            narrative_instructions=("Descreva o extremo do ranking com label e valor.",),
        )
    return CompositionResult(
        computed=tuple(cell.as_mapping() for cell in cells),
        facts=leaf_facts,
        cells=cells,
        gaps=(),
        narrative_instructions=("Descreva apenas os facts/cells fornecidos.",),
    )


def _compose_leader_comparison(
    *,
    graph: RequirementsGraph,
    leaf_facts: tuple[ExtractedFact, ...],
    cells: tuple[FactCell, ...],
    semantics_version: str,
) -> CompositionResult:
    if len(leaf_facts) < 2:
        return CompositionResult(
            computed=(),
            facts=leaf_facts,
            cells=cells,
            gaps=(
                FactGap(
                    fact_key="dynamic:leader_change",
                    reason=GapReason.EXTRACTION_FAILED,
                    detail="leader_change requires one ranking fact per period",
                ),
            ),
            narrative_instructions=("Não tenho comparação de líderes materializada.",),
        )
    ordered = sorted(
        zip(leaf_facts, cells, strict=True),
        key=lambda item: item[1].period or item[0].fact_key,
    )
    before_fact, before_cell = ordered[0]
    after_fact, after_cell = ordered[-1]
    changed = _normalize_label(before_fact.label) != _normalize_label(after_fact.label)
    confidence = min(before_fact.confidence, after_fact.confidence)
    comparison = LeaderComparison(
        leader_before={
            "label": before_fact.label,
            "value": before_fact.value,
            "unit": before_fact.unit,
            "period": before_cell.period,
            "fact_key": before_fact.fact_key,
        },
        leader_after={
            "label": after_fact.label,
            "value": after_fact.value,
            "unit": after_fact.unit,
            "period": after_cell.period,
            "fact_key": after_fact.fact_key,
        },
        changed=changed,
        confidence=confidence,
        coverage={"period_count": len(ordered), "fact_count": len(leaf_facts)},
    )
    edge = next((e for e in graph.edges if e.kind.value == "compare_identity"), None)
    derived_key = edge.target_key if edge else (
        f"dynamic:leader_change:{before_cell.period or ''}:{after_cell.period or ''}"
    )
    continuity = "mudou" if changed else "manteve"
    derived = ExtractedFact(
        fact_key=derived_key,
        label=after_fact.label,
        value=f"{continuity}; before={before_fact.label}; after={after_fact.label}",
        unit=None,
        fact_type=FactType.DERIVED,
        confidence=confidence,
        origin_id=after_fact.origin_id,
        context_key=after_fact.context_key,
        trace=FactTrace(
            fact_key=derived_key,
            resolved_from=(before_fact.origin_id, after_fact.origin_id),
            context_keys=(before_fact.context_key, after_fact.context_key),
            rule_applied=ResolutionRule.JOIN_PLAN,
            extraction_path=ExtractionPath.DERIVED_COMPUTE,
            semantics_version=semantics_version,
        ),
    )
    return CompositionResult(
        computed=(comparison.as_mapping(),),
        facts=(*leaf_facts, derived),
        cells=cells,
        gaps=(),
        narrative_instructions=(
            "Verbalize LeaderComparison: líder de cada período e se mudou (changed).",
            "Não calcule growth% nem compare magnitudes entre períodos.",
        ),
    )


def _compose_period_delta(
    *,
    graph: RequirementsGraph,
    leaf_facts: tuple[ExtractedFact, ...],
    cells: tuple[FactCell, ...],
    resolved: dict[str, ResolvedMemoryHit],
    semantics_version: str,
) -> CompositionResult:
    requirements = graph.nodes
    groups: dict[str, list[FactRequirement]] = {}
    for req in requirements:
        if not req.matched_key or req.entity:
            continue
        groups.setdefault(req.matched_key, []).append(req)

    facts: list[ExtractedFact] = []
    gaps: list[FactGap] = []
    computed: list[dict[str, Any]] = []
    comparable_rows: int | None = None
    truncated = False
    ascending = (graph.plan.operation or "").lower() in (
        PublicOperationType.PERIOD_DECLINE.value,
        "period_decline",
        "ranking_asc",
        "min",
    )

    for matched_key, group in groups.items():
        if len(group) < 2:
            continue
        period_rows: list[tuple[FactRequirement, ResolvedMemoryHit, tuple]] = []
        for requirement in group:
            resolved_hit = resolved.get(requirement.fact_key)
            if resolved_hit is None:
                continue
            if _key_metrics_truncated(resolved_hit.hit, requirement):
                truncated = True
            rows = _rows_for_requirement(requirement, resolved_hit.hit)
            if rows:
                period_rows.append((requirement, resolved_hit, rows))
        if len(period_rows) < 2:
            continue
        period_rows.sort(key=lambda item: item[0].period or "")
        first_req, first_hit, first_rows = period_rows[0]
        last_req, last_hit, last_rows = period_rows[-1]
        growth = _growth_by_label(first_rows, last_rows)
        if not growth:
            gaps.append(
                FactGap(
                    fact_key=f"dynamic:{matched_key}@growth",
                    reason=GapReason.EXTRACTION_FAILED,
                    detail="no intersecting entities across periods for ranking growth",
                )
            )
            continue
        ranked = sorted(growth.items(), key=lambda item: item[1], reverse=not ascending)
        winner_label, winner_pct = ranked[0]
        comparable_rows = len(growth) if comparable_rows is None else min(comparable_rows, len(growth))
        confidence = confidence_for_path(ExtractionPath.RANKING_DERIVED)
        if comparable_rows <= 1 or truncated:
            confidence = min(confidence, PARTIAL_RANKING_CONFIDENCE)
        fact_key = f"dynamic:{matched_key}@growth:{first_req.period or ''}:{last_req.period or ''}"
        delta = PeriodDelta(
            label=winner_label,
            value=winner_pct,
            unit="pct",
            period_from=first_req.period or "",
            period_to=last_req.period or "",
            ascending=ascending,
            confidence=confidence,
            comparable_rows=comparable_rows,
            truncated=truncated,
        )
        computed.append(delta.as_mapping())
        facts.append(
            ExtractedFact(
                fact_key=fact_key,
                label=winner_label,
                value=f"{winner_pct:.2f}%",
                unit="pct",
                fact_type=FactType.DERIVED,
                confidence=confidence,
                origin_id=last_hit.hit.origin_id,
                context_key=last_hit.hit.context_key,
                trace=FactTrace(
                    fact_key=fact_key,
                    resolved_from=(first_hit.hit.origin_id, last_hit.hit.origin_id),
                    context_keys=(first_hit.hit.context_key, last_hit.hit.context_key),
                    rule_applied=ResolutionRule.JOIN_PLAN,
                    extraction_path=ExtractionPath.RANKING_DERIVED,
                    semantics_version=semantics_version,
                ),
            )
        )

    return CompositionResult(
        computed=tuple(computed),
        facts=tuple(facts),
        cells=cells,
        gaps=tuple(gaps),
        ranking_base_rows=comparable_rows,
        source_truncated=truncated,
        narrative_instructions=(
            "Verbalize PeriodDelta: entidade vencedora e variação percentual entre períodos.",
        ),
    )


def _compose_time_series(
    *,
    graph: RequirementsGraph,
    leaf_facts: tuple[ExtractedFact, ...],
    cells: tuple[FactCell, ...],
    resolved: dict[str, ResolvedMemoryHit],
    semantics_version: str,
) -> CompositionResult:
    series_map, missing, gaps = _series_from_resolved(graph, resolved)
    if not series_map:
        series_map, missing = _series_from_leaf_facts(leaf_facts, cells, graph.plan.periods)

    computed: list[dict[str, Any]] = []
    facts: list[ExtractedFact] = list(leaf_facts)
    labels = list(series_map.keys())
    crossover: tuple[str, ...] = ()
    if len(labels) >= 2:
        crossover = _crossover_months(series_map[labels[0]], series_map[labels[1]])

    for label, points in series_map.items():
        series = TimeSeries(
            label=label,
            points=tuple(points),
            unit="BRL",
            confidence=confidence_for_path(ExtractionPath.DERIVED_COMPUTE),
            crossover_months=crossover if label == labels[0] else (),
            missing_periods=tuple(missing.get(label, ())),
        )
        computed.append(series.as_mapping())
        fact_key = f"dynamic:time_series:{_normalize_label(label)}"
        facts.append(
            ExtractedFact(
                fact_key=fact_key,
                label=label,
                value="; ".join(f"{p['period']}={p['value']}" for p in points),
                unit="BRL",
                fact_type=FactType.DERIVED,
                confidence=series.confidence,
                origin_id=leaf_facts[0].origin_id if leaf_facts else 0,
                context_key=leaf_facts[0].context_key if leaf_facts else "",
                trace=FactTrace(
                    fact_key=fact_key,
                    resolved_from=tuple(f.origin_id for f in leaf_facts[:4]),
                    context_keys=tuple(f.context_key for f in leaf_facts[:4]),
                    rule_applied=ResolutionRule.JOIN_PLAN,
                    extraction_path=ExtractionPath.DERIVED_COMPUTE,
                    semantics_version=semantics_version,
                ),
            )
        )

    if crossover:
        facts.append(
            ExtractedFact(
                fact_key="dynamic:time_series:crossover",
                label="crossover_months",
                value=",".join(crossover),
                unit=None,
                fact_type=FactType.DERIVED,
                confidence=confidence_for_path(ExtractionPath.DERIVED_COMPUTE),
                origin_id=leaf_facts[0].origin_id if leaf_facts else 0,
                context_key="",
                trace=FactTrace(
                    fact_key="dynamic:time_series:crossover",
                    resolved_from=(),
                    context_keys=(),
                    rule_applied=ResolutionRule.JOIN_PLAN,
                    extraction_path=ExtractionPath.DERIVED_COMPUTE,
                    semantics_version=semantics_version,
                ),
            )
        )

    instructions = [
        "Verbalize TimeSeries: pontos por período; não invente meses ausentes.",
    ]
    if crossover:
        instructions.append(
            f"Use crossover_months já materializado: {', '.join(crossover)}."
        )
    return CompositionResult(
        computed=tuple(computed),
        facts=tuple(facts),
        cells=cells,
        gaps=tuple(gaps),
        narrative_instructions=tuple(instructions),
    )


def _compose_cumulative(
    *,
    graph: RequirementsGraph,
    leaf_facts: tuple[ExtractedFact, ...],
    cells: tuple[FactCell, ...],
    resolved: dict[str, ResolvedMemoryHit],
    semantics_version: str,
) -> CompositionResult:
    series_map, missing, gaps = _series_from_resolved(graph, resolved)
    if not series_map:
        series_map, missing = _series_from_leaf_facts(leaf_facts, cells, graph.plan.periods)

    expected = tuple(graph.plan.periods) or tuple(
        sorted({p["period"] for points in series_map.values() for p in points})
    )
    computed: list[dict[str, Any]] = []
    facts: list[ExtractedFact] = list(leaf_facts)
    totals: dict[str, float] = {}

    for label, points in series_map.items():
        total = sum(float(p["value"]) for p in points)
        totals[label] = total
        miss = tuple(p for p in expected if p not in {pt["period"] for pt in points})
        if label in missing:
            miss = tuple(dict.fromkeys((*miss, *missing[label])))
        cum = CumulativeSum(
            label=label,
            value=total,
            unit="BRL",
            periods=tuple(p["period"] for p in points),
            missing_periods=miss,
            confidence=confidence_for_path(ExtractionPath.DERIVED_COMPUTE),
        )
        computed.append(cum.as_mapping())
        fact_key = f"dynamic:cumulative:{_normalize_label(label)}"
        facts.append(
            ExtractedFact(
                fact_key=fact_key,
                label=label,
                value=f"{total:.2f}",
                unit="BRL",
                fact_type=FactType.DERIVED,
                confidence=cum.confidence,
                origin_id=leaf_facts[0].origin_id if leaf_facts else 0,
                context_key=leaf_facts[0].context_key if leaf_facts else "",
                trace=FactTrace(
                    fact_key=fact_key,
                    resolved_from=tuple(f.origin_id for f in leaf_facts[:4]),
                    context_keys=tuple(f.context_key for f in leaf_facts[:4]),
                    rule_applied=ResolutionRule.JOIN_PLAN,
                    extraction_path=ExtractionPath.DERIVED_COMPUTE,
                    semantics_version=semantics_version,
                ),
            )
        )

    if len(totals) >= 2:
        labels = list(totals.keys())
        diff = totals[labels[0]] - totals[labels[1]]
        diff_label = f"diff:{labels[0]}-{labels[1]}"
        computed.append(
            CumulativeSum(
                label=diff_label,
                value=diff,
                unit="BRL",
                periods=expected,
                missing_periods=(),
                confidence=confidence_for_path(ExtractionPath.DERIVED_COMPUTE),
            ).as_mapping()
        )
        facts.append(
            ExtractedFact(
                fact_key="dynamic:cumulative:diff",
                label=diff_label,
                value=f"{diff:.2f}",
                unit="BRL",
                fact_type=FactType.DERIVED,
                confidence=confidence_for_path(ExtractionPath.DERIVED_COMPUTE),
                origin_id=leaf_facts[0].origin_id if leaf_facts else 0,
                context_key="",
                trace=FactTrace(
                    fact_key="dynamic:cumulative:diff",
                    resolved_from=(),
                    context_keys=(),
                    rule_applied=ResolutionRule.JOIN_PLAN,
                    extraction_path=ExtractionPath.DERIVED_COMPUTE,
                    semantics_version=semantics_version,
                ),
            )
        )

    return CompositionResult(
        computed=tuple(computed),
        facts=tuple(facts),
        cells=cells,
        gaps=tuple(gaps),
        narrative_instructions=(
            "Verbalize CumulativeSum: totais por entidade e diff se presente; cite missing_periods.",
        ),
    )


def _series_from_resolved(
    graph: RequirementsGraph,
    resolved: dict[str, ResolvedMemoryHit],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, tuple[str, ...]], list[FactGap]]:
    series: dict[str, list[dict[str, Any]]] = {}
    present: dict[str, set[str]] = {}
    gaps: list[FactGap] = []
    expected = set(graph.plan.periods)

    for requirement in graph.nodes:
        resolved_hit = resolved.get(requirement.fact_key)
        if resolved_hit is None:
            continue
        period = requirement.period or ""
        rows = _rows_for_requirement(requirement, resolved_hit.hit)
        if requirement.entity:
            match = next(
                (
                    row
                    for row in rows
                    if _normalize_label(row.label) == _normalize_label(requirement.entity)
                    or _normalize_label(requirement.entity) in _normalize_label(row.label)
                ),
                None,
            )
            if match is None and not rows:
                continue
            if match is None:
                # leaf scalar path may already be in entity requirement without rows
                continue
            label = match.label
            series.setdefault(label, []).append({"period": period, "value": match.value})
            present.setdefault(label, set()).add(period)
            continue
        for row in rows:
            if not row.label:
                continue
            series.setdefault(row.label, []).append({"period": period, "value": row.value})
            present.setdefault(row.label, set()).add(period)

    # Keep only entities that appear in requirements.entity when those exist
    entity_labels = {
        req.entity for req in graph.nodes if req.entity
    }
    if entity_labels:
        filtered: dict[str, list[dict[str, Any]]] = {}
        for label, points in series.items():
            if any(
                _normalize_label(entity) in _normalize_label(label)
                or _normalize_label(label) in _normalize_label(entity)
                for entity in entity_labels
            ):
                filtered[label] = sorted(points, key=lambda p: p["period"])
        series = filtered

    for label in list(series.keys()):
        series[label] = sorted(series[label], key=lambda p: p["period"])

    missing: dict[str, tuple[str, ...]] = {}
    if expected:
        for label, seen in present.items():
            miss = tuple(sorted(expected - seen))
            if miss:
                missing[label] = miss
                gaps.append(
                    FactGap(
                        fact_key=f"dynamic:series:{_normalize_label(label)}",
                        reason=GapReason.NO_MEMORY_FOUND,
                        detail=f"missing_periods:{','.join(miss)}",
                    )
                )
    return series, missing, gaps


def _series_from_leaf_facts(
    leaf_facts: tuple[ExtractedFact, ...],
    cells: tuple[FactCell, ...],
    expected_periods: tuple[str, ...],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, tuple[str, ...]]]:
    series: dict[str, list[dict[str, Any]]] = {}
    for fact, cell in zip(leaf_facts, cells, strict=False):
        period = cell.period or ""
        try:
            value = float(str(fact.value).replace("%", "").replace(",", "."))
        except ValueError:
            from orion_mcp_v3.public_chat.domain.key_metrics_reader import parse_metric_value

            parsed = parse_metric_value(fact.value)
            if parsed is None:
                continue
            value = parsed
        series.setdefault(fact.label, []).append({"period": period, "value": value})
    for label in series:
        series[label] = sorted(series[label], key=lambda p: p["period"])
    missing: dict[str, tuple[str, ...]] = {}
    if expected_periods:
        for label, points in series.items():
            seen = {p["period"] for p in points}
            miss = tuple(p for p in expected_periods if p not in seen)
            if miss:
                missing[label] = miss
    return series, missing


def _crossover_months(
    series_a: list[dict[str, Any]],
    series_b: list[dict[str, Any]],
) -> tuple[str, ...]:
    map_b = {p["period"]: float(p["value"]) for p in series_b}
    out: list[str] = []
    for point in series_a:
        period = point["period"]
        if period in map_b and float(point["value"]) > map_b[period]:
            out.append(period)
    return tuple(out)


def _period_for_fact(fact: ExtractedFact, nodes: tuple[FactRequirement, ...]) -> str | None:
    for req in nodes:
        if req.fact_key == fact.fact_key:
            return req.period
    return None


def _dimension_for_fact(fact: ExtractedFact, nodes: tuple[FactRequirement, ...]) -> str | None:
    for req in nodes:
        if req.fact_key == fact.fact_key:
            return req.dimension
    return None


def _matched_for_fact(fact: ExtractedFact, nodes: tuple[FactRequirement, ...]) -> str | None:
    for req in nodes:
        if req.fact_key == fact.fact_key:
            return req.matched_key
    return None


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").strip().casefold())
