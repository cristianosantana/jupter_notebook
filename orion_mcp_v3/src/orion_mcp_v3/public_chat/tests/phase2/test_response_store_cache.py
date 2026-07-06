from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from orion_mcp_v3.public_chat.domain.knowledge import AnswerPayload
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore


def _pool_with_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.mark.asyncio
async def test_upsert_resolution_payload() -> None:
    conn = AsyncMock()
    conn.fetchval.return_value = uuid4()
    store = ResponseStore(_pool_with_conn(conn))

    payload = AnswerPayload(
        context_keys=("ctx",),
        knowledge_ids=(42,),
        essence_themes=("fechamento",),
    )
    response_id = await store.upsert_resolution(
        topic="faturamento:2026-05",
        semantic_hash="abc123",
        answer_payload=payload,
        knowledge_fingerprint="fp123",
        cache_ttl_days=90,
    )

    assert response_id is not None
    sql = str(conn.fetchval.await_args.args[0])
    assert "public_chat_responses" in sql
    assert "answer_payload" in sql
    payload_arg = conn.fetchval.await_args.args[3]
    parsed = json.loads(payload_arg)
    assert parsed["knowledge_ids"] == [42]


@pytest.mark.asyncio
async def test_find_cached_intent_returns_latest_contract() -> None:
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "topic": "parcelas:2026-04",
        "intent_contract": {
            "intent": "consulta_metrica",
            "metric": "faturamento",
            "period": "2026-04",
            "confidence": 0.9,
        },
        "semantic_hash": "hash-stable",
    }
    store = ResponseStore(_pool_with_conn(conn))

    cached = await store.find_cached_intent(
        "qual o total em cartão de crédito em 10x em abril de 2026?",
        parent_question_id=None,
    )

    assert cached is not None
    assert cached.topic == "parcelas:2026-04"
    assert cached.semantic_hash == "hash-stable"
    sql = str(conn.fetchrow.await_args.args[0])
    assert "query_normalized" in sql


@pytest.mark.asyncio
async def test_find_resolution_returns_cached_payload() -> None:
    response_id = uuid4()
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "id": response_id,
        "topic": "faturamento:2026-05",
        "semantic_hash": "abc",
        "answer_payload": {
            "context_keys": ["ctx"],
            "knowledge_ids": [42],
            "essence_themes": [],
        },
        "knowledge_fingerprint": "fp",
        "presentation_snapshot": None,
        "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc),
    }
    store = ResponseStore(_pool_with_conn(conn))

    cached = await store.find_resolution("faturamento:2026-05", "abc")

    assert cached is not None
    assert cached.id == response_id
    assert cached.answer_payload.knowledge_ids == (42,)
