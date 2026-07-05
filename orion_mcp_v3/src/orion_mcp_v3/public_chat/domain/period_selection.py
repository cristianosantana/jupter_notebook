"""Seleção de períodos analíticos a partir do contrato de intenção."""

from __future__ import annotations

import re
import unicodedata

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract

_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_PARCEL_COUNT_RE = re.compile(r"\b(\d+)\s*x\b", re.IGNORECASE)


def periods_from_contract(contract: IntentContract) -> tuple[str, ...]:
    periods: list[str] = []
    if _is_year_month(contract.period):
        periods.append(str(contract.period))
    for filt in contract.entity_filters:
        if _is_period_filter(filt) and _is_year_month(filt.value):
            periods.append(str(filt.value))
    return tuple(dict.fromkeys(periods))


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


def entity_for_dimension(contract: IntentContract, dimension: str, *, message: str = "") -> str | None:
    target = _normalize_dimension(dimension)
    for filt in non_period_entity_filters(contract):
        if not filt.value:
            continue
        if _normalize_dimension(filt.dimension or "") == target:
            if target == "parcelas":
                return normalize_parcel_entity(filt.value)
            return filt.value
    if target == "parcelas":
        return parcel_entity_from_contract(contract, message=message)
    for filt in non_period_entity_filters(contract):
        if filt.value and not extract_parcel_count_entity(filt.value):
            return filt.value
    return None


def _is_period_filter(filt: EntityFilter) -> bool:
    return _normalize_text(filt.dimension or "") == "periodo"


def _is_year_month(value: str | None) -> bool:
    return isinstance(value, str) and bool(_YEAR_MONTH_RE.match(value.strip()))


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
