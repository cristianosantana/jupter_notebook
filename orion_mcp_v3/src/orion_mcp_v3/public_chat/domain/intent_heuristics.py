"""Sinais heurísticos locais para enriquecer o contrato de intenção."""

from __future__ import annotations

import re
import unicodedata

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.intent_parser import (
    _normalize_text,
    extract_mentioned_periods,
    normalize_period,
)
from orion_mcp_v3.public_chat.domain.period_selection import (
    extract_parcel_count_entity,
    normalize_parcel_entity,
)

_RANKING_OPERATIONS = frozenset(
    {
        PublicOperationType.RANKING_ASC.value,
        PublicOperationType.RANKING_DESC.value,
        "ranking_asc",
        "ranking_desc",
        "min",
        "max",
    }
)

_OPERATION_ASC = (
    "pior",
    "piores",
    "menor",
    "menores",
    "minimo",
    "mínimo",
    "minima",
    "mínima",
)
_OPERATION_DESC = (
    "melhor",
    "melhores",
    "maior",
    "maiores",
    "maximo",
    "máximo",
    "maxima",
    "máxima",
    "top",
    "dominante",
    "dominantes",
    "principal",
    "principais",
)

_DIMENSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("forma_pagamento", ("forma de pagamento", "formas de pagamento", "meio de pagamento", "pagamento")),
    ("tipo_venda", ("tipo de venda", "tipos de venda", "tipo de vendas", "tipos de vendas")),
    ("concessionaria", ("concessionária", "concessionaria", "concessionárias", "concessionarias")),
    ("servico", ("serviço", "servico", "serviços", "servicos", "produção por serviço", "producao por servico")),
    ("produto", ("produto", "produtos", "produção por produto", "producao por produto")),
    ("parcelamento", ("parcelamento", "parcela", "parcelas")),
    ("comissao", ("comissão", "comissao", "comissões", "comissoes")),
)

_PAYMENT_METHOD_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"cartao\s+de\s+credito", "cartao de credito"),
    (r"cartao\s+de\s+debito", "cartao de debito"),
    (r"\bpix\b", "pix"),
    (r"\bdinheiro\b", "dinheiro"),
    (r"\bcheque\b", "cheque"),
    (r"deposito\s+bancario", "deposito bancario"),
    (r"\bpermuta\b", "permuta"),
)


def _coalesce_period(period: str | None) -> str | None:
    normalized = normalize_period(period)
    if normalized and len(normalized) <= 64:
        return normalized
    return None


def extract_heuristic_signals(message: str) -> dict[str, str | None]:
    """Extrai operation/dimension/period candidatos da mensagem."""
    text = (message or "").strip().lower()
    if not text:
        return {"operation": None, "dimension": None, "period": None}

    operation: str | None = None
    if _contains_needle(text, _OPERATION_ASC):
        operation = PublicOperationType.RANKING_ASC.value
    elif _contains_needle(text, _OPERATION_DESC):
        operation = PublicOperationType.RANKING_DESC.value

    dimension: str | None = None
    for slug, needles in _DIMENSIONS:
        if _contains_needle(text, needles):
            dimension = slug
            break

    period = normalize_period(message)
    return {"operation": operation, "dimension": dimension, "period": period}


def apply_heuristic_enrichment(contract: IntentContract, message: str) -> IntentContract:
    """Preenche lacunas do contrato LLM com sinais heurísticos."""
    signals = extract_heuristic_signals(message)
    operation = contract.operation or signals["operation"]
    dimension = contract.dimension or signals["dimension"]
    mentioned_periods = extract_mentioned_periods(message)
    period = (
        _coalesce_period(contract.period)
        or signals["period"]
        or (mentioned_periods[0] if mentioned_periods else None)
    )
    sort_direction = contract.sort_direction or _sort_direction_from_operation(operation)
    metric = contract.metric
    if dimension == "forma_pagamento" and not metric:
        metric = "faturamento"
    entity_filters = _merge_period_filters(
        contract.entity_filters,
        primary_period=period,
        periods=mentioned_periods,
    )
    parcel_entity = extract_parcel_count_entity(message)
    if parcel_entity:
        dimension = "parcelas"
        entity_filters = _apply_parcel_filters(entity_filters, parcel_entity)
    entity_filters = _apply_payment_method_filter(entity_filters, message)
    dimension = _dimension_for_cortesia_group(dimension, entity_filters)
    entity_filters = _entity_filters_for_dimension(entity_filters, dimension)
    if dimension == "parcelamento":
        dimension = "parcelas"
    enriched = IntentContract(
        intent=contract.intent,
        metric=metric,
        period=period,
        domain=contract.domain,
        entity_filters=entity_filters,
        confidence=contract.confidence,
        operation=operation,
        dimension=dimension,
        sort_direction=sort_direction,
    )
    return sanitize_ranking_entity_filters(enriched)


def sanitize_ranking_entity_filters(contract: IntentContract) -> IntentContract:
    """Descarta entity_filter na dimensão-alvo quando a operação é ranking.

    Pedir ranking/comparação no eixo X e fixar X num valor único são
    mutuamente exclusivos. Filtros de escopo em outras dimensões permanecem.
    Comparação multi-entidade (2+ valores no mesmo eixo) não passa por aqui —
    só ranking_asc/ranking_desc.
    """
    operation = (contract.operation or "").strip().lower()
    if operation not in _RANKING_OPERATIONS:
        return contract
    target = _normalize_ranking_dimension(contract.dimension)
    if not target:
        return contract
    kept: list[EntityFilter] = []
    for filt in contract.entity_filters:
        dim = _normalize_ranking_dimension(filt.dimension)
        if dim == "periodo":
            kept.append(filt)
            continue
        if dim == target:
            continue
        kept.append(filt)
    if len(kept) == len(contract.entity_filters):
        return contract
    return IntentContract(
        intent=contract.intent,
        metric=contract.metric,
        period=contract.period,
        domain=contract.domain,
        entity_filters=tuple(kept),
        confidence=contract.confidence,
        operation=contract.operation,
        dimension=contract.dimension,
        sort_direction=contract.sort_direction,
    )


def _normalize_ranking_dimension(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"\s+", "_", ascii_text).strip("_")
    aliases = {
        "parcelas": ("parcelas", "parcelamento", "parcela"),
        "forma_pagamento": ("forma_pagamento", "pagamento", "tipo_de_pagamento"),
        "tipo_de_venda": ("tipo_de_venda", "tipo_venda", "venda"),
    }
    for canonical, options in aliases.items():
        if slug in options:
            return canonical
    return slug


def _sort_direction_from_operation(operation: str | None) -> str | None:
    if operation == PublicOperationType.RANKING_ASC.value:
        return "asc"
    if operation == PublicOperationType.RANKING_DESC.value:
        return "desc"
    return None


def _contains_needle(text: str, needles: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(needle)}\b", text) for needle in needles)


def _merge_period_filters(
    filters: tuple[EntityFilter, ...],
    *,
    primary_period: str | None,
    periods: tuple[str, ...],
) -> tuple[EntityFilter, ...]:
    merged = list(filters)
    existing = {
        filt.value
        for filt in merged
        if filt.dimension == "periodo" and filt.value
    }
    for period in periods:
        if period == primary_period or period in existing:
            continue
        merged.append(EntityFilter(dimension="periodo", value=period, match="exact"))
        existing.add(period)
    return tuple(merged)


def _dimension_for_cortesia_group(
    dimension: str | None,
    filters: tuple[EntityFilter, ...],
) -> str | None:
    if dimension in {None, "tipo_venda", "tipo_de_venda"}:
        return dimension
    if any(_is_cortesia_group(filt.value) for filt in filters):
        return "tipo_venda"
    return dimension


def _entity_filters_for_dimension(
    filters: tuple[EntityFilter, ...],
    dimension: str | None,
) -> tuple[EntityFilter, ...]:
    if dimension not in {"tipo_venda", "tipo_de_venda"}:
        return filters
    normalized: list[EntityFilter] = []
    for filt in filters:
        if _is_cortesia_group(filt.value) and filt.dimension != "periodo":
            normalized.append(EntityFilter(dimension="tipo_venda", value=filt.value, match=filt.match))
            continue
        normalized.append(filt)
    return tuple(normalized)


def _is_cortesia_group(value: str | None) -> bool:
    return (value or "").strip().lower() in {"cortesia", "cortesias"}


def extract_payment_method_entity(message: str) -> str | None:
    """Detecta forma de pagamento mencionada na mensagem (valor canônico)."""
    text = _normalize_text(message or "")
    if not text:
        return None
    for pattern, canonical in _PAYMENT_METHOD_PATTERNS:
        if re.search(pattern, text):
            return canonical
    return None


def _apply_payment_method_filter(
    filters: tuple[EntityFilter, ...],
    message: str,
) -> tuple[EntityFilter, ...]:
    payment = extract_payment_method_entity(message)
    if not payment:
        return filters
    if any(filt.dimension == "forma_pagamento" for filt in filters):
        return filters
    return filters + (EntityFilter(dimension="forma_pagamento", value=payment, match="contains"),)


def _apply_parcel_filters(
    filters: tuple[EntityFilter, ...],
    parcel_entity: str,
) -> tuple[EntityFilter, ...]:
    cleaned: list[EntityFilter] = []
    for filt in filters:
        if filt.dimension == "periodo":
            cleaned.append(filt)
            continue
        if extract_parcel_count_entity(filt.value or ""):
            continue
        cleaned.append(filt)
    cleaned.append(EntityFilter(dimension="parcelas", value=normalize_parcel_entity(parcel_entity), match="contains"))
    return tuple(cleaned)
