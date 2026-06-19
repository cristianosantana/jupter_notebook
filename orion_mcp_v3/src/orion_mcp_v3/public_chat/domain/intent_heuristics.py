"""Sinais heurísticos locais para enriquecer o contrato de intenção."""

from __future__ import annotations

import re

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.intent_parser import normalize_period

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
    ("concessionaria", ("concessionária", "concessionaria", "concessionárias", "concessionarias")),
    ("servico", ("serviço", "servico", "serviços", "servicos", "produção por serviço", "producao por servico")),
    ("produto", ("produto", "produtos", "produção por produto", "producao por produto")),
    ("tipo_venda", ("tipo de venda", "tipos de venda")),
    ("parcelamento", ("parcelamento", "parcela", "parcelas")),
    ("comissao", ("comissão", "comissao", "comissões", "comissoes")),
)


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
    period = contract.period or signals["period"]
    sort_direction = contract.sort_direction or _sort_direction_from_operation(operation)
    metric = contract.metric
    if dimension == "forma_pagamento" and not metric:
        metric = "faturamento"
    return IntentContract(
        intent=contract.intent,
        metric=metric,
        period=period,
        domain=contract.domain,
        entity_filters=contract.entity_filters,
        confidence=contract.confidence,
        operation=operation,
        dimension=dimension,
        sort_direction=sort_direction,
    )


def _sort_direction_from_operation(operation: str | None) -> str | None:
    if operation == PublicOperationType.RANKING_ASC.value:
        return "asc"
    if operation == PublicOperationType.RANKING_DESC.value:
        return "desc"
    return None


def _contains_needle(text: str, needles: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(needle)}\b", text) for needle in needles)
