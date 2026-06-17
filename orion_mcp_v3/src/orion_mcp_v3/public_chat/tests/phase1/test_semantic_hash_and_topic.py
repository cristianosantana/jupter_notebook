from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicIntentType
from orion_mcp_v3.public_chat.domain.intent_parser import (
    normalize_contract_for_hash,
    parse_public_intent_payload,
)
from orion_mcp_v3.public_chat.domain.semantic_hash import build_semantic_hash
from orion_mcp_v3.public_chat.domain.topic_resolver import resolve_topic


def _faturamento_maio_contract() -> IntentContract:
    return IntentContract(
        intent=PublicIntentType.CONSULTA_METRICA.value,
        metric="faturamento",
        period="2026-05",
        domain="financeiro",
        confidence=0.92,
    )


def test_semantic_hash_stable() -> None:
    left = build_semantic_hash(_faturamento_maio_contract())
    right = build_semantic_hash(_faturamento_maio_contract())
    assert left == right
    assert len(left) == 64


def test_semantic_hash_equivalent_phrasings() -> None:
    payloads = [
        {
            "intent": "consulta_metrica",
            "metric": "faturamento",
            "period": "maio de 2026",
            "domain": "financeiro",
            "confidence": 0.9,
        },
        {
            "intent": "consulta_metrica",
            "metric": "Faturamento",
            "period": "2026-05",
            "domain": "Financeiro",
            "confidence": 0.88,
        },
        {
            "intent": "consulta_metrica",
            "metric": "faturamento",
            "period": "2026/5",
            "domain": "financeiro",
            "confidence": 0.95,
        },
    ]
    hashes = [
        build_semantic_hash(parse_public_intent_payload(payload, min_confidence=0.5))
        for payload in payloads
    ]
    assert hashes[0] == hashes[1] == hashes[2]


def test_topic_from_contract_only() -> None:
    contract = _faturamento_maio_contract()
    assert resolve_topic(contract) == "faturamento:2026-05"
    assert resolve_topic(IntentContract.geral()) == "geral"


def test_normalize_contract_sorts_entity_filters() -> None:
    contract = IntentContract(
        intent=PublicIntentType.CONSULTA_METRICA.value,
        metric="faturamento",
        period="2026-05",
        entity_filters=(
            EntityFilter(dimension="vendedor", value="joao", match="contains"),
            EntityFilter(dimension="concessionaria", value="alpha", match="exact"),
        ),
        confidence=0.8,
    )
    canonical = normalize_contract_for_hash(contract)
    assert canonical["entity_filters"][0]["dimension"] == "concessionaria"
    assert canonical["entity_filters"][1]["dimension"] == "vendedor"
