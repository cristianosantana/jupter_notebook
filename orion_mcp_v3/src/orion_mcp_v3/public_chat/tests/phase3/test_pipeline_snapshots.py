from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.pipeline_snapshots import (
    snapshot_intent,
    snapshot_knowledge,
    snapshot_knowledge_hit,
    snapshot_vector_matches,
)


def test_snapshot_knowledge_hit() -> None:
    hit = KnowledgeHit(
        origin_id=42,
        context_key="ctx:2026-01",
        category="Financeiro",
        validated_answer="Faturamento validado em R$ 100.",
        key_metrics={"faturamento": 100},
        score=0.12,
    )
    data = snapshot_knowledge_hit(hit)
    assert data["origin_id"] == 42
    assert data["source"] == "memory_curta"
    assert "Faturamento" in data["validated_answer_preview"]


def test_snapshot_knowledge_and_intent() -> None:
    knowledge = ConhecimentoRecuperado(
        hits=(
            KnowledgeHit(
                origin_id=1,
                context_key="k1",
                category="Cat",
                validated_answer="x",
                key_metrics={},
            ),
        )
    )
    snap = snapshot_knowledge(knowledge)
    assert snap["hit_count"] == 1
    assert snap["knowledge_ids"] == [1]

    contract = IntentContract(intent="comparacao", period="2026-01", confidence=0.8)
    intent = snapshot_intent(contract)
    assert intent["intent"] == "comparacao"
    assert intent["period"] == "2026-01"


def test_snapshot_vector_matches() -> None:
    matches = snapshot_vector_matches([(2, 0.15), (3, 0.22)])
    assert matches[0]["origin_id"] == 2
    assert matches[0]["score"] == 0.15
