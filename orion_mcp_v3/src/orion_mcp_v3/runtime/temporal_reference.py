"""Detecção leve de referências temporais anafóricas."""

from __future__ import annotations

import re
import unicodedata

_TEMPORAL_TERMS = {
    "periodo",
    "mes",
    "competencia",
    "intervalo",
    "data",
    "janela",
    "recorte",
}

_ANAPHORIC_TERMS = {
    "mesmo",
    "mesma",
    "igual",
    "esse",
    "essa",
    "este",
    "esta",
    "nesse",
    "nessa",
    "neste",
    "nesta",
    "desse",
    "dessa",
    "deste",
    "desta",
    "do",
    "no",
    "da",
    "na",
    "aquele",
    "aquela",
    "anterior",
    "ultimo",
    "ultima",
    "atual",
    "citado",
    "citada",
    "informado",
    "informada",
    "analisado",
    "analisada",
    "acima",
}


def normalize_temporal_reference_text(text: str) -> str:
    """Normaliza acentos/caixa para comparar termos em português."""
    raw = "".join(
        c for c in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", raw).strip()


def temporal_anaphora_match(message: str) -> str | None:
    """Retorna o fragmento temporal anafórico detectado, se houver.

    A regra exige um termo temporal ("periodo", "competencia", "janela" etc.)
    próximo de um marcador anafórico/deítico ("mesmo", "nessa", "citado" etc.).
    """
    text = normalize_temporal_reference_text(message)
    tokens = re.findall(r"\b\w+\b", text)
    if not tokens:
        return None

    for index, token in enumerate(tokens):
        if token not in _TEMPORAL_TERMS:
            continue

        start = max(0, index - 3)
        end = min(len(tokens), index + 4)
        before = tokens[start:index]
        after = tokens[index + 1 : end]

        for pos in range(index - 1, start - 1, -1):
            if tokens[pos] in _ANAPHORIC_TERMS:
                return " ".join(tokens[pos : index + 1])

        for offset, candidate in enumerate(after, start=index + 1):
            if candidate in _ANAPHORIC_TERMS:
                return " ".join(tokens[index : offset + 1])

        if any(item in _ANAPHORIC_TERMS for item in before):
            return token

    return None


def has_temporal_anaphora(message: str) -> bool:
    return temporal_anaphora_match(message) is not None
