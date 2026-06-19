"""Testes Fase 4A — intenção viva."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.intent_heuristics import (
    apply_heuristic_enrichment,
    extract_heuristic_signals,
)
from orion_mcp_v3.public_chat.domain.intent_parser import parse_public_intent_payload
from orion_mcp_v3.public_chat.domain.semantic_hash import build_semantic_hash
from orion_mcp_v3.public_chat.domain.topic_resolver import resolve_topic


def test_heuristics_pior_maps_ranking_asc() -> None:
    signals = extract_heuristic_signals("qual a forma de pagamento foi pior em março de 2026?")
    assert signals["operation"] == PublicOperationType.RANKING_ASC.value
    assert signals["dimension"] == "forma_pagamento"
    assert signals["period"] == "2026-03"


def test_intent_ranking_asc_pior() -> None:
    contract = parse_public_intent_payload(
        {
            "intent": "consulta_metrica",
            "period": "2026-03",
            "confidence": 0.8,
        },
        message="qual a forma de pagamento foi pior em março de 2026?",
    )
    assert contract.operation == PublicOperationType.RANKING_ASC.value
    assert contract.dimension == "forma_pagamento"
    assert contract.period == "2026-03"
    assert contract.metric == "faturamento"
    assert contract.sort_direction == "asc"


def test_topic_includes_dimension() -> None:
    contract = apply_heuristic_enrichment(
        IntentContract(intent="consulta_metrica", period="2026-03", confidence=0.8),
        "qual a forma de pagamento foi pior em março de 2026?",
    )
    assert resolve_topic(contract) == "forma_pagamento:2026-03"


def test_semantic_hash_distinguishes_questions() -> None:
    generic = parse_public_intent_payload(
        {"intent": "comparacao", "period": "2026-03", "confidence": 0.65},
        message="como foi março de 2026?",
    )
    specific = parse_public_intent_payload(
        {
            "intent": "consulta_metrica",
            "period": "2026-03",
            "operation": "ranking_asc",
            "dimension": "forma_pagamento",
            "confidence": 0.8,
        },
        message="qual a forma de pagamento foi pior em março de 2026?",
    )
    assert build_semantic_hash(generic) != build_semantic_hash(specific)


def test_contract_backward_compatible_defaults() -> None:
    contract = IntentContract.from_mapping({"intent": "consulta_metrica", "confidence": 0.9})
    assert contract.operation is None
    assert contract.dimension is None
    assert contract.sort_direction is None
