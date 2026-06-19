"""Resolução determinística de tópico — exclusivamente a partir do contrato."""

from __future__ import annotations

import re
import unicodedata

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicIntentType


def resolve_topic(contract: IntentContract) -> str:
    """Deriva slug legível só de metric, period, domain, dimension e intent."""
    metric = _slug(contract.metric) if contract.metric else None
    period = (contract.period or "").strip() or None
    domain = _slug(contract.domain) if contract.domain else None
    dimension = _slug(contract.dimension) if contract.dimension else None

    if dimension and period:
        return f"{dimension}:{period}"
    if dimension and metric:
        return f"{dimension}:{metric}"
    if dimension:
        return dimension
    if metric and period:
        return f"{metric}:{period}"
    if metric and domain:
        return f"{metric}:{domain}"
    if metric:
        return metric
    if period:
        return f"periodo:{period}"
    if domain:
        return domain
    intent = _slug(contract.intent) if contract.intent else None
    if intent and intent != PublicIntentType.GERAL.value:
        return intent
    return "geral"


def _slug(value: str) -> str:
    raw = "".join(
        char
        for char in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(char)
    )
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    return raw.strip("_") or "geral"
