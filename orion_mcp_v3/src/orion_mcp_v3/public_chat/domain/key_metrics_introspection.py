"""Introspecção dinâmica de índices ``key_metrics``."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.requirement_kind import RequirementKind
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import (
    AggregationRule,
    Comparator,
    FactSemantics,
    SourcePriority,
)
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.key_metrics_contract import (
    DIMENSION_ALIASES,
    METRIC_KIND_ALIASES,
    extract_meta,
)
from orion_mcp_v3.public_chat.domain.key_metrics_reader import (
    entity_slug,
    normalize_key_metrics_entry,
    rows_from_key_metrics_entry,
    sample_labels_from_entry,
)
from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit
from orion_mcp_v3.public_chat.domain.period_selection import (
    contract_has_parcel_filter,
    entity_for_dimension,
    is_predicate_filter_value,
    message_has_parcel_count,
    non_period_entity_filters,
)
from orion_mcp_v3.public_chat.domain.period_utils import normalize_period_key

_DYNAMIC_PREFIX = "dynamic:"
_MIN_ACCEPT_SCORE = 3.0
_AMBIGUITY_DELTA = 0.5


class MatchMethod(str, Enum):
    META_EXACT = "meta_exact"
    HEURISTIC = "heuristic"
    LLM = "llm"


class HeuristicStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class KeyMetricsIndexEntry:
    key: str
    dimension: str
    metric_kind: str
    entity_field: str
    value_field: str
    schema: str
    sample_labels: tuple[str, ...]
    shape: str
    subdimension: str | None = None
    score_breakdown: tuple[tuple[str, float], ...] = ()
    origin_id: int | None = None
    context_key: str | None = None


@dataclass(frozen=True, slots=True)
class SourceMatchResult:
    status: HeuristicStatus
    entry: KeyMetricsIndexEntry | None = None
    candidates: tuple[KeyMetricsIndexEntry, ...] = ()
    score: float = 0.0
    match_method: MatchMethod | None = None
    score_breakdown: tuple[tuple[str, float], ...] = ()


def build_key_metrics_index(
    key_metrics: Mapping[str, Any],
    *,
    origin_id: int | None = None,
    context_key: str | None = None,
) -> tuple[KeyMetricsIndexEntry, ...]:
    entries: list[KeyMetricsIndexEntry] = []
    for key, raw in key_metrics.items():
        if key.startswith("_"):
            continue
        meta = extract_meta(key, raw)
        if meta is None:
            continue
        normalized = normalize_key_metrics_entry(key, raw)
        rows = rows_from_key_metrics_entry(key, raw)
        labels = sample_labels_from_entry(rows, entity_field=meta.get("entity_field", "tipo"))
        shape = normalized.shape
        if shape == "scalar":
            continue
        entries.append(
            KeyMetricsIndexEntry(
                key=key,
                dimension=str(meta.get("dimension") or ""),
                metric_kind=str(meta.get("metric_kind") or "revenue"),
                entity_field=str(meta.get("entity_field") or "tipo"),
                value_field=str(meta.get("value_field") or "valor"),
                schema=str(meta.get("schema") or "ranked_list"),
                sample_labels=labels,
                shape=shape,
                subdimension=str(meta["subdimension"]) if meta.get("subdimension") else None,
                origin_id=origin_id,
                context_key=context_key,
            )
        )
    return tuple(entries)


def build_key_metrics_index_from_hits(
    hits: tuple[KnowledgeHit, ...],
) -> tuple[KeyMetricsIndexEntry, ...]:
    return tuple(
        entry
        for hit in hits
        for entry in build_key_metrics_index(
            hit.key_metrics,
            origin_id=hit.origin_id,
            context_key=hit.context_key,
        )
    )


def resolve_scalar_metrics(key_metrics: Mapping[str, Any]) -> tuple[tuple[str, float], ...]:
    scalars: list[tuple[str, float]] = []
    for key, raw in key_metrics.items():
        normalized = normalize_key_metrics_entry(key, raw)
        if normalized.shape != "scalar":
            continue
        value = normalized.scalar_value
        if value is not None:
            scalars.append((key, value))
    return tuple(scalars)


def dimensions_from_contract(contract: IntentContract, message: str = "") -> tuple[str, ...]:
    dims: list[str] = []
    text = _normalize_text(message)

    if contract.dimension:
        dims.append(_normalize_dimension(contract.dimension))

    for filt in non_period_entity_filters(contract):
        if not filt.dimension or is_predicate_filter_value(filt.value or ""):
            continue
        normalized = _normalize_dimension(filt.dimension)
        if normalized in DIMENSION_ALIASES and normalized not in dims:
            dims.append(normalized)

    keyword_map = (
        ("servico", ("servico", "serviço", "servicos", "serviços")),
        ("produto", ("produto", "produtos")),
        ("parcelas", ("parcelas", "parcelamento", "parcela")),
        ("forma_pagamento", ("forma de pagamento", "formas de pagamento", "pix")),
        ("tipo_de_venda", ("tipo de venda", "tipos de venda")),
        ("concessionaria", ("concessionaria", "concessionária", "concessionarias")),
    )
    for dimension, needles in keyword_map:
        if any(needle in text for needle in needles) and dimension not in dims:
            dims.append(dimension)

    if message_has_parcel_count(message) or contract_has_parcel_filter(contract):
        dims = [dimension for dimension in dims if dimension != "forma_pagamento"]
        if "parcelas" not in dims:
            dims.insert(0, "parcelas")
    elif any(needle in text for needle in ("pagamento", "forma de pagamento", "formas de pagamento")):
        if "forma_pagamento" not in dims:
            dims.append("forma_pagamento")

    if not dims and _mentions_revenue(contract, message):
        dims.append("periodo")

    return tuple(dict.fromkeys(dims))


def find_key_metrics_source(
    index: tuple[KeyMetricsIndexEntry, ...],
    *,
    dimension: str | None,
    metric_kind: str | None = None,
    entity: str | None = None,
    message: str = "",
) -> SourceMatchResult:
    if not index:
        return SourceMatchResult(status=HeuristicStatus.NOT_FOUND)

    target_dimension = _normalize_dimension(dimension) if dimension else None
    target_metric = _normalize_metric_kind(metric_kind) if metric_kind else None
    text = _normalize_text(message)

    scored: list[tuple[KeyMetricsIndexEntry, float, tuple[tuple[str, float], ...]]] = []
    for entry in index:
        score, breakdown = _score_entry(
            entry,
            target_dimension=target_dimension,
            target_metric=target_metric,
            entity=entity,
            message=text,
        )
        if score > 0:
            scored.append((entry, score, breakdown))

    if not scored:
        return SourceMatchResult(status=HeuristicStatus.NOT_FOUND)

    scored.sort(key=lambda item: item[1], reverse=True)
    best_entry, best_score, best_breakdown = scored[0]
    if best_score < _MIN_ACCEPT_SCORE:
        return SourceMatchResult(status=HeuristicStatus.NOT_FOUND, score=best_score, score_breakdown=best_breakdown)

    if len(scored) > 1 and (best_score - scored[1][1]) < _AMBIGUITY_DELTA:
        return SourceMatchResult(
            status=HeuristicStatus.AMBIGUOUS,
            candidates=tuple(item[0] for item in scored[:3]),
            score=best_score,
            score_breakdown=best_breakdown,
        )

    method = MatchMethod.META_EXACT if best_breakdown and best_breakdown[0][0] == "meta_dimension" else MatchMethod.HEURISTIC
    return SourceMatchResult(
        status=HeuristicStatus.RESOLVED,
        entry=replace(best_entry, score_breakdown=best_breakdown),
        score=best_score,
        match_method=method,
        score_breakdown=best_breakdown,
    )


def scope_axes_for_entry(entry: KeyMetricsIndexEntry) -> frozenset[str]:
    return scope_axes_from_meta_fields(
        dimension=entry.dimension,
        entity_field=entry.entity_field,
        subdimension=entry.subdimension,
    )


def scope_axes_from_meta(meta: Mapping[str, Any]) -> frozenset[str]:
    return scope_axes_from_meta_fields(
        dimension=str(meta.get("dimension") or ""),
        entity_field=str(meta.get("entity_field") or ""),
        subdimension=str(meta["subdimension"]) if meta.get("subdimension") else None,
    )


def scope_axes_from_meta_fields(
    *,
    dimension: str,
    entity_field: str,
    subdimension: str | None,
) -> frozenset[str]:
    axes: set[str] = set()
    if dimension:
        axes.add(_normalize_dimension(dimension))
    if subdimension:
        axes.add(_normalize_dimension(subdimension))
    mapped = _dimension_for_entity_field(entity_field)
    if mapped:
        axes.add(mapped)
    return frozenset(axes)


def scope_axes_from_hit_meta(hit: KnowledgeHit, matched_key: str | None) -> frozenset[str]:
    if not matched_key:
        return frozenset()
    raw = hit.key_metrics.get(matched_key)
    if raw is None:
        return frozenset()
    meta = extract_meta(matched_key, raw)
    if meta is None:
        return frozenset()
    return scope_axes_from_meta(meta)


def partition_scope_entities(
    scope_entities: tuple[tuple[str, str], ...],
    axes: frozenset[str],
    *,
    exclude_dimensions: tuple[str, ...] = (),
) -> tuple[tuple[tuple[str, str], ...], tuple[dict[str, str], ...]]:
    excluded = {_normalize_dimension(dimension) for dimension in exclude_dimensions}
    applicable: list[tuple[str, str]] = []
    discarded: list[dict[str, str]] = []
    for dimension, value in scope_entities:
        dim_norm = _normalize_dimension(dimension)
        if dim_norm in excluded:
            discarded.append(
                {"dimension": dimension, "value": value, "reason": "excluded_loop_dim"},
            )
            continue
        if dim_norm in axes:
            applicable.append((dimension, value))
            continue
        discarded.append(
            {"dimension": dimension, "value": value, "reason": "not_in_schema"},
        )
    return tuple(applicable), tuple(discarded)


def build_dynamic_requirement(
    entry: KeyMetricsIndexEntry,
    *,
    contract: IntentContract,
    match_method: MatchMethod | None = None,
    heuristic_status: HeuristicStatus = HeuristicStatus.RESOLVED,
    message: str = "",
    entity: str | None = None,
    period: str | None = None,
    scope_entities: tuple[tuple[str, str], ...] = (),
    include_period_in_key: bool = False,
    exclude_scope_dimensions: tuple[str, ...] = (),
) -> FactRequirement:
    aggregation, comparator = _aggregation_for_contract(contract, entry)
    value_field = _value_field_for_contract(contract, entry)
    resolved_entity = _resolve_requirement_entity(
        contract,
        entry=entry,
        entity=entity,
        message=message,
    )
    resolved_period = period if period is not None else contract.period
    axes = scope_axes_for_entry(entry)
    applicable_scope, discarded_scope = partition_scope_entities(
        scope_entities,
        axes,
        exclude_dimensions=exclude_scope_dimensions,
    )
    resolved_entity = _sanitize_entity_against_discarded(resolved_entity, discarded_scope)
    fact_key = entity_scoped_fact_key(entry.key, resolved_entity)
    if include_period_in_key and resolved_period:
        fact_key = period_scoped_fact_key(fact_key, resolved_period)
    scope_axes_snapshot = tuple(sorted(axes))
    source_resolution_mode = "index_pinned" if entry.origin_id is not None else None
    return FactRequirement(
        fact_key=fact_key,
        metric=contract.metric,
        dimension=entry.dimension,
        entity=resolved_entity,
        period=resolved_period,
        operation=contract.operation,
        requirement_kind=RequirementKind.LOOKUP,
        matched_key=entry.key,
        match_method=match_method.value if match_method else MatchMethod.HEURISTIC.value,
        heuristic_status=heuristic_status.value,
        source_origin_id=entry.origin_id,
        source_context_key=entry.context_key,
        source_resolution_mode=source_resolution_mode,
        scope_entities=applicable_scope,
        discarded_scope=discarded_scope,
        semantics=FactSemantics(
            fact_key=fact_key,
            aggregation_rule=aggregation,
            comparator=comparator,
            source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
            value_kind="currency" if value_field != "percentual" else "pct",
            allows_multiple_values=aggregation in (AggregationRule.MIN, AggregationRule.MAX),
            memory_themes=("fechamento_gerencial", "fechamento_gerencial_mensal"),
            key_metrics_keys=(entry.key,),
            key_metrics_entity_field=entry.entity_field,
            key_metrics_value_field=value_field,
            key_metrics_scope_axes=scope_axes_snapshot,
        ),
    )


def _sanitize_entity_against_discarded(
    entity: str | None,
    discarded_scope: tuple[dict[str, str], ...],
) -> str | None:
    if entity is None or entity == "":
        return None
    for item in discarded_scope:
        if item.get("value") == entity and item.get("reason") == "not_in_schema":
            return None
    return entity


def entity_scoped_fact_key(index_key: str, entity: str | None) -> str:
    base = f"{_DYNAMIC_PREFIX}{index_key}"
    if not entity:
        return base
    return f"{base}@{entity_slug(entity)}"


def period_scoped_fact_key(base_key: str, period: str | None) -> str:
    if not period:
        return base_key
    return f"{base_key}@{period}"


def period_from_context_key(context_key: str | None) -> str | None:
    if not context_key:
        return None
    return normalize_period_key(context_key)


def periods_from_index_entries(
    entries: tuple[KeyMetricsIndexEntry, ...],
) -> tuple[str, ...]:
    periods: list[str] = []
    for entry in entries:
        period = period_from_context_key(entry.context_key)
        if period:
            periods.append(period)
    return tuple(dict.fromkeys(periods))


def same_key_only_period_ambiguity(
    candidates: tuple[KeyMetricsIndexEntry, ...],
) -> bool:
    if len(candidates) < 2:
        return False
    keys = {entry.key for entry in candidates}
    if len(keys) != 1:
        return False
    return len(periods_from_index_entries(candidates)) >= 2


def expand_same_key_period_from_index(
    index: tuple[KeyMetricsIndexEntry, ...],
    *,
    index_key: str,
) -> tuple[KeyMetricsIndexEntry, ...]:
    by_period: dict[str, KeyMetricsIndexEntry] = {}
    for entry in index:
        if entry.key != index_key:
            continue
        period = period_from_context_key(entry.context_key)
        if period and period not in by_period:
            by_period[period] = entry
    return tuple(by_period[period] for period in sorted(by_period))


def should_include_period_in_fact_key(
    contract: IntentContract,
    index: tuple[KeyMetricsIndexEntry, ...],
    *,
    index_key: str,
) -> bool:
    if contract.period:
        return False
    return len(expand_same_key_period_from_index(index, index_key=index_key)) > 1


def dynamic_fact_key(index_key: str) -> str:
    return f"{_DYNAMIC_PREFIX}{index_key}"


def index_key_from_dynamic(fact_key: str) -> str | None:
    if not fact_key.startswith(_DYNAMIC_PREFIX):
        return None
    rest = fact_key[len(_DYNAMIC_PREFIX) :]
    if "@" in rest:
        rest = rest.split("@", 1)[0]
    if ":" in rest:
        rest = rest.split(":", 1)[0]
    return rest or None


def available_key_metrics_payload(index: tuple[KeyMetricsIndexEntry, ...]) -> list[dict[str, object]]:
    return [
        {
            "key": entry.key,
            "dimension": entry.dimension,
            "metric_kind": entry.metric_kind,
            "sample_labels": list(entry.sample_labels[:5]),
            "schema": entry.schema,
            "origin_id": entry.origin_id,
            "context_key": entry.context_key,
        }
        for entry in index
    ]


def _score_entry(
    entry: KeyMetricsIndexEntry,
    *,
    target_dimension: str | None,
    target_metric: str | None,
    entity: str | None,
    message: str,
) -> tuple[float, tuple[tuple[str, float], ...]]:
    breakdown: list[tuple[str, float]] = []
    score = 0.0

    if target_dimension:
        if entry.dimension == target_dimension:
            score += 5.0
            breakdown.append(("meta_dimension", 5.0))
        elif _period_dimension_can_use_entry(entry, target_dimension, target_metric):
            score += 4.0
            breakdown.append(("period_revenue_source", 4.0))
            priority = _period_revenue_source_priority(entry.key)
            if priority:
                score += priority
                breakdown.append(("period_revenue_source_priority", priority))
        elif _dimension_matches(entry.dimension, target_dimension):
            score += 3.5
            breakdown.append(("dimension_alias", 3.5))
        else:
            segment_score = _segment_dimension_score(entry.key, target_dimension)
            if segment_score:
                score += segment_score
                breakdown.append(("segment_match", segment_score))

    if target_metric:
        if entry.metric_kind == target_metric:
            score += 2.0
            breakdown.append(("metric_kind", 2.0))
        elif _metric_kind_matches(entry.metric_kind, target_metric):
            score += 1.0
            breakdown.append(("metric_kind_alias", 1.0))

    key_boost = _key_token_message_boost(entry.key, message)
    if key_boost:
        score += key_boost
        breakdown.append(("key_token_message_boost", key_boost))

    penalty = _token_penalty(entry.key, target_dimension, message)
    if penalty:
        score -= penalty
        breakdown.append(("token_penalty", -penalty))

    if entity:
        entity_norm = _normalize_text(entity)
        if any(entity_norm in _normalize_text(label) for label in entry.sample_labels):
            score += 2.0
            breakdown.append(("entity_in_labels", 2.0))

    boost = _message_boost(entry, message)
    if boost:
        score += boost
        breakdown.append(("message_boost", boost))

    structural = _structural_validation(entry, entity)
    if structural:
        score += structural
        breakdown.append(("structural_validation", structural))

    return score, tuple(breakdown)


def _segment_dimension_score(key: str, target_dimension: str) -> float:
    key_norm = _normalize_text(key)
    aliases = DIMENSION_ALIASES.get(target_dimension, (target_dimension,))
    for alias in aliases:
        token = _normalize_text(alias)
        if not token:
            continue
        pattern = f"_{token}_"
        if pattern in key_norm or key_norm.endswith(f"_{token}") or key_norm.startswith(f"{token}_"):
            if target_dimension == "tipo_de_venda" and "tipo_venda_produtos" in key_norm:
                continue
            return 2.5
    return 0.0


def _token_penalty(key: str, target_dimension: str | None, message: str) -> float:
    key_tokens = set(_segment_tokens(key))
    wanted: set[str] = set()
    if target_dimension:
        wanted.update(_normalize_text(alias) for alias in DIMENSION_ALIASES.get(target_dimension, (target_dimension,)))
    for token in _segment_tokens(message):
        if len(token) > 3:
            wanted.add(token)
    extra = key_tokens - wanted - {"por", "de", "e", "tipo", "faturamento", "comissao"}
    return min(len(extra) * 0.25, 2.0)


def _message_boost(entry: KeyMetricsIndexEntry, message: str) -> float:
    if not message:
        return 0.0
    boost = 0.0
    for label in entry.sample_labels[:8]:
        label_norm = _normalize_text(label)
        for token in label_norm.split():
            if len(token) > 4 and token in message:
                boost += 0.5
    return min(boost, 2.0)


def _key_token_message_boost(key: str, message: str) -> float:
    if not message:
        return 0.0
    message_tokens = set(_segment_tokens(message))
    key_tokens = set(_segment_tokens(key))
    matched = {token for token in key_tokens if len(token) > 4 and token in message_tokens}
    return min(len(matched) * 1.0, 2.0)


def _structural_validation(entry: KeyMetricsIndexEntry, entity: str | None) -> float:
    if not entity or not entry.sample_labels:
        return 0.0
    entity_norm = _normalize_text(entity)
    if any(entity_norm in _normalize_text(label) for label in entry.sample_labels):
        return 1.0
    return 0.0


def _aggregation_for_contract(
    contract: IntentContract,
    entry: KeyMetricsIndexEntry,
) -> tuple[AggregationRule, Comparator]:
    operation = (contract.operation or "").lower()
    # LOOKUP só quando há entidade/filtro na dimensão do próprio índice.
    # Filtros de escopo em outra dimensão (ex.: forma_pagamento=cartao numa
    # pergunta de ranking de parcelas) não abandonam o ranking.
    if _entity_from_contract(contract, entry_dimension=entry.dimension) or _has_filter_on_entry_dimension(
        contract,
        entry.dimension,
    ):
        return AggregationRule.LOOKUP, Comparator.NONE
    if operation in (PublicOperationType.RANKING_ASC.value, "ranking_asc", "min"):
        return AggregationRule.MIN, Comparator.ASC
    if operation in (PublicOperationType.RANKING_DESC.value, "ranking_desc", "max", "summary"):
        if entry.dimension in ("servico", "produto", "forma_pagamento"):
            return AggregationRule.MAX, Comparator.DESC
    if operation in (PublicOperationType.RANKING_DESC.value, "ranking_desc", "max"):
        return AggregationRule.MAX, Comparator.DESC
    if operation in (PublicOperationType.RANKING_ASC.value, "ranking_asc"):
        return AggregationRule.MIN, Comparator.ASC
    return AggregationRule.LOOKUP, Comparator.NONE


def _has_filter_on_entry_dimension(contract: IntentContract, entry_dimension: str | None) -> bool:
    target = _normalize_dimension(entry_dimension)
    if not target:
        return False
    for filt in non_period_entity_filters(contract):
        if _normalize_dimension(filt.dimension or "") == target and filt.value:
            return True
    return False


def _resolve_requirement_entity(
    contract: IntentContract,
    *,
    entry: KeyMetricsIndexEntry,
    entity: str | None,
    message: str,
) -> str | None:
    """Resolve entidade do requirement.

    Em ranking sem filtro no eixo do índice, `entity=None` do planner significa
    eixo inteiro (ranked_list) — não extrair valor do texto da mensagem.
    """
    if entity is not None and entity != "":
        return entity
    operation = (contract.operation or "").lower()
    ranking_ops = {
        PublicOperationType.RANKING_ASC.value,
        PublicOperationType.RANKING_DESC.value,
        "ranking_asc",
        "ranking_desc",
        "min",
        "max",
    }
    if operation in ranking_ops and not _has_filter_on_entry_dimension(contract, entry.dimension):
        return None
    return _entity_from_contract(contract, entry_dimension=entry.dimension, message=message)

def _value_field_for_contract(contract: IntentContract, entry: KeyMetricsIndexEntry) -> str:
    metric = _normalize_metric_kind(contract.metric)
    if metric == "share":
        return "percentual"
    if metric == "commission":
        return entry.value_field if "comissao" in entry.value_field else "valor_comissao"
    return entry.value_field


def _entity_from_contract(
    contract: IntentContract,
    *,
    entry_dimension: str | None = None,
    message: str = "",
) -> str | None:
    if entry_dimension:
        entity = entity_for_dimension(contract, entry_dimension, message=message)
        if entity is not None and entity != "":
            return entity
    entity = entity_for_dimension(contract, contract.dimension or "", message=message)
    if entity is not None and entity != "":
        return entity
    return None


def _mentions_revenue(contract: IntentContract, message: str) -> bool:
    metric = (contract.metric or "").lower()
    text = message.lower()
    return any(
        needle in metric or needle in text
        for needle in ("faturamento", "faturamos", "receita", "recebemos")
    )


def _dimension_for_entity_field(entity_field: str) -> str | None:
    field_norm = _normalize_dimension(entity_field)
    if not field_norm:
        return None
    for canonical, aliases in DIMENSION_ALIASES.items():
        alias_norms = {_normalize_dimension(alias) for alias in aliases}
        if field_norm == canonical or field_norm in alias_norms:
            return canonical
    return field_norm


def _normalize_dimension(value: str | None) -> str:
    if not value:
        return ""
    normalized = _normalize_text(value)
    for dimension, aliases in DIMENSION_ALIASES.items():
        if normalized in {_normalize_text(alias) for alias in aliases} or normalized == dimension:
            return dimension
    return normalized.replace(" ", "_")


def _normalize_metric_kind(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize_text(value)
    for kind, aliases in METRIC_KIND_ALIASES.items():
        if normalized in {_normalize_text(alias) for alias in aliases} or normalized == kind:
            return kind
    return normalized


def _dimension_matches(entry_dimension: str, target: str) -> bool:
    aliases = DIMENSION_ALIASES.get(target, (target,))
    entry_norm = _normalize_text(entry_dimension)
    return any(entry_norm == _normalize_text(alias) for alias in aliases)


def _metric_kind_matches(entry_kind: str, target: str) -> bool:
    aliases = METRIC_KIND_ALIASES.get(target, (target,))
    entry_norm = _normalize_text(entry_kind)
    return any(entry_norm == _normalize_text(alias) for alias in aliases)


def _period_dimension_can_use_entry(
    entry: KeyMetricsIndexEntry,
    target_dimension: str,
    target_metric: str | None,
) -> bool:
    if target_dimension != "periodo":
        return False
    if target_metric and not (
        entry.metric_kind == target_metric or _metric_kind_matches(entry.metric_kind, target_metric)
    ):
        return False
    if "parcelamento" in _normalize_text(entry.key):
        return False
    return entry.metric_kind in {"revenue", "faturamento"} and entry.value_field in {
        "valor",
        "total",
        "total_faturamento",
    }


def _period_revenue_source_priority(key: str) -> float:
    normalized = _normalize_text(key)
    if normalized == "faturamento_por_tipo_de_venda":
        return 2.0
    if normalized == "faturamento_por_tipo_de_pagamento":
        return 1.0
    return 0.0


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


def _segment_tokens(text: str) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[_\s]+", _normalize_text(text)) if token)
