"""Resolução determinística de tópico — exclusivamente a partir do contrato."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicIntentType

MAX_TOPIC_LEN = 128
_MAX_TOPIC_TOKEN_LEN = 32


def resolve_topic(contract: IntentContract) -> str:
    """Deriva slug legível só de metric, period, domain, dimension e intent."""
    metric = _slug(contract.metric) if contract.metric else None
    period = _topic_token(contract.period)
    domain = _slug(contract.domain) if contract.domain else None
    dimension = _slug(contract.dimension) if contract.dimension else None

    if dimension and period:
        return _cap_topic(f"{dimension}:{period}")
    if dimension and metric:
        return _cap_topic(f"{dimension}:{metric}")
    if dimension:
        return _cap_topic(dimension)
    if metric and period:
        return _cap_topic(f"{metric}:{period}")
    if metric and domain:
        return _cap_topic(f"{metric}:{domain}")
    if metric:
        return _cap_topic(metric)
    if period:
        return _cap_topic(f"periodo:{period}")
    if domain:
        return _cap_topic(domain)
    intent = _slug(contract.intent) if contract.intent else None
    if intent and intent != PublicIntentType.GERAL.value:
        return _cap_topic(intent)
    return "geral"


def _topic_token(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip()
    if len(token) <= _MAX_TOPIC_TOKEN_LEN:
        return token
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _cap_topic(topic: str) -> str:
    if len(topic) <= MAX_TOPIC_LEN:
        return topic
    digest = hashlib.sha256(topic.encode()).hexdigest()[:10]
    return f"{topic[: MAX_TOPIC_LEN - 11]}:{digest}"


def _slug(value: str) -> str:
    raw = "".join(
        char
        for char in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(char)
    )
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    return raw.strip("_") or "geral"
