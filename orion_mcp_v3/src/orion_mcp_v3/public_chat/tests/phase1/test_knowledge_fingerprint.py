from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge_fingerprint import build_knowledge_fingerprint


def test_knowledge_fingerprint_stable() -> None:
    left = build_knowledge_fingerprint(
        validated_answers=["Resposta validada."],
        key_metrics=[{"faturamento": 100.0}],
        essence_themes=["fechamento_mensal"],
    )
    right = build_knowledge_fingerprint(
        validated_answers=["Resposta validada."],
        key_metrics=[{"faturamento": 100.0}],
        essence_themes=["fechamento_mensal"],
    )
    assert left == right
    assert len(left) == 64
