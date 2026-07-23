"""Testes Fase 4A — intenção viva."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicOperationType
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


def test_heuristics_maior_queda_maps_period_decline() -> None:
    message = "Qual concessionária teve a maior queda de comissão entre janeiro a maio de 2026?"
    signals = extract_heuristic_signals(message)
    assert signals["operation"] == PublicOperationType.PERIOD_DECLINE.value
    assert signals["dimension"] == "concessionaria"

    # Coligação sobrescreve LLM que errou para ranking_desc
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="comissao",
            period="2026-01",
            operation="ranking_desc",
            dimension="concessionaria",
            sort_direction="desc",
            confidence=0.75,
        ),
        message,
    )
    assert contract.operation == PublicOperationType.PERIOD_DECLINE.value
    assert contract.sort_direction == "asc"


def test_heuristics_maior_crescimento_maps_period_growth() -> None:
    signals = extract_heuristic_signals(
        "qual parcela teve o maior crescimento percentual até junho?"
    )
    assert signals["operation"] == PublicOperationType.PERIOD_GROWTH.value


def test_heuristics_mais_vendido_manteve_lider_is_leader_change() -> None:
    message = "Qual foi o serviço mais vendido em maio, e se manteve líder em junho?"
    signals = extract_heuristic_signals(message)
    assert signals["operation"] == PublicOperationType.LEADER_CHANGE.value
    assert signals["dimension"] == "servico"

    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="comparacao",
            metric="producao",
            period="2026-05",
            operation="comparison",
            dimension=None,
            entity_filters=(),
            confidence=0.8,
        ),
        message,
    )
    assert contract.operation == PublicOperationType.LEADER_CHANGE.value
    assert contract.sort_direction == "desc"
    assert contract.dimension == "servico"


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


def test_intent_enrichment_extracts_comparison_period_from_message_typo() -> None:
    contract = parse_public_intent_payload(
        {
            "intent": "comparacao",
            "metric": "faturamento",
            "period": "2026-05",
            "operation": "comparison",
            "entity_filters": [],
            "confidence": 0.8,
        },
        message="qual o faturamento em maio de 2026 vs abriu de 2026?",
    )

    assert contract.period == "2026-05"
    assert [item.as_mapping() for item in contract.entity_filters] == [
        {"dimension": "periodo", "value": "2026-04", "match": "exact"},
    ]


def test_cortesias_enrichment_targets_tipo_venda_not_forma_pagamento() -> None:
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-06",
            dimension="forma_pagamento",
            entity_filters=(EntityFilter(dimension="forma_pagamento", value="cortesias", match="contains"),),
            confidence=0.92,
        ),
        "qual o faturamos com cortesias em junho de 2026?",
    )

    assert contract.dimension == "tipo_venda"
    assert contract.entity_filters[0].as_mapping() == {
        "dimension": "tipo_venda",
        "value": "cortesias",
        "match": "contains",
    }


def test_tipo_de_vendas_has_priority_over_concessionaria_token() -> None:
    signals = extract_heuristic_signals(
        "quanto faturamos no tipo de vendas Cortesia Concessionária em junho de 2026?"
    )

    assert signals["dimension"] == "tipo_venda"


def test_cartao_credito_5x_enrichment_targets_parcelas_dimension() -> None:
    message = "qual o total de vendas com pagamento em cartão de credito em 5x em abril de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-04",
            dimension="forma_pagamento",
            entity_filters=(
                EntityFilter(dimension="forma_pagamento", value="cartão de crédito 5x", match="contains"),
            ),
            confidence=0.95,
        ),
        message,
    )

    assert contract.dimension == "parcelas"
    parcel_filters = [item for item in contract.entity_filters if item.dimension == "parcelas"]
    assert len(parcel_filters) == 1
    assert parcel_filters[0].as_mapping() == {
        "dimension": "parcelas",
        "value": "5X",
        "match": "contains",
    }
    payment_filters = [item for item in contract.entity_filters if item.dimension == "forma_pagamento"]
    assert len(payment_filters) == 1
    assert payment_filters[0].value == "cartao de credito"


def test_cartao_credito_10x_injects_forma_pagamento_when_llm_omits() -> None:
    message = "qual o total de vendas com pagamento em cartão de credito em 10x em abril de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-04",
            dimension="parcelas",
            entity_filters=(EntityFilter(dimension="parcelas", value="10X", match="contains"),),
            confidence=0.9,
        ),
        message,
    )

    payment_filters = [item for item in contract.entity_filters if item.dimension == "forma_pagamento"]
    assert len(payment_filters) == 1
    assert payment_filters[0].value == "cartao de credito"


def test_cartao_credito_5x_splits_forma_pagamento_and_parcelas_filters() -> None:
    message = "qual o total de vendas com pagamento em cartão de credito em 5x em abril de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-04",
            dimension="forma_pagamento",
            entity_filters=(
                EntityFilter(dimension="forma_pagamento", value="cartão de crédito", match="contains"),
                EntityFilter(dimension="parcelas", value="5x", match="contains"),
            ),
            confidence=0.9,
        ),
        message,
    )

    assert contract.dimension == "parcelas"
    parcel_filters = [item for item in contract.entity_filters if item.dimension == "parcelas"]
    assert len(parcel_filters) == 1
    assert parcel_filters[0].value == "5X"


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
