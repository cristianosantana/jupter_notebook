"""Seleção de períodos analíticos a partir do contrato de intenção."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract

_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_YEAR_HALF_RE = re.compile(r"^(\d{4})-H([12])$", re.IGNORECASE)
_SPAN_RE = re.compile(r"^(\d{4}-\d{2})\.\.(\d{4}-\d{2})$")
_PARCEL_COUNT_RE = re.compile(r"\b(\d+)\s*x\b", re.IGNORECASE)
_PREDICATE_FILTER_RE = re.compile(r"^\s*(>=|<=|!=|>|<)\s*[-+]?\d+(?:[.,]\d+)?\s*$")


def is_predicate_filter_value(value: str) -> bool:
    return bool(_PREDICATE_FILTER_RE.match(value or ""))


def expand_period_range(start: str, end: str) -> tuple[str, ...]:
    """Expande intervalo inclusivo ``YYYY-MM`` → ``(start, …, end)``."""
    if not _is_year_month(start) or not _is_year_month(end):
        return ()
    start_y, start_m = int(start[:4]), int(start[5:7])
    end_y, end_m = int(end[:4]), int(end[5:7])
    cursor = date(start_y, start_m, 1)
    stop = date(end_y, end_m, 1)
    if cursor > stop:
        cursor, stop = stop, cursor
    periods: list[str] = []
    while cursor <= stop:
        periods.append(f"{cursor.year:04d}-{cursor.month:02d}")
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return tuple(periods)


def expand_periods_inclusive(periods: tuple[str, ...]) -> tuple[str, ...]:
    """Se houver ≥2 YYYY-MM, preenche meses entre o menor e o maior."""
    year_months = sorted({p for p in periods if _is_year_month(p)})
    if len(year_months) < 2:
        return tuple(dict.fromkeys(p for p in periods if _is_year_month(p) or _is_year_half(p)))
    return expand_period_range(year_months[0], year_months[-1])


def periods_from_token(token: str | None) -> tuple[str, ...]:
    """Interpreta ``YYYY-MM``, ``YYYY-H1/H2``, ``A..B`` ou lista CSV."""
    if not token:
        return ()
    text = token.strip()
    if _is_year_month(text):
        return (text,)
    half = _YEAR_HALF_RE.match(text)
    if half:
        year = int(half.group(1))
        if half.group(2) == "1":
            return expand_period_range(f"{year:04d}-01", f"{year:04d}-06")
        return expand_period_range(f"{year:04d}-07", f"{year:04d}-12")
    span = _SPAN_RE.match(text)
    if span:
        return expand_period_range(span.group(1), span.group(2))
    if "," in text:
        parts = tuple(p.strip() for p in text.split(",") if p.strip())
        expanded: list[str] = []
        for part in parts:
            expanded.extend(periods_from_token(part))
        return expand_periods_inclusive(tuple(expanded)) if len(expanded) >= 2 else tuple(dict.fromkeys(expanded))
    return ()


def periods_from_contract(contract: IntentContract) -> tuple[str, ...]:
    periods: list[str] = []
    periods.extend(periods_from_token(contract.period))
    for filt in contract.entity_filters:
        if _is_period_filter(filt):
            periods.extend(periods_from_token(filt.value))
    discrete = tuple(dict.fromkeys(p for p in periods if _is_year_month(p)))
    if len(discrete) >= 2:
        return expand_periods_inclusive(discrete)
    return discrete


def non_period_entity_filters(contract: IntentContract) -> tuple[EntityFilter, ...]:
    return tuple(filt for filt in contract.entity_filters if not _is_period_filter(filt))


def extract_parcel_count_entity(message: str) -> str | None:
    match = _PARCEL_COUNT_RE.search(message or "")
    if not match:
        return None
    return f"{match.group(1)}X"


def normalize_parcel_entity(value: str) -> str:
    match = _PARCEL_COUNT_RE.search(value or "")
    if match:
        return f"{match.group(1)}X"
    return value.strip()


def message_has_parcel_count(message: str) -> bool:
    return extract_parcel_count_entity(message) is not None


def contract_has_parcel_filter(contract: IntentContract) -> bool:
    if _normalize_dimension(contract.dimension or "") == "parcelas":
        return True
    for filt in non_period_entity_filters(contract):
        if _normalize_dimension(filt.dimension or "") == "parcelas":
            return True
        if extract_parcel_count_entity(filt.value or ""):
            return True
    return False


def parcel_entity_from_contract(contract: IntentContract, *, message: str = "") -> str | None:
    for filt in non_period_entity_filters(contract):
        if _normalize_dimension(filt.dimension or "") == "parcelas" and filt.value:
            return normalize_parcel_entity(filt.value)
    for filt in non_period_entity_filters(contract):
        parcel = extract_parcel_count_entity(filt.value or "")
        if parcel:
            return parcel
    return extract_parcel_count_entity(message)


def group_entity_filters_by_dimension(contract: IntentContract) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for filt in non_period_entity_filters(contract):
        if not filt.value or is_predicate_filter_value(filt.value):
            continue
        dimension = _normalize_dimension(filt.dimension or "")
        if not dimension:
            continue
        value = (
            normalize_parcel_entity(filt.value)
            if dimension == "parcelas"
            else filt.value
        )
        groups.setdefault(dimension, []).append(value)
    return {dimension: tuple(dict.fromkeys(values)) for dimension, values in groups.items()}


def comparison_operand_dimensions(contract: IntentContract) -> tuple[str, ...]:
    groups = group_entity_filters_by_dimension(contract)
    return tuple(dimension for dimension, values in groups.items() if len(values) >= 2)


def scope_entity_filters(
    contract: IntentContract,
    operands: tuple[str, ...],
    *,
    exclude_dimensions: tuple[str, ...] = (),
) -> tuple[EntityFilter, ...]:
    operand_dims = {_normalize_dimension(dimension) for dimension in operands}
    excluded_dims = {_normalize_dimension(dimension) for dimension in exclude_dimensions}
    scope: list[EntityFilter] = []
    for filt in non_period_entity_filters(contract):
        dimension = _normalize_dimension(filt.dimension or "")
        if (
            dimension in operand_dims
            or dimension in excluded_dims
            or not filt.value
            or is_predicate_filter_value(filt.value)
        ):
            continue
        scope.append(filt)
    return tuple(scope)


def scope_entity_tuples(
    contract: IntentContract,
    operands: tuple[str, ...],
    *,
    exclude_dimensions: tuple[str, ...] = (),
) -> tuple[tuple[str, str, str], ...]:
    """Retorna ``(dimension, value, match)`` — concessionária etc. forçam ``exact``."""
    out: list[tuple[str, str, str]] = []
    for filt in scope_entity_filters(
        contract,
        operands,
        exclude_dimensions=exclude_dimensions,
    ):
        if not filt.value:
            continue
        dim = _normalize_dimension(filt.dimension or "")
        mode = _resolve_scope_match(dim, filt.match)
        out.append((dim, filt.value, mode))
    return tuple(out)


def _resolve_scope_match(dimension: str, raw_match: str | None) -> str:
    mode = (raw_match or "").strip().lower()
    if dimension in {"concessionaria", "estabelecimento", "empresa"}:
        # Default dataclass ``contains`` não deve afrouxar nomes próprios (Senna).
        if mode in ("", "contains", "exact"):
            return "exact"
        return mode
    return mode or "contains"


def _default_scope_match(dimension: str) -> str:
    if dimension in {"concessionaria", "estabelecimento", "empresa"}:
        return "exact"
    return "contains"


def entities_for_dimension(
    contract: IntentContract,
    dimension: str,
    *,
    message: str = "",
) -> tuple[str, ...]:
    target = _normalize_dimension(dimension)
    grouped = group_entity_filters_by_dimension(contract)
    if target in grouped and grouped[target]:
        return grouped[target]
    # Ranking no eixo inteiro: não inventar entidade a partir do texto da mensagem
    # (ex.: "1x a 10x" → primeiro match "1X").
    operation = (contract.operation or "").strip().lower()
    if operation in {
        "ranking_asc",
        "ranking_desc",
        "leader_change",
        "period_growth",
        "period_decline",
        "time_series",
        "cumulative",
        "share",
        "min",
        "max",
    }:
        return ()
    entity = _single_entity_for_dimension(contract, dimension, message=message)
    return (entity,) if entity else ()


def entity_for_dimension(contract: IntentContract, dimension: str, *, message: str = "") -> str | None:
    entities = entities_for_dimension(contract, dimension, message=message)
    return entities[0] if entities else None


def _single_entity_for_dimension(
    contract: IntentContract,
    dimension: str,
    *,
    message: str = "",
) -> str | None:
    target = _normalize_dimension(dimension)
    for filt in non_period_entity_filters(contract):
        if not filt.value or is_predicate_filter_value(filt.value):
            continue
        if _normalize_dimension(filt.dimension or "") == target:
            if target == "parcelas":
                return normalize_parcel_entity(filt.value)
            return filt.value
    if target == "parcelas":
        return parcel_entity_from_contract(contract, message=message)
    return None


def _is_period_filter(filt: EntityFilter) -> bool:
    return _normalize_text(filt.dimension or "") == "periodo"


def _is_year_month(value: str | None) -> bool:
    return isinstance(value, str) and bool(_YEAR_MONTH_RE.match(value.strip()))


def _is_year_half(value: str | None) -> bool:
    return isinstance(value, str) and bool(_YEAR_HALF_RE.match(value.strip()))

def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


def _normalize_dimension(value: str) -> str:
    normalized = _normalize_text(value)
    aliases = {
        "parcelas": ("parcelas", "parcelamento", "parcela"),
        "forma_pagamento": ("forma_pagamento", "pagamento", "tipo_de_pagamento"),
    }
    for dimension, options in aliases.items():
        if normalized in options:
            return dimension
    return normalized.replace(" ", "_")
