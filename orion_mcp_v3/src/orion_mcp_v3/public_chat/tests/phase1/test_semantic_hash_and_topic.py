from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicIntentType
from orion_mcp_v3.public_chat.domain.intent_parser import (
    normalize_contract_for_hash,
    normalize_period,
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


def test_normalize_period_rejects_long_free_text() -> None:
    garbage = "qual foi o produto de ppf/filme mais vendido em cada mes do primeiro semestre de 2026?"
    assert normalize_period(garbage) == "2026-H1"


def test_parse_payload_with_long_period_uses_semestre_token() -> None:
    message = (
        "Qual foi o produto de PPF/filme mais vendido em cada mês do primeiro semestre de 2026, "
        "e ele se manteve o líder em todos os meses?"
    )
    contract = parse_public_intent_payload(
        {
            "intent": "comparacao",
            "metric": "quantidade_vendida",
            "period": message,
            "domain": "vendas",
            "confidence": 0.85,
            "operation": "ranking_desc",
            "dimension": "produto",
            "entity_filters": [{"dimension": "produto", "value": "PPF/filme", "match": "contains"}],
        },
        min_confidence=0.5,
        message=message,
    )
    assert contract.period == "2026-H1"
    topic = resolve_topic(contract)
    assert len(topic) <= 128
    assert topic == "produto:2026-H1"


def test_topic_cap_never_exceeds_max_length() -> None:
    contract = IntentContract(
        intent=PublicIntentType.COMPARACAO.value,
        metric="x" * 80,
        period="y" * 80,
        dimension="z" * 80,
        confidence=0.9,
    )
    topic = resolve_topic(contract)
    assert len(topic) <= 128


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


def test_semantic_hash_equivalent_entity_filter_formatting() -> None:
    """cartão de crédito vs cartao_de_credito devem convergir na chave de cache."""
    base = {
        "intent": "consulta_metrica",
        "metric": "faturamento",
        "period": "2026-04",
        "domain": "vendas",
        "operation": "summary",
        "dimension": "parcelas",
        "confidence": 0.9,
    }
    with_accent = {
        **base,
        "entity_filters": [
            {"dimension": "forma_pagamento", "value": "cartão de crédito", "match": "contains"},
            {"dimension": "parcelas", "value": "10X", "match": "contains"},
        ],
    }
    with_underscore = {
        **base,
        "entity_filters": [
            {"dimension": "forma_pagamento", "value": "cartao_de_credito", "match": "contains"},
            {"dimension": "parcelas", "value": "10X", "match": "contains"},
        ],
    }
    hash_accent = build_semantic_hash(parse_public_intent_payload(with_accent, min_confidence=0.5))
    hash_underscore = build_semantic_hash(
        parse_public_intent_payload(with_underscore, min_confidence=0.5)
    )
    assert hash_accent == hash_underscore


def test_semantic_hash_stable_when_llm_omits_forma_pagamento_filter() -> None:
    """Heurística deve injectar forma_pagamento e convergir hash com contrato completo."""
    from orion_mcp_v3.public_chat.domain.intent_heuristics import apply_heuristic_enrichment

    message = "qual o total de vendas com pagamento em cartão de credito em 10x em abril de 2026?"
    full = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-04",
            domain="vendas",
            operation="summary",
            dimension="parcelas",
            entity_filters=(
                EntityFilter(dimension="forma_pagamento", value="cartão de crédito", match="contains"),
                EntityFilter(dimension="parcelas", value="10X", match="contains"),
            ),
            confidence=0.9,
        ),
        message,
    )
    partial = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-04",
            domain="vendas",
            operation="summary",
            dimension="parcelas",
            entity_filters=(EntityFilter(dimension="parcelas", value="10X", match="contains"),),
            confidence=0.9,
        ),
        message,
    )
    assert build_semantic_hash(full) == build_semantic_hash(partial)
