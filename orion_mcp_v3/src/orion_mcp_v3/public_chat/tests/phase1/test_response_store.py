from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from orion_mcp_v3.public_chat.application.context_window import load_context_window
from orion_mcp_v3.public_chat.domain.errors import InvalidParentQuestionError
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicIntentType
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore


def _pool_with_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _question_row(
    *,
    question_id: UUID,
    thread_id: UUID,
    parent_question_id: UUID | None,
    query_original: str,
    contract: IntentContract,
) -> dict[str, object]:
    return {
        "id": question_id,
        "thread_id": thread_id,
        "parent_question_id": parent_question_id,
        "topic": "faturamento:2026-05",
        "intent_contract": contract.as_mapping(),
        "semantic_hash": "abc123",
        "query_original": query_original,
        "created_at": datetime(2026, 6, 16, tzinfo=timezone.utc),
    }


@pytest.mark.asyncio
async def test_root_question_thread_id() -> None:
    question_id = uuid4()
    contract = IntentContract(
        intent=PublicIntentType.CONSULTA_METRICA.value,
        metric="faturamento",
        period="2026-05",
        confidence=0.9,
    )
    insert_row = _question_row(
        question_id=question_id,
        thread_id=question_id,
        parent_question_id=None,
        query_original="Qual o faturamento de maio?",
        contract=contract,
    )

    conn = AsyncMock()
    conn.fetchrow.side_effect = [insert_row, {"thread_id": question_id}, insert_row]

    store = ResponseStore(_pool_with_conn(conn))
    question = await store.insert_question(
        query_original="Qual o faturamento de maio?",
        topic="faturamento:2026-05",
        intent_contract=contract,
        semantic_hash="abc123",
    )

    assert question.parent_question_id is None
    assert question.thread_id == question.id


@pytest.mark.asyncio
async def test_follow_up_chain() -> None:
    root_id = uuid4()
    parent_id = uuid4()
    child_id = uuid4()
    thread_id = root_id
    contract = IntentContract(
        intent=PublicIntentType.CONSULTA_METRICA.value,
        metric="faturamento",
        period="2026-05",
        confidence=0.9,
    )
    parent_row = _question_row(
        question_id=parent_id,
        thread_id=thread_id,
        parent_question_id=root_id,
        query_original="Qual o faturamento de maio?",
        contract=contract,
    )
    child_contract = IntentContract(
        intent=PublicIntentType.CONSULTA_METRICA.value,
        metric="faturamento",
        period="2026-06",
        confidence=0.88,
    )
    child_row = _question_row(
        question_id=child_id,
        thread_id=thread_id,
        parent_question_id=parent_id,
        query_original="e em junho?",
        contract=child_contract,
    )

    conn = AsyncMock()
    conn.fetchrow.side_effect = [parent_row, child_row]

    store = ResponseStore(_pool_with_conn(conn))
    question = await store.insert_question(
        query_original="e em junho?",
        topic="faturamento:2026-06",
        intent_contract=child_contract,
        semantic_hash="def456",
        parent_question_id=parent_id,
    )

    assert question.parent_question_id == parent_id
    assert question.thread_id == thread_id


@pytest.mark.asyncio
async def test_invalid_parent_question() -> None:
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    store = ResponseStore(_pool_with_conn(conn))

    with pytest.raises(InvalidParentQuestionError):
        await store.insert_question(
            query_original="e em junho?",
            topic="geral",
            intent_contract=IntentContract.geral(),
            semantic_hash="000",
            parent_question_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_context_window_depth() -> None:
    q1 = uuid4()
    q2 = uuid4()
    q3 = uuid4()
    q4 = uuid4()
    contract = IntentContract(
        intent=PublicIntentType.CONSULTA_METRICA.value,
        metric="faturamento",
        confidence=0.9,
    )

    rows = {
        q4: _question_row(
            question_id=q4,
            thread_id=q1,
            parent_question_id=q3,
            query_original="e abril?",
            contract=contract,
        ),
        q3: _question_row(
            question_id=q3,
            thread_id=q1,
            parent_question_id=q2,
            query_original="e março?",
            contract=contract,
        ),
        q2: _question_row(
            question_id=q2,
            thread_id=q1,
            parent_question_id=q1,
            query_original="e fevereiro?",
            contract=contract,
        ),
        q1: _question_row(
            question_id=q1,
            thread_id=q1,
            parent_question_id=None,
            query_original="faturamento?",
            contract=contract,
        ),
    }

    conn = AsyncMock()

    async def _fetchrow(query: str, question_id: UUID) -> dict[str, object] | None:
        return rows.get(question_id)

    conn.fetchrow.side_effect = _fetchrow
    store = ResponseStore(_pool_with_conn(conn))

    ancestors = await load_context_window(store, q4, max_depth=2)

    assert len(ancestors) == 2
    assert [turn.question_id for turn in ancestors] == [q2, q3]
    assert ancestors[0].query_original == "e fevereiro?"
