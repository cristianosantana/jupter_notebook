"""Testes Fase 4D — resposta focalizada e pipeline."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from orion_mcp_v3.protocols.llm import LLMResponse, LLMStreamChunk
from orion_mcp_v3.public_chat.application.consulta_turn_runner import ConsultaTurnRunner
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.domain.section_parser import DocumentSection
from orion_mcp_v3.public_chat.domain.selected_context import SelectedContext
from orion_mcp_v3.public_chat.infrastructure.context_selector import PublicContextSelector
from orion_mcp_v3.public_chat.infrastructure.intent_interpreter import PublicIntentInterpreter
from orion_mcp_v3.public_chat.infrastructure.narrator import PublicNarrator
from orion_mcp_v3.public_chat.infrastructure.remissive_retriever import RemissiveRetriever
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore
from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry
from orion_mcp_v3.public_chat.tests.phase4.fixtures import FECHAMENTO_MARCO_2026, march_hit
from orion_mcp_v3.public_chat.tests.phase4.helpers import PassthroughContextSelector


def _pool_with_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.mark.asyncio
async def test_narrator_prompt_contains_only_selected() -> None:
    provider = AsyncMock()
    captured: dict[str, str] = {}

    async def _stream(messages, **_kwargs):
        captured["user"] = messages[1].content
        yield LLMStreamChunk(delta="Depósito Bancário.")
        yield LLMStreamChunk(delta="", finish_reason="stop")

    provider.stream = _stream
    narrator = PublicNarrator(provider)
    contract = IntentContract(
        intent="consulta_metrica",
        period="2026-03",
        operation=PublicOperationType.RANKING_ASC.value,
        dimension="forma_pagamento",
        confidence=0.8,
    )
    selected = SelectedContext(
        sections=(
            DocumentSection(
                id="4:s1",
                title="Formas de pagamento",
                body="Depósito Bancário R$ 3.690,00",
                source_hit_id=4,
                context_key="marco",
            ),
        ),
        source_context_chars=100,
        selected_context_chars=30,
    )
    parts: list[str] = []
    async for delta in narrator.stream("pior forma pagamento?", contract=contract, selected=selected):
        parts.append(delta)
    assert "Depósito Bancário" in captured["user"]
    assert "Produção por serviço" not in captured["user"]


def test_narrator_qa_not_summary() -> None:
    prompt = get_public_chat_prompt_registry().get_text("public_chat_narrator.system")
    assert "Question Answering" in prompt
    assert "resumo executivo" in prompt.lower()


@pytest.mark.asyncio
async def test_runner_end_to_end_pior_forma_pagamento() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert_row = {
        "id": question_id,
        "thread_id": thread_id,
        "parent_question_id": None,
        "topic": "forma_pagamento:2026-03",
        "intent_contract": {},
        "semantic_hash": "hash-pior",
        "query_original": "qual a forma de pagamento foi pior em março de 2026?",
        "created_at": "2026-06-16T00:00:00+00:00",
    }
    conn = AsyncMock()
    conn.fetchrow.side_effect = [insert_row, {"thread_id": thread_id}, insert_row, None]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    llm = AsyncMock()
    llm.chat.side_effect = [
        LLMResponse(
            text=json.dumps(
                {
                    "intent": "consulta_metrica",
                    "period": "2026-03",
                    "operation": "ranking_asc",
                    "dimension": "forma_pagamento",
                    "confidence": 0.85,
                }
            )
        ),
    ]

    async def _stream(messages, **_kwargs):
        user_payload = json.loads(messages[1].content)
        if "context_sections" in user_payload:
            yield LLMStreamChunk(
                delta=(
                    "A forma de pagamento com menor faturamento foi Depósito Bancário, "
                    "totalizando R$ 3.690,00. Cheque e Permuta não tiveram movimentação."
                )
            )
        yield LLMStreamChunk(delta="", finish_reason="stop")

    llm.stream = _stream

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.retrieve.return_value = ConhecimentoRecuperado(hits=(march_hit(),))

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(cache_ttl_days=90),
        store=ResponseStore(_pool_with_conn(conn)),
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )
    result, answer = await runner.run_turn_with_metadata(
        "qual a forma de pagamento foi pior em março de 2026?"
    )
    assert result.cached is False
    assert "Depósito Bancário" in answer
    assert "Cartão" not in answer or "dominant" not in answer.lower()


@pytest.mark.asyncio
async def test_runner_cache_hit_recomputes_selection() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    topic = "forma_pagamento:2026-03"
    semantic_hash = "hash-pior"
    insert_row = {
        "id": question_id,
        "thread_id": thread_id,
        "parent_question_id": None,
        "topic": topic,
        "intent_contract": {},
        "semantic_hash": semantic_hash,
        "query_original": "qual a forma de pagamento foi pior em março de 2026?",
        "created_at": "2026-06-16T00:00:00+00:00",
    }
    cached_row = {
        "id": response_id,
        "topic": topic,
        "semantic_hash": semantic_hash,
        "answer_payload": {"knowledge_ids": [4], "context_keys": [], "essence_themes": []},
        "knowledge_fingerprint": "fp-stable",
        "presentation_snapshot": None,
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert_row,
        {"thread_id": thread_id},
        insert_row,
        cached_row,
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text=json.dumps(
            {
                "intent": "consulta_metrica",
                "period": "2026-03",
                "operation": "ranking_asc",
                "dimension": "forma_pagamento",
                "confidence": 0.85,
            }
        )
    )

    async def _stream(*_args, **_kwargs):
        yield LLMStreamChunk(delta="Depósito Bancário R$ 3.690,00.")
        yield LLMStreamChunk(delta="", finish_reason="stop")

    llm.stream = _stream

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = ConhecimentoRecuperado(hits=(march_hit(),))

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(cache_ttl_days=90),
        store=ResponseStore(_pool_with_conn(conn)),
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )
    result, answer = await runner.run_turn_with_metadata(
        "qual a forma de pagamento foi pior em março de 2026?"
    )
    assert result.cached is True
    retriever.retrieve.assert_not_awaited()
    retriever.reload_from_payload.assert_awaited_once()
    assert "Depósito" in answer
