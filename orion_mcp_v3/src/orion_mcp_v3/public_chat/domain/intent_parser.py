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


_MAX_PERIOD_TOKEN_LEN = 64


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
    if message and not period:
        period = normalize_period(message)
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
                "dimension": _normalize_token(item.dimension) or "",
                "match": _normalize_token(item.match) or item.match,
                "value": normalize_entity_filter_value(item.value),
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
    """Normaliza período para token curto (``YYYY-MM``, ``YYYY-H1``, intervalo compacto)."""
    if not value:
        return None
    text = value.strip().lower()
    if not text:
        return None

    iso_match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}"

    half_match = re.fullmatch(r"(\d{4})-h([12])", text)
    if half_match:
        return f"{half_match.group(1)}-H{half_match.group(2)}"

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

    extracted = extract_mentioned_periods(text)
    if extracted:
        return _compact_period_span(extracted)

    semestre = _normalize_semestre(text)
    if semestre:
        return semestre

    if len(text) <= _MAX_PERIOD_TOKEN_LEN:
        return text
    return None


def _normalize_semestre(text: str) -> str | None:
    year_match = re.search(r"(20\d{2})", text)
    if not year_match:
        return None
    year = year_match.group(1)
    if re.search(r"primeiro\s+semestre|1\s*[ºo°]\s*semestre|\bh1\b", text):
        return f"{year}-H1"
    if re.search(r"segundo\s+semestre|2\s*[ºo°]\s*semestre|\bh2\b", text):
        return f"{year}-H2"
    return None


def _compact_period_span(periods: tuple[str, ...]) -> str:
    ordered = tuple(dict.fromkeys(periods))
    if len(ordered) == 1:
        return ordered[0]
    first, last = ordered[0], ordered[-1]
    if first[:4] == last[:4]:
        compact = f"{first}..{last}"
        if len(compact) <= _MAX_PERIOD_TOKEN_LEN:
            return compact
    joined = ",".join(ordered)
    if len(joined) <= _MAX_PERIOD_TOKEN_LEN:
        return joined
    return f"{ordered[0]}..{ordered[-1]}"


def extract_mentioned_periods(message: str | None) -> tuple[str, ...]:
    """Extrai períodos YYYY-MM; com range/semestre, lista inclusiva."""
    text = _normalize_text(message or "")
    if not text:
        return ()

    semestre = _semestre_months(text)
    if semestre:
        return semestre

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

    if len(ordered) >= 2 and _message_has_period_range(text):
        from orion_mcp_v3.public_chat.domain.period_selection import expand_periods_inclusive

        return expand_periods_inclusive(tuple(ordered))
    return tuple(ordered)


def _message_has_period_range(text: str) -> bool:
    return bool(
        re.search(
            r"\b(entre|ate|até|de\s+\w+\s+a\s+|a\s+\w+\s+de\s+20\d{2}|1\s*[oº°]?\s*semestre|"
            r"2\s*[oº°]?\s*semestre|primeiro\s+semestre|segundo\s+semestre)\b",
            text,
        )
    )


def _semestre_months(text: str) -> tuple[str, ...]:
    year_match = re.search(r"(20\d{2})", text)
    if not year_match:
        return ()
    year = year_match.group(1)
    from orion_mcp_v3.public_chat.domain.period_selection import expand_period_range

    if re.search(r"primeiro\s+semestre|1\s*[ºo°]?\s*semestre|\bh1\b", text):
        return expand_period_range(f"{year}-01", f"{year}-06")
    if re.search(r"segundo\s+semestre|2\s*[ºo°]?\s*semestre|\bh2\b", text):
        return expand_period_range(f"{year}-07", f"{year}-12")
    return ()


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


def normalize_entity_filter_value(value: str) -> str:
    """Forma canônica para chave de cache — ignora acento, espaço vs underscore."""
    collapsed = value.strip().lower().replace("_", " ")
    return _normalize_text(collapsed)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()
