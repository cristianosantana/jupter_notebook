"""Planeja e projeta respostas diretas a partir de resultados SQL de templates."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from orion_mcp_v3.broker.answer_capability import (
    AnswerCapability,
    AnswerPlan,
    DimensionCapability,
    MeasureCapability,
    ProjectedAnswer,
)
from orion_mcp_v3.broker.executor import AnalyticsResult

if TYPE_CHECKING:
    from orion_mcp_v3.broker.query_templates import QueryTemplateRegistry


def _norm(text: str) -> str:
    raw = "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", raw).strip()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format_value(value: Any, kind: str) -> str:
    n = _to_float(value)
    if n is None:
        return str(value)
    if kind == "money":
        s = f"{n:,.2f}"
        whole, frac = s.rsplit(".", 1)
        return f"R$ {whole.replace(',', '.')},{frac}"
    if kind == "percent":
        return f"{n:.2f}%".replace(".", ",")
    if kind == "count":
        return f"{n:,.0f}".replace(",", ".")
    return f"{n:.2f}".replace(".", ",")


def _row_label(row: Mapping[str, Any], dimension: DimensionCapability | None) -> str:
    if dimension is None:
        return "registro"
    return str(row.get(dimension.column, "n/d"))


def _operation_from_query(query_text: str) -> str:
    q = _norm(query_text)
    has_top = bool(re.search(r"\b(maior|melhor|top|mais|domina|ranking)\b", q))
    has_bottom = bool(re.search(r"\b(menor|pior|menos|baixo|menores)\b", q))
    if has_top and has_bottom:
        return "top_and_bottom"
    if has_bottom:
        return "ranking_asc"
    if has_top:
        return "ranking_desc"
    if re.search(r"\b(cada|por|liste|lista|mostre)\b", q):
        return "list"
    return "ranking_desc"


def _score_measure(measure: MeasureCapability, query_text: str) -> int:
    q = _norm(query_text)
    score = 0
    terms = (measure.column, measure.label, *measure.synonyms)
    for term in terms:
        t = _norm(term)
        if t and t in q:
            score += 8 if t == _norm(measure.label) else 5
    if measure.column in {"ticket_medio", "ticket_medio_os"} and "ticket" in q:
        score += 20
    if measure.column in {
        "total_vendas",
        "total_os",
        "qtd_recebimentos",
        "total_recebimentos",
        "quantidade_os",
    }:
        if "volume" in q or "quantidade" in q or "qtd" in q:
            score += 18
    if measure.column in {"faturamento", "valor_total", "valor_total_recebido", "total_recebido"}:
        if any(t in q for t in ("faturamento", "faturou", "receita", "valor", "recebido")):
            score += 16
    if measure.column == "maior_recebimento" and "maior recebimento" in q:
        score += 24
    if measure.column == "menor_recebimento" and "menor recebimento" in q:
        score += 24
    return score


def _score_dimension(dimension: DimensionCapability, query_text: str) -> int:
    q = _norm(query_text)
    score = 0
    for term in (dimension.column, dimension.label, *dimension.synonyms):
        t = _norm(term)
        if t and t in q:
            score += 8
    return score


def infer_answer_plan(
    query_text: str,
    *,
    template_slug: str,
    capability: AnswerCapability,
) -> AnswerPlan:
    """Escolhe métrica, dimensão e operação suportadas por um template."""
    measure_scores = {
        key: _score_measure(measure, query_text)
        for key, measure in capability.measures.items()
    }
    measure_key = max(
        measure_scores,
        key=lambda k: (measure_scores[k], k == capability.default_measure),
    )
    if measure_scores[measure_key] <= 0:
        measure_key = capability.default_measure

    dimension_key: str | None = None
    if capability.dimensions:
        dim_scores = {
            key: _score_dimension(dim, query_text)
            for key, dim in capability.dimensions.items()
        }
        dimension_key = max(
            dim_scores,
            key=lambda k: (dim_scores[k], k == capability.default_dimension),
        )
        if dim_scores[dimension_key] <= 0:
            dimension_key = capability.default_dimension

    operation = _operation_from_query(query_text)
    if operation not in capability.supported_operations:
        operation = "ranking_desc" if "ranking_desc" in capability.supported_operations else capability.supported_operations[0]

    return AnswerPlan(
        template_slug=template_slug,
        measure=measure_key,
        dimension=dimension_key,
        operation=operation,
        reason="capability_match",
    )


def _aggregate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    measure: MeasureCapability,
    dimension: DimensionCapability | None,
) -> list[dict[str, Any]]:
    if dimension is None:
        out: list[dict[str, Any]] = []
        for row in rows:
            if measure.column in row:
                out.append(dict(row))
        return out

    grouped: dict[str, dict[str, Any]] = {}
    values: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        if dimension.column not in row or measure.column not in row:
            continue
        label = str(row[dimension.column]).strip()
        n = _to_float(row[measure.column])
        if not label or n is None:
            continue
        if label not in grouped:
            grouped[label] = dict(row)
            grouped[label][measure.column] = 0.0 if measure.additive else n
        if measure.additive:
            grouped[label][measure.column] = float(grouped[label][measure.column]) + n
        else:
            values[label].append(n)

    if not measure.additive:
        for label, nums in values.items():
            if nums:
                grouped[label][measure.column] = sum(nums) / len(nums)
    return list(grouped.values())


def project_answer(
    rows: Sequence[Mapping[str, Any]],
    *,
    plan: AnswerPlan,
    capability: AnswerCapability,
    limit: int = 10,
) -> ProjectedAnswer | None:
    """Projeta rows SQL em ranking/lista/top-bottom usando a coluna certa."""
    measure = capability.measures.get(plan.measure)
    if measure is None:
        return None
    dimension = capability.dimensions.get(plan.dimension) if plan.dimension else None
    projected = _aggregate_rows(rows, measure=measure, dimension=dimension)
    projected = [r for r in projected if _to_float(r.get(measure.column)) is not None]
    if not projected:
        return None

    reverse = plan.operation != "ranking_asc"
    ordered = sorted(projected, key=lambda r: _to_float(r.get(measure.column)) or 0.0, reverse=reverse)
    top = ordered[0]
    bottom = sorted(projected, key=lambda r: _to_float(r.get(measure.column)) or 0.0)[0]
    selected = tuple(ordered[: max(1, limit)])

    dim_label = dimension.label if dimension is not None else "registro"
    top_label = _row_label(top, dimension) if dimension is not None else "maior valor"
    top_value = _format_value(top.get(measure.column), measure.kind)
    parts: list[str] = []
    if plan.operation == "top_and_bottom":
        bottom_label = _row_label(bottom, dimension) if dimension is not None else "menor valor"
        bottom_value = _format_value(bottom.get(measure.column), measure.kind)
        parts.append(
            f"Resposta direta: maior {measure.label} por {dim_label}: {top_label} ({top_value}); "
            f"menor {measure.label}: {bottom_label} ({bottom_value})."
        )
    elif plan.operation == "ranking_asc":
        parts.append(f"Resposta direta: menor {measure.label} por {dim_label}: {top_label} ({top_value}).")
    elif plan.operation == "list":
        lines = [f"Resposta direta: {measure.label} por {dim_label}:"]
        for i, row in enumerate(selected, start=1):
            label = _row_label(row, dimension)
            value = _format_value(row.get(measure.column), measure.kind)
            lines.append(f"{i}. {label}: {value}")
        parts.append("\n".join(lines))
    else:
        parts.append(f"Resposta direta: maior {measure.label} por {dim_label}: {top_label} ({top_value}).")

    return ProjectedAnswer(
        plan=plan,
        summary=" ".join(parts),
        rows=tuple(ordered),
        top=top,
        bottom=bottom if plan.operation == "top_and_bottom" else None,
    )


def build_projected_answer(
    query_text: str,
    results: Sequence[AnalyticsResult],
    *,
    templates: "QueryTemplateRegistry",
) -> ProjectedAnswer | None:
    """Escolhe o melhor resultado de template e constrói uma resposta direta."""
    best: tuple[int, AnalyticsResult, AnswerPlan, AnswerCapability] | None = None
    q = _norm(query_text)
    for result in results:
        hints = result.plan.hints if isinstance(result.plan.hints, Mapping) else {}
        slug = hints.get("template_slug")
        if not isinstance(slug, str):
            continue
        template = templates.get(slug)
        capability = getattr(template, "capability", None)
        if template is None or capability is None:
            continue
        plan = infer_answer_plan(query_text, template_slug=slug, capability=capability)
        measure = capability.measures.get(plan.measure)
        dimension = capability.dimensions.get(plan.dimension) if plan.dimension else None
        score = 0
        if measure is not None:
            score += _score_measure(measure, query_text)
        if dimension is not None:
            score += _score_dimension(dimension, query_text)
        if slug in q:
            score += 20
        if result.rows:
            score += 2
        candidate = (score, result, plan, capability)
        if best is None or candidate[0] > best[0]:
            best = candidate

    if best is None:
        return None
    _, result, plan, capability = best
    return project_answer(result.rows, plan=plan, capability=capability)
