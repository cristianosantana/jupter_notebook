from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicIntentType
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.domain.knowledge_fingerprint import (
    build_knowledge_fingerprint_from_knowledge,
)
from orion_mcp_v3.public_chat.domain.topic_resolver import resolve_topic


def test_knowledge_fingerprint_changes() -> None:
    left = build_knowledge_fingerprint_from_knowledge(
        ConhecimentoRecuperado(
            hits=(
                KnowledgeHit(
                    origin_id=1,
                    context_key="a",
                    category="Financeiro",
                    validated_answer="A",
                    key_metrics={"v": 1},
                ),
            )
        )
    )
    right = build_knowledge_fingerprint_from_knowledge(
        ConhecimentoRecuperado(
            hits=(
                KnowledgeHit(
                    origin_id=1,
                    context_key="a",
                    category="faturamento",
                    validated_answer="B",
                    key_metrics={"v": 2},
                ),
            )
        )
    )
    assert left != right


def test_category_divergence_contract_wins() -> None:
    contract = IntentContract(
        intent=PublicIntentType.CONSULTA_METRICA.value,
        metric="faturamento",
        period="2026-05",
        domain="financeiro",
        confidence=0.9,
    )
    topic = resolve_topic(contract)
    hit = KnowledgeHit(
        origin_id=1,
        context_key="ctx",
        category="faturamento",
        validated_answer="x",
        key_metrics={},
    )
    assert resolve_topic(contract) == topic
    assert hit.category != contract.domain
