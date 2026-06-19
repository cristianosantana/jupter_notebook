from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from orion_mcp_v3.public_chat.domain.knowledge import AnswerPayload, KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.remissive_retriever import RemissiveRetriever


@pytest.mark.asyncio
async def test_retriever_returns_knowledge() -> None:
    reader = AsyncMock()
    reader.search_origin_ids.return_value = [(42, 0.12)]
    reader.load_hits_by_origin_ids.return_value = [
        KnowledgeHit(
            origin_id=42,
            context_key="financeiro:faturamento:2026-05",
            category="Financeiro",
            validated_answer="Faturamento validado.",
            key_metrics={"faturamento": 100.0},
            score=0.12,
        )
    ]

    retriever = RemissiveRetriever(reader)
    knowledge = await retriever.retrieve("faturamento maio")

    assert knowledge.has_hits
    assert knowledge.hits[0].origin_id == 42
    assert knowledge.hits[0].category == "Financeiro"


@pytest.mark.asyncio
async def test_reload_from_payload() -> None:
    reader = AsyncMock()
    reader.load_hits_by_origin_ids.return_value = [
        KnowledgeHit(
            origin_id=42,
            context_key="ctx",
            category="Financeiro",
            validated_answer="Resposta.",
            key_metrics={},
        )
    ]
    reader.load_essence_by_themes.return_value = []

    retriever = RemissiveRetriever(reader)
    knowledge = await retriever.reload_from_payload(
        AnswerPayload(context_keys=("ctx",), knowledge_ids=(42,), essence_themes=())
    )

    reader.load_hits_by_origin_ids.assert_awaited_once_with([42])
    assert knowledge.hits[0].origin_id == 42


@pytest.mark.asyncio
async def test_synonymy_via_remissive_on_miss() -> None:
    reader = AsyncMock()
    reader.search_origin_ids.side_effect = [
        [(42, 0.2)],
        [(42, 0.18)],
    ]
    reader.load_hits_by_origin_ids.return_value = [
        KnowledgeHit(
            origin_id=42,
            context_key="ctx",
            category="Financeiro",
            validated_answer="Mesmo conhecimento.",
            key_metrics={},
        )
    ]

    retriever = RemissiveRetriever(reader)
    first = await retriever.retrieve("Qual o faturamento de maio?")
    second = await retriever.retrieve("Quanto faturou em maio?")

    assert first.hits[0].origin_id == second.hits[0].origin_id == 42
