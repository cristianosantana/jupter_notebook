from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from orion_mcp_v3.protocols.llm import LLMResponse, LLMStreamChunk
from orion_mcp_v3.public_chat.application.consulta_turn_runner import ConsultaTurnRunner
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.intent_interpreter import PublicIntentInterpreter
from orion_mcp_v3.public_chat.infrastructure.narrator import PublicNarrator
from orion_mcp_v3.public_chat.infrastructure.remissive_retriever import RemissiveRetriever
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore
from orion_mcp_v3.public_chat.tests.phase4.helpers import PassthroughContextSelector


def _pool_with_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.mark.asyncio
async def test_audit_chain_miss_path() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()

    conn = AsyncMock()
    insert_row = {
        "id": question_id,
        "thread_id": thread_id,
        "parent_question_id": None,
        "topic": "faturamento:2026-05",
        "intent_contract": {
            "intent": "consulta_metrica",
            "metric": "faturamento",
            "period": "2026-05",
            "confidence": 0.9,
        },
        "semantic_hash": "hash1",
        "query_original": "faturamento maio?",
        "created_at": "2026-06-16T00:00:00+00:00",
    }
    conn.fetchrow.side_effect = [insert_row, {"thread_id": thread_id}, insert_row, None]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    store = ResponseStore(_pool_with_conn(conn))

    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='{"intent":"consulta_metrica","metric":"faturamento","period":"2026-05","confidence":0.9}'
    )

    async def _stream(*_args, **_kwargs):
        yield LLMStreamChunk(delta="Resposta narrada.")
        yield LLMStreamChunk(delta="", finish_reason="stop")

    llm.stream = _stream

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.retrieve.return_value = ConhecimentoRecuperado(
        hits=(
            KnowledgeHit(
                origin_id=42,
                context_key="ctx",
                category="Financeiro",
                validated_answer="validado",
                key_metrics={"faturamento": 1},
            ),
        )
    )

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(cache_ttl_days=90),
        store=store,
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )

    result, presentation = await runner.run_turn_with_metadata("faturamento maio?")

    assert result.question_id == question_id
    assert result.response_id == response_id
    assert result.topic == "faturamento:2026-05"
    assert "Resposta narrada." in presentation
    retriever.retrieve.assert_awaited_once()
    assert conn.fetchval.awaited
    assert conn.execute.awaited


@pytest.mark.asyncio
async def test_runner_miss_end_to_end() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = question_id

    conn = AsyncMock()
    insert_row = {
        "id": question_id,
        "thread_id": thread_id,
        "parent_question_id": None,
        "topic": "geral",
        "intent_contract": {"intent": "geral", "confidence": 0.0},
        "semantic_hash": "hash",
        "query_original": "oi",
        "created_at": "2026-06-16T00:00:00+00:00",
    }
    conn.fetchrow.side_effect = [insert_row, {"thread_id": thread_id}, insert_row, None]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    store = ResponseStore(_pool_with_conn(conn))
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(text='{"intent":"geral","confidence":0.1}')

    async def _stream(*_args, **_kwargs):
        yield LLMStreamChunk(delta="Não encontrei informações validadas sobre isso.")

    llm.stream = _stream

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.retrieve.return_value = ConhecimentoRecuperado()

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(),
        store=store,
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )

    deltas: list[str] = []
    async for delta in runner.run_turn_miss_only("oi"):
        deltas.append(delta)

    assert "Não encontrei" in "".join(deltas)
