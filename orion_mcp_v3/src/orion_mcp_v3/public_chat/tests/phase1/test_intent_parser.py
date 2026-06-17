from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicIntentType
from orion_mcp_v3.public_chat.domain.intent_parser import parse_public_intent_payload


def test_intent_parser_valid_json() -> None:
    contract = parse_public_intent_payload(
        {
            "intent": "consulta_metrica",
            "metric": "faturamento",
            "period": "maio de 2026",
            "domain": "financeiro",
            "confidence": 0.91,
        }
    )
    assert contract.metric == "faturamento"
    assert contract.period == "2026-05"
    assert contract.domain == "financeiro"
    assert contract.confidence == 0.91


def test_intent_parser_invalid_json() -> None:
    contract = parse_public_intent_payload(None)
    assert contract.intent == PublicIntentType.GERAL.value
    assert contract.metric is None

    low_confidence = parse_public_intent_payload(
        {
            "intent": "consulta_metrica",
            "metric": "faturamento",
            "period": "2026-05",
            "confidence": 0.1,
        }
    )
    assert low_confidence.intent == PublicIntentType.GERAL.value
