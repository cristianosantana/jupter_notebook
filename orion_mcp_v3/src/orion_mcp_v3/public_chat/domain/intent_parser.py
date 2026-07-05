"""Parser e normalização do payload JSON de intenção pública."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Mapping

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicIntentType


_MONTH_NAMES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
_MONTH_ALIASES = {
    **_MONTH_NAMES,
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "abriu": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}


def parse_public_intent_payload(
    payload: Mapping[str, Any] | None,
    *,
    min_confidence: float = 0.5,
    message: str | None = None,
) -> IntentContract:
    """Valida JSON do LLM; fallback para contrato geral quando inválido ou fraco."""
    if payload is None:
        return IntentContract.geral()
    try:
        contract = IntentContract.from_mapping(payload)
    except (TypeError, ValueError):
        return IntentContract.geral()

    period = normalize_period(contract.period)
    contract = IntentContract(
        intent=contract.intent or PublicIntentType.GERAL.value,
        metric=_normalize_token(contract.metric),
        period=period,
        domain=_normalize_token(contract.domain),
        entity_filters=contract.entity_filters,
        confidence=contract.confidence,
        operation=_normalize_token(contract.operation),
        dimension=_normalize_token(contract.dimension),
        sort_direction=_normalize_token(contract.sort_direction),
    )
    if message:
        from orion_mcp_v3.public_chat.domain.intent_heuristics import apply_heuristic_enrichment

        contract = apply_heuristic_enrichment(contract, message)
    if contract.confidence < min_confidence:
        return IntentContract.geral(confidence=contract.confidence)
    if not any(
        (
            contract.metric,
            contract.period,
            contract.domain,
            contract.entity_filters,
            contract.operation,
            contract.dimension,
        )
    ):
        if contract.intent == PublicIntentType.GERAL.value:
            return IntentContract.geral(confidence=contract.confidence)
    return contract


def normalize_contract_for_hash(contract: IntentContract) -> dict[str, Any]:
    """Representação canônica usada por ``build_semantic_hash``."""
    filters = sorted(
        (
            {
                "dimension": item.dimension,
                "match": item.match,
                "value": item.value,
            }
            for item in contract.entity_filters
        ),
        key=lambda item: (item["dimension"], item["value"], item["match"]),
    )
    return {
        "entity_filters": filters,
        "intent": contract.intent or PublicIntentType.GERAL.value,
        "metric": contract.metric or "",
        "period": contract.period or "",
        "operation": contract.operation or "",
        "dimension": contract.dimension or "",
    }


def normalize_period(value: str | None) -> str | None:
    """Normaliza período para ``YYYY-MM`` quando possível."""
    if not value:
        return None
    text = value.strip().lower()
    if not text:
        return None

    iso_match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}"

    slash_match = re.fullmatch(r"(\d{4})/(\d{1,2})", text)
    if slash_match:
        return f"{slash_match.group(1)}-{int(slash_match.group(2)):02d}"

    for name, month in _MONTH_NAMES.items():
        if name in text:
            year_match = re.search(r"(20\d{2})", text)
            if year_match:
                return f"{year_match.group(1)}-{month:02d}"
            return f"0000-{month:02d}"

    month_match = re.search(r"\b(0?[1-9]|1[0-2])\b", text)
    year_match = re.search(r"(20\d{2})", text)
    if month_match and year_match:
        return f"{year_match.group(1)}-{int(month_match.group(1)):02d}"

    return text


def extract_mentioned_periods(message: str | None) -> tuple[str, ...]:
    """Extrai todos os períodos YYYY-MM mencionados em ordem textual."""
    text = _normalize_text(message or "")
    if not text:
        return ()

    matches: list[tuple[int, str]] = []
    for match in re.finditer(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", text):
        matches.append((match.start(), f"{match.group(1)}-{int(match.group(2)):02d}"))

    aliases = "|".join(re.escape(alias) for alias in sorted(_MONTH_ALIASES, key=len, reverse=True))
    month_year_re = re.compile(rf"\b({aliases})\b\s*(?:de\s*)?(20\d{{2}})\b")
    for match in month_year_re.finditer(text):
        month = _MONTH_ALIASES[match.group(1)]
        matches.append((match.start(), f"{match.group(2)}-{month:02d}"))

    years = tuple(dict.fromkeys(re.findall(r"\b(20\d{2})\b", text)))
    if len(years) == 1:
        month_re = re.compile(rf"\b({aliases})\b")
        for match in month_re.finditer(text):
            month = _MONTH_ALIASES[match.group(1)]
            matches.append((match.start(), f"{years[0]}-{month:02d}"))

    ordered: list[str] = []
    for _, period in sorted(matches, key=lambda item: item[0]):
        if period not in ordered:
            ordered.append(period)
    return tuple(ordered)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Extrai objeto JSON de resposta do LLM."""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _normalize_token(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().lower()
    return text or None


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()
