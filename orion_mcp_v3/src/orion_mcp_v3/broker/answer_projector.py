"""Planeja e projeta respostas diretas a partir de resultados SQL de templates."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import replace
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from orion_mcp_v3.broker.answer_capability import (
    AnswerCapability,
    AnswerPlan,
    DimensionCapability,
    MeasureCapability,
    ProjectedAnswer,
    ProjectedAnswerSet,
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


def _entity_filters_from_hints(
    hints: Mapping[str, Any],
    capability: AnswerCapability,
) -> tuple[Mapping[str, str], ...]:
    raw = hints.get("entity_filters")
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[Mapping[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        dimension = _hint_key(item.get("dimension"), capability.dimensions)
        value = str(item.get("value") or "").strip()
        if dimension is None or not value:
            continue
        if dimension in _TEMPORAL_FILTER_DIMENSIONS:
            continue
        match = _normalize_filter_match(
            dimension=dimension,
            value=value,
            match=str(item.get("match") or "contains"),
        )
        out.append({"dimension": dimension, "value": value, "match": match})
    return tuple(out)


def _result_scope_from_hints(hints: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw = hints.get("result_scope")
    if not isinstance(raw, Mapping):
        return None
    mode = str(raw.get("mode") or "").strip().lower()
    if mode not in {"all", "top_n", "bottom_n", "sample"}:
        return None
    limit_raw = raw.get("limit")
    limit: int | None = None
    if limit_raw not in (None, ""):
        try:
            limit = max(1, int(limit_raw))
        except (TypeError, ValueError):
            limit = None
    return {"mode": mode, "limit": limit}


def _sort_from_hints(hints: Mapping[str, Any], capability: AnswerCapability) -> Mapping[str, str] | None:
    raw = hints.get("sort")
    if not isinstance(raw, Mapping):
        return None
    field = _hint_key(raw.get("field"), capability.measures) or _hint_key(raw.get("field"), capability.dimensions)
    direction = str(raw.get("direction") or "desc").strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "desc"
    return {"field": field or "", "direction": direction}


def _normalize_filter_match(*, dimension: str, value: str, match: str) -> str:
    normalized = match.strip().lower()
    if normalized not in {"contains", "exact"}:
        normalized = "contains"
    if normalized != "exact":
        return normalized
    if dimension in {"periodo", "data_pagamento"} and re.fullmatch(r"20\d{2}(?:-\d{2})?(?:-\d{2})?", value):
        return "exact"
    return "contains"


_TEMPORAL_FILTER_DIMENSIONS = frozenset({"periodo", "data_pagamento"})


def filter_rows_for_entity_filters(
    rows: Sequence[Mapping[str, Any]],
    *,
    entity_filters: Sequence[Mapping[str, str]],
    capability: AnswerCapability,
) -> tuple[Mapping[str, Any], ...]:
    """Aplica filtros semânticos de entidade em rows já retornadas por um template."""
    if not entity_filters:
        return tuple(rows)
    filtered: list[Mapping[str, Any]] = []
    for row in rows:
        keep = True
        for item in entity_filters:
            dimension = capability.dimensions.get(str(item.get("dimension") or ""))
            if dimension is None:
                continue
            if dimension.column in _TEMPORAL_FILTER_DIMENSIONS:
                continue
            row_value = _norm(str(row.get(dimension.column, "")))
            filter_value = _norm(str(item.get("value") or ""))
            if not filter_value:
                continue
            match = _normalize_filter_match(
                dimension=str(item.get("dimension") or ""),
                value=str(item.get("value") or ""),
                match=str(item.get("match") or "contains"),
            )
            if match == "exact":
                keep = row_value == filter_value
            else:
                keep = filter_value in row_value
            if not keep:
                break
        if keep:
            filtered.append(row)
    return tuple(filtered)


def _operation_from_query(query_text: str) -> str:
    q = _norm(query_text)
    if re.search(r"\babaixo da media\b|\bmenor(?:es)? que a media\b", q):
        return "below_average"
    has_top = bool(re.search(r"\b(maior|melhor|top|mais|domina|ranking)\b", q))
    has_bottom = bool(re.search(r"\b(menor|pior|menos|baixo|menores)\b", q))
    if has_top and has_bottom:
        return "top_and_bottom"
    if has_bottom:
        return "ranking_asc"
    if has_top:
        return "ranking_desc"
    if re.search(r"\b(cada|por|liste|lista|mostre|tod[oa]s?)\b", q):
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
    if measure.column in {"ticket_medio", "ticket_medio_item", "ticket_medio_os"} and "ticket" in q:
        score += 20
    if measure.column == "ticket_medio_item" and "item" in q:
        score += 12
    if measure.column in {
        "total_vendas",
        "total_os",
        "qtd_recebimentos",
        "total_recebimentos",
        "quantidade_os",
        "quantidade_vendida",
    }:
        if "volume" in q or "quantidade" in q or "qtd" in q:
            score += 18
    if measure.column == "quantidade_vendida" and (
        ("volume" in q or "quantidade" in q or "qtd" in q)
        and ("item" in q or "itens" in q or "produto" in q or "servico" in q)
    ):
        score += 10
    if measure.column in {"faturamento", "valor_total", "valor_total_recebido", "total_recebido"}:
        if any(t in q for t in ("faturamento", "faturou", "receita", "valor", "recebido")):
            score += 16
    if measure.column == "percentual_faturamento" and any(
        t in q for t in ("percentual", "participacao", "share", "curva abc")
    ):
        score += 24
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
    if operation != "below_average" and operation not in capability.supported_operations:
        operation = "ranking_desc" if "ranking_desc" in capability.supported_operations else capability.supported_operations[0]

    return AnswerPlan(
        template_slug=template_slug,
        measure=measure_key,
        dimension=dimension_key,
        operation=operation,
        entity_filters=(),
        reason="capability_match",
    )


def _answer_plan_from_hints(
    hints: Mapping[str, Any],
    *,
    query_text: str,
    template_slug: str,
    capability: AnswerCapability,
) -> AnswerPlan | None:
    measure = _hint_key(hints.get("selected_metric"), capability.measures)
    dimension = _hint_key(hints.get("selected_dimension"), capability.dimensions)
    operation_raw = hints.get("selected_operation")
    operation = str(operation_raw).strip() if operation_raw is not None else ""
    if measure is None and dimension is None and not operation:
        return None
    if measure is None:
        measure = capability.default_measure
    if dimension is None:
        dimension = capability.default_dimension
    derived_operation = _operation_from_query(query_text)
    result_scope = _result_scope_from_hints(hints)
    sort = _sort_from_hints(hints, capability)
    if isinstance(result_scope, Mapping) and result_scope.get("mode") == "all":
        selected_operation = "list"
    elif derived_operation == "below_average":
        selected_operation = derived_operation
    elif operation == "below_average" or operation in capability.supported_operations:
        selected_operation = operation
    else:
        selected_operation = (
            "ranking_desc" if "ranking_desc" in capability.supported_operations else capability.supported_operations[0]
        )
    return AnswerPlan(
        template_slug=template_slug,
        measure=measure,
        dimension=dimension,
        operation=selected_operation,
        entity_filters=_entity_filters_from_hints(hints, capability),
        result_scope=result_scope,
        sort=sort,
        reason="validated_semantic_hints",
    )


def _hint_key(value: Any, allowed: Mapping[str, Any]) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw in allowed:
        return raw
    raw_lower = raw.lower()
    for key in allowed:
        if key.lower() == raw_lower:
            return key
    return None


def _aggregate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    measure: MeasureCapability,
    dimension: DimensionCapability | None,
    measures: Mapping[str, MeasureCapability] | None = None,
) -> list[dict[str, Any]]:
    if dimension is None:
        out: list[dict[str, Any]] = []
        for row in rows:
            if measure.column in row:
                out.append(dict(row))
        return out

    grouped: dict[str, dict[str, Any]] = {}
    values: defaultdict[str, list[float]] = defaultdict(list)
    additive_measures = tuple(item for item in (measures or {}).values() if item.additive)
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
            for additive_measure in additive_measures:
                if additive_measure.column in row and _to_float(row.get(additive_measure.column)) is not None:
                    grouped[label][additive_measure.column] = 0.0
        if measure.additive:
            grouped[label][measure.column] = float(grouped[label][measure.column]) + n
        else:
            values[label].append(n)
        for additive_measure in additive_measures:
            if additive_measure.column == measure.column:
                continue
            value = _to_float(row.get(additive_measure.column))
            if value is not None:
                grouped[label][additive_measure.column] = float(grouped[label].get(additive_measure.column, 0.0)) + value

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
    limit: int | None = 10,
) -> ProjectedAnswer | None:
    """Projeta rows SQL em ranking/lista/top-bottom usando a coluna certa."""
    measure = capability.measures.get(plan.measure)
    if measure is None:
        return None
    dimension = capability.dimensions.get(plan.dimension) if plan.dimension else None
    filtered_rows = filter_rows_for_entity_filters(
        rows,
        entity_filters=plan.entity_filters,
        capability=capability,
    )
    projected = _aggregate_rows(filtered_rows, measure=measure, dimension=dimension, measures=capability.measures)
    projected = [r for r in projected if _to_float(r.get(measure.column)) is not None]
    if not projected:
        return None

    sort_field = str((plan.sort or {}).get("field") or "")
    sort_direction = str((plan.sort or {}).get("direction") or "").lower()
    if not sort_direction:
        sort_direction = "asc" if plan.operation == "ranking_asc" else "desc"
    sort_measure = capability.measures.get(sort_field)
    sort_dimension = capability.dimensions.get(sort_field)
    sort_column = (
        sort_measure.column
        if sort_measure is not None
        else sort_dimension.column
        if sort_dimension is not None
        else measure.column
    )
    reverse = sort_direction != "asc"
    ordered = sorted(
        projected,
        key=lambda r: _sort_value(r.get(sort_column)),
        reverse=reverse,
    )
    top = ordered[0]
    bottom = sorted(projected, key=lambda r: _to_float(r.get(measure.column)) or 0.0)[0]
    selected_limit = _selected_limit(plan=plan, row_count=len(ordered), default_limit=limit)
    selected = tuple(ordered[:selected_limit])

    dim_label = dimension.label if dimension is not None else "registro"
    top_label = _row_label(top, dimension) if dimension is not None else "maior valor"
    top_value = _format_value(top.get(measure.column), measure.kind)
    parts: list[str] = []
    if plan.operation == "below_average":
        nums = [_to_float(r.get(measure.column)) for r in projected]
        numeric_values = [n for n in nums if n is not None]
        mean = sum(numeric_values) / len(numeric_values)
        below = tuple(
            r
            for r in sorted(projected, key=lambda item: _to_float(item.get(measure.column)) or 0.0)
            if (_to_float(r.get(measure.column)) or 0.0) < mean
        )
        lines = [
            f"Resposta direta: {dim_label}s com {measure.label} abaixo da média "
            f"({_format_value(mean, measure.kind)}):"
        ]
        for i, row in enumerate(below[: max(1, limit)], start=1):
            label = _row_label(row, dimension)
            value = _format_value(row.get(measure.column), measure.kind)
            lines.append(f"{i}. {label}: {value}")
        if not below:
            lines.append("Nenhum registro abaixo da média na evidência disponível.")
        parts.append("\n".join(lines))
        selected = below
        top = below[0] if below else top
    elif plan.operation == "top_and_bottom":
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


def _selected_limit(*, plan: AnswerPlan, row_count: int, default_limit: int | None) -> int:
    scope = plan.result_scope if isinstance(plan.result_scope, Mapping) else None
    mode = str(scope.get("mode") or "").lower() if scope is not None else ""
    raw_limit = scope.get("limit") if scope is not None else None
    if mode == "all" or plan.operation == "list":
        return row_count
    if raw_limit not in (None, ""):
        try:
            return min(row_count, max(1, int(raw_limit)))
        except (TypeError, ValueError):
            pass
    if default_limit is None:
        return row_count
    return min(row_count, max(1, default_limit))


def _sort_value(value: Any) -> tuple[int, float | str]:
    n = _to_float(value)
    if n is not None:
        return (0, n)
    return (1, _norm(str(value)))


def build_full_list_summary(
    projected: ProjectedAnswer,
    *,
    templates: "QueryTemplateRegistry",
) -> str | None:
    """Reprojeta todas as linhas como lista completa (escopo ``all``) para e-mail."""
    capability = _capability_for_projected(projected, templates)
    if capability is None:
        return None
    full_plan = replace(
        projected.plan,
        operation="list",
        result_scope={"mode": "all", "limit": None},
    )
    full = project_answer(projected.rows, plan=full_plan, capability=capability)
    return full.summary if full is not None else None


def build_projected_answer(
    query_text: str,
    results: Sequence[AnalyticsResult],
    *,
    templates: "QueryTemplateRegistry",
) -> ProjectedAnswer | None:
    """Escolhe o melhor resultado de template e constrói uma resposta direta."""
    best: tuple[int, ProjectedAnswer] | None = None
    q = _norm(query_text)
    for result in results:
        projected = _project_result(query_text, result, templates=templates)
        if projected is None:
            continue
        capability = _capability_for_projected(projected, templates)
        if capability is None:
            continue
        plan = projected.plan
        measure = capability.measures.get(plan.measure)
        dimension = capability.dimensions.get(plan.dimension) if plan.dimension else None
        score = 0
        if measure is not None:
            score += _score_measure(measure, query_text)
        if dimension is not None:
            score += _score_dimension(dimension, query_text)
        slug = plan.template_slug
        if slug in q:
            score += 20
        if result.rows:
            score += 2
        candidate = (score, projected)
        if best is None or candidate[0] > best[0]:
            best = candidate

    if best is None:
        return None
    return best[1]


def build_projected_answer_set(
    query_text: str,
    results: Sequence[AnalyticsResult],
    *,
    templates: "QueryTemplateRegistry",
) -> ProjectedAnswerSet | None:
    """Projeta cada resultado de uma colecao/fanout em secoes objetivas."""
    answers: list[ProjectedAnswer] = []
    collection_slug: str | None = None
    presentation_mode = "sections"
    for result in results:
        hints = result.plan.hints if isinstance(result.plan.hints, Mapping) else {}
        raw_collection = hints.get("collection_slug")
        if isinstance(raw_collection, str) and raw_collection.strip():
            collection_slug = collection_slug or raw_collection.strip()
        raw_mode = hints.get("collection_presentation_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            presentation_mode = raw_mode.strip()
        projected = _project_result(query_text, result, templates=templates)
        if projected is not None:
            answers.append(projected)

    if not answers:
        return None

    sections = [
        f"## {answer.plan.template_slug}\n{answer.summary}"
        for answer in answers
    ]
    summary = "Resposta direta composta:\n\n" + "\n\n".join(sections)
    if _is_fechamento_gerencial_por_mes(collection_slug, answers):
        return _build_fechamento_gerencial_por_mes_projection(
            answers,
            collection_slug=collection_slug,
            presentation_mode=presentation_mode,
            templates=templates,
        )
    return ProjectedAnswerSet(
        collection_slug=collection_slug,
        presentation_mode=presentation_mode,
        summary=summary,
        answers=tuple(answers),
    )


def _project_result(
    query_text: str,
    result: AnalyticsResult,
    *,
    templates: "QueryTemplateRegistry",
) -> ProjectedAnswer | None:
    hints = result.plan.hints if isinstance(result.plan.hints, Mapping) else {}
    slug = hints.get("template_slug")
    if not isinstance(slug, str):
        return None
    template = templates.get(slug)
    capability = getattr(template, "capability", None)
    if template is None or capability is None:
        return None
    plan = _answer_plan_from_hints(
        hints,
        query_text=query_text,
        template_slug=slug,
        capability=capability,
    )
    if plan is None:
        plan = infer_answer_plan(query_text, template_slug=slug, capability=capability)
    return project_answer(result.rows, plan=plan, capability=capability)


_FECHAMENTO_SECTION_ORDER = {
    "fechamento_faturamento_tipo_pagamento": 10,
    "fechamento_faturamento_tipo_venda": 20,
    "fechamento_faturamento_tipo_venda_produtos": 30,
    "fechamento_faturamento_comissao_concessionaria_periodo": 40,
    "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo": 50,
    "fechamento_producao_servico": 60,
    "fechamento_producao_produto": 70,
    "fechamento_parcelamento_cartao": 80,
    "fechamento_taxas_cartao_credito": 90,
}

_FECHAMENTO_LABELS = {
    "fechamento_faturamento_tipo_pagamento": "Faturamento por tipo de pagamento",
    "fechamento_faturamento_tipo_venda": "Faturamento por tipo de venda",
    "fechamento_faturamento_tipo_venda_produtos": "Faturamento por tipo de venda de produtos",
    "fechamento_faturamento_comissao_concessionaria_periodo": "Faturamento e comissão por concessionária",
    "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo": "Faturamento e comissão por tipo de O.S.",
    "fechamento_producao_servico": "Produção por serviço",
    "fechamento_producao_produto": "Produção por produto",
    "fechamento_parcelamento_cartao": "Parcelamento de cartão",
    "fechamento_taxas_cartao_credito": "Taxas de cartão de crédito",
}
_COMISSAO_TIPO_OS_SLUG = "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo"


def _is_fechamento_gerencial_por_mes(
    collection_slug: str | None,
    answers: Sequence[ProjectedAnswer],
) -> bool:
    if collection_slug == "fechamento_gerencial_por_mes":
        return True
    if collection_slug:
        return False
    return bool(answers) and all(answer.plan.template_slug.startswith("fechamento_") for answer in answers)


def _build_fechamento_gerencial_por_mes_projection(
    answers: Sequence[ProjectedAnswer],
    *,
    collection_slug: str | None,
    presentation_mode: str,
    templates: "QueryTemplateRegistry",
) -> ProjectedAnswerSet:
    ordered_answers = tuple(
        sorted(
            answers,
            key=lambda answer: (
                _FECHAMENTO_SECTION_ORDER.get(answer.plan.template_slug, 999),
                answer.plan.template_slug,
            ),
        )
    )
    executive_sections = tuple(
        section
        for answer in ordered_answers
        if (section := _fechamento_section(answer, templates=templates)) is not None
    )
    managerial_totals = _fechamento_managerial_totals(executive_sections)
    headline = _fechamento_headline(managerial_totals, len(ordered_answers))
    data_quality = {
        "templates_projected": len(ordered_answers),
        "rows_projected": sum(len(answer.rows) for answer in ordered_answers),
        "collection_slug": collection_slug or "fechamento_gerencial_por_mes",
        "source": "ProjectedAnswerSet",
    }
    lines = [headline, "", "Seções executivas:"]
    for section in executive_sections:
        total = section.get("total") or "n/d"
        top = section.get("top") or "sem movimentação"
        top_value = section.get("top_value") or "n/d"
        lines.append(f"- {section['label']}: total {total}; líder {top} ({top_value}).")
    summary = "\n".join(lines)
    section_detail = _fechamento_section_detail(ordered_answers, templates=templates)
    return ProjectedAnswerSet(
        collection_slug=collection_slug,
        presentation_mode=presentation_mode,
        summary=summary,
        answers=ordered_answers,
        headline=headline,
        executive_summary=summary,
        section_detail=section_detail,
        executive_sections=executive_sections,
        managerial_totals=managerial_totals,
        data_quality=data_quality,
    )


def _fechamento_section(
    answer: ProjectedAnswer,
    *,
    templates: "QueryTemplateRegistry",
) -> dict[str, Any] | None:
    capability = _capability_for_projected(answer, templates)
    if capability is None:
        return None
    measure = capability.measures.get(answer.plan.measure)
    dimension = capability.dimensions.get(answer.plan.dimension) if answer.plan.dimension else None
    if measure is None:
        return None
    values = [_to_float(row.get(measure.column)) for row in answer.rows]
    numeric_values = [value for value in values if value is not None]
    total = sum(numeric_values) if numeric_values else None
    top = answer.top or (answer.rows[0] if answer.rows else None)
    top_value_num = _to_float(top.get(measure.column)) if isinstance(top, Mapping) else None
    share = (top_value_num / total * 100.0) if total and top_value_num is not None else None
    zero_count = sum(1 for value in numeric_values if value == 0.0)
    warnings: list[str] = []
    if not answer.rows:
        warnings.append("sem movimentação")
    if zero_count:
        warnings.append(f"{zero_count} registro(s) com valor zero")
    return {
        "template_slug": answer.plan.template_slug,
        "label": _FECHAMENTO_LABELS.get(answer.plan.template_slug, answer.plan.template_slug),
        "measure": answer.plan.measure,
        "dimension": answer.plan.dimension,
        "total": _format_value(total, measure.kind) if total is not None else None,
        "total_raw": total,
        "top": _row_label(top, dimension) if isinstance(top, Mapping) else None,
        "top_value": _format_value(top_value_num, measure.kind) if top_value_num is not None else None,
        "top_value_raw": top_value_num,
        "share_percent": _format_value(share, "percent") if share is not None else None,
        "row_count": len(answer.rows),
        "warnings": tuple(warnings),
    }


def _fechamento_section_detail(
    answers: Sequence[ProjectedAnswer],
    *,
    templates: "QueryTemplateRegistry",
    limit_per_section: int = 10,
) -> str:
    lines = ["Detalhe por seção do fechamento gerencial:"]
    for answer in answers:
        capability = _capability_for_projected(answer, templates)
        if capability is None:
            continue
        measure = capability.measures.get(answer.plan.measure)
        dimension = capability.dimensions.get(answer.plan.dimension) if answer.plan.dimension else None
        if measure is None:
            continue
        if answer.plan.template_slug == _COMISSAO_TIPO_OS_SLUG:
            lines.extend(_fechamento_comissao_tipo_os_table(answer, limit_per_section=limit_per_section))
            continue
        label = _FECHAMENTO_LABELS.get(answer.plan.template_slug, answer.plan.template_slug)
        lines.extend(["", f"## {label}", f"Template: {answer.plan.template_slug}", f"Linhas disponíveis: {len(answer.rows)}"])
        values = [_to_float(row.get(measure.column)) for row in answer.rows]
        total = sum(value for value in values if value is not None)
        for index, row in enumerate(answer.rows[:limit_per_section], start=1):
            value_num = _to_float(row.get(measure.column))
            value = _format_value(value_num, measure.kind) if value_num is not None else "n/d"
            share = _format_value((value_num / total * 100.0), "percent") if total and value_num is not None else None
            label_value = _row_label(row, dimension)
            suffix = f" ({share})" if share else ""
            lines.append(f"{index}. {label_value}: {value}{suffix}")
        omitted = max(0, len(answer.rows) - limit_per_section)
        if omitted:
            lines.append(f"... mais {omitted} linha(s) disponíveis em answers[].rows.")
        if not answer.rows:
            lines.append("Sem movimentação na evidência disponível.")
    return "\n".join(lines)


def _fechamento_comissao_tipo_os_table(answer: ProjectedAnswer, *, limit_per_section: int) -> list[str]:
    rows = _commission_type_rows(answer.rows)
    lines = [
        "",
        "## Comissão por tipo de O.S.",
        f"Template: {answer.plan.template_slug}",
        f"Linhas disponíveis: {len(rows)}",
        "concessionaria | venda normal | financiamento | total comissão",
    ]
    for row in rows[:limit_per_section]:
        lines.append(
            " | ".join(
                (
                    str(row["concessionaria"]),
                    _format_value(row["comissao_venda_normal"], "money"),
                    _format_value(row["comissao_financiamento"], "money"),
                    _format_value(row["total_comissao"], "money"),
                )
            )
        )
    omitted = max(0, len(rows) - limit_per_section)
    if omitted:
        lines.append(f"... mais {omitted} linha(s) disponíveis em answers[].rows.")
    if not rows:
        lines.append("Sem movimentação na evidência disponível.")
    return lines


def _commission_type_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = str(row.get("concessionaria") or "").strip()
        if not label:
            continue
        target = grouped.setdefault(
            label,
            {
                "concessionaria": label,
                "comissao_venda_normal": 0.0,
                "comissao_financiamento": 0.0,
                "total_comissao": 0.0,
            },
        )
        for key in ("comissao_venda_normal", "comissao_financiamento", "total_comissao"):
            target[key] = float(target[key]) + (_to_float(row.get(key)) or 0.0)
    return sorted(grouped.values(), key=lambda row: _to_float(row.get("total_comissao")) or 0.0, reverse=True)


def _fechamento_managerial_totals(
    sections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_slug = {str(section.get("template_slug")): section for section in sections}
    totals: dict[str, Any] = {}
    payment = by_slug.get("fechamento_faturamento_tipo_pagamento")
    if payment and payment.get("total") is not None:
        totals["financial_net"] = {
            "label": "Faturamento líquido por forma de pagamento",
            "source_template": "fechamento_faturamento_tipo_pagamento",
            "value": payment["total"],
            "value_raw": payment.get("total_raw"),
        }
    sale_type = by_slug.get("fechamento_faturamento_tipo_venda")
    if sale_type and sale_type.get("total") is not None:
        totals["sales_type_total"] = {
            "label": "Faturamento por tipo de venda",
            "source_template": "fechamento_faturamento_tipo_venda",
            "value": sale_type["total"],
            "value_raw": sale_type.get("total_raw"),
        }
    fees = by_slug.get("fechamento_taxas_cartao_credito")
    if fees and fees.get("total") is not None:
        totals["card_fees"] = {
            "label": "Taxas de cartão",
            "source_template": "fechamento_taxas_cartao_credito",
            "value": fees["total"],
            "value_raw": fees.get("total_raw"),
        }
    return totals


def _fechamento_headline(managerial_totals: Mapping[str, Any], template_count: int) -> str:
    financial = managerial_totals.get("financial_net")
    if isinstance(financial, Mapping) and financial.get("value"):
        return f"{financial['label']}: {financial['value']}"
    sale_type = managerial_totals.get("sales_type_total")
    if isinstance(sale_type, Mapping) and sale_type.get("value"):
        return f"{sale_type['label']}: {sale_type['value']}"
    return f"Fechamento gerencial: dados executados em {template_count} template(s)"


def _capability_for_projected(
    projected: ProjectedAnswer,
    templates: "QueryTemplateRegistry",
) -> AnswerCapability | None:
    template = templates.get(projected.plan.template_slug)
    capability = getattr(template, "capability", None)
    return capability if isinstance(capability, AnswerCapability) else None
