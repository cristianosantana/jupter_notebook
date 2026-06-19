from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from orion_mcp_v3.protocols.llm import LLMResponse, LLMStreamChunk
from orion_mcp_v3.public_chat.application.consulta_turn_runner import ConsultaTurnRunner
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings
from orion_mcp_v3.public_chat.domain.knowledge import (
    ConhecimentoRecuperado,
    KnowledgeHit,
)
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


def _insert_row(*, question_id, thread_id, topic="faturamento:2026-05", semantic_hash="hash1"):
    return {
        "id": question_id,
        "thread_id": thread_id,
        "parent_question_id": None,
        "topic": topic,
        "intent_contract": {
            "intent": "consulta_metrica",
            "metric": "faturamento",
            "period": "2026-05",
            "confidence": 0.9,
        },
        "semantic_hash": semantic_hash,
        "query_original": "faturamento maio?",
        "created_at": "2026-06-16T00:00:00+00:00",
    }


def _cached_row(*, response_id, topic, semantic_hash, fingerprint="fp-stable"):
    return {
        "id": response_id,
        "topic": topic,
        "semantic_hash": semantic_hash,
        "answer_payload": {"knowledge_ids": [42], "context_keys": [], "essence_themes": []},
        "knowledge_fingerprint": fingerprint,
        "presentation_snapshot": None,
        "expires_at": "2099-01-01T00:00:00+00:00",
    }


def _knowledge() -> ConhecimentoRecuperado:
    return ConhecimentoRecuperado(
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


def _runner(store: ResponseStore, retriever: AsyncMock, llm: AsyncMock | None = None) -> ConsultaTurnRunner:
    llm = llm or AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='{"intent":"consulta_metrica","metric":"faturamento","period":"2026-05","confidence":0.9}'
    )

    async def _stream(*_args, **_kwargs):
        yield LLMStreamChunk(delta="Resposta narrada.")
        yield LLMStreamChunk(delta="", finish_reason="stop")

    llm.stream = _stream
    return ConsultaTurnRunner(
        settings=PublicChatSettings(cache_ttl_days=90),
        store=store,
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )


@pytest.mark.asyncio
async def test_cache_hit_by_semantic_hash() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert,
        {"thread_id": thread_id},
        insert,
        _cached_row(response_id=response_id, topic=insert["topic"], semantic_hash=insert["semantic_hash"]),
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = _knowledge()

    runner = _runner(ResponseStore(_pool_with_conn(conn)), retriever)
    result, _ = await runner.run_turn_with_metadata("faturamento maio?")

    assert result.cached is True
    retriever.retrieve.assert_not_awaited()
    retriever.reload_from_payload.assert_awaited_once()
    link_args = conn.execute.await_args.args
    assert link_args[3] is True


@pytest.mark.asyncio
async def test_cache_hit_regenerates_narrative() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert,
        {"thread_id": thread_id},
        insert,
        _cached_row(response_id=response_id, topic=insert["topic"], semantic_hash=insert["semantic_hash"]),
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='{"intent":"consulta_metrica","metric":"faturamento","period":"2026-05","confidence":0.9}'
    )
    stream_calls = 0

    async def _stream(*_args, **_kwargs):
        nonlocal stream_calls
        stream_calls += 1
        yield LLMStreamChunk(delta="Nova narrativa.")

    llm.stream = _stream

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = _knowledge()

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(),
        store=ResponseStore(_pool_with_conn(conn)),
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )

    _, presentation = await runner.run_turn_with_metadata("faturamento maio?")

    assert stream_calls >= 1
    assert "Nova narrativa." in presentation


@pytest.mark.asyncio
async def test_knowledge_fingerprint_invalidation() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert,
        {"thread_id": thread_id},
        insert,
        _cached_row(
            response_id=response_id,
            topic=insert["topic"],
            semantic_hash=insert["semantic_hash"],
            fingerprint="stale-fp",
        ),
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = _knowledge()

    runner = _runner(ResponseStore(_pool_with_conn(conn)), retriever)
    await runner.run_turn_with_metadata("faturamento maio?")

    fingerprint_arg = conn.fetchval.await_args.args[4]
    assert fingerprint_arg != "stale-fp"


@pytest.mark.asyncio
async def test_runner_full_hit_then_miss() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [insert, {"thread_id": thread_id}, insert, None]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.retrieve.return_value = _knowledge()

    runner = _runner(ResponseStore(_pool_with_conn(conn)), retriever)
    result, _ = await runner.run_turn_with_metadata("faturamento maio?")

    assert result.cached is False
    retriever.retrieve.assert_awaited_once()
