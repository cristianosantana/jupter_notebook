from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.infrastructure.intent_interpreter import PublicIntentInterpreter
from orion_mcp_v3.public_chat.infrastructure.response_store import CachedIntent, ResponseStore


@pytest.mark.asyncio
async def test_intent_cache_hit_skips_llm() -> None:
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-04",
        confidence=0.9,
    )
    cached = CachedIntent(
        topic="faturamento:2026-04",
        intent_contract=contract,
        semantic_hash="abc123",
    )
    store = AsyncMock(spec=ResponseStore)
    store.find_cached_intent.return_value = cached
    llm = AsyncMock()

    interpreter = PublicIntentInterpreter(
        llm,
        store=store,
        use_intent_cache=True,
    )
    result_contract, topic, semantic_hash = await interpreter.interpret(
        "faturamento em abril de 2026?",
        parent_question_id=None,
    )

    llm.chat.assert_not_awaited()
    store.find_cached_intent.assert_awaited_once()
    assert result_contract.intent == "consulta_metrica"
    assert topic == "faturamento:2026-04"
    assert semantic_hash == "abc123"


@pytest.mark.asyncio
async def test_intent_cache_disabled_calls_llm() -> None:
    from orion_mcp_v3.protocols.llm import LLMResponse

    store = AsyncMock(spec=ResponseStore)
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='{"intent":"consulta_metrica","metric":"faturamento","period":"2026-05","confidence":0.9}'
    )

    interpreter = PublicIntentInterpreter(
        llm,
        store=store,
        use_intent_cache=False,
    )
    await interpreter.interpret("faturamento maio?", parent_question_id=None)

    store.find_cached_intent.assert_not_awaited()
    llm.chat.assert_awaited_once()
