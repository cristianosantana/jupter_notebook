from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from orion_mcp_v3.protocols.llm import LLMResponse
from orion_mcp_v3.public_chat.domain.intent_contract import PublicIntentType
from orion_mcp_v3.public_chat.infrastructure.intent_interpreter import PublicIntentInterpreter


@pytest.mark.asyncio
async def test_intent_interpreter_mock_llm() -> None:
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        text=json.dumps(
            {
                "intent": "consulta_metrica",
                "metric": "faturamento",
                "period": "2026-05",
                "domain": "financeiro",
                "entity_filters": [],
                "confidence": 0.93,
            }
        )
    )
    interpreter = PublicIntentInterpreter(provider, min_confidence=0.5)

    contract, topic, semantic_hash = await interpreter.interpret("Qual o faturamento de maio?")

    assert contract.intent == PublicIntentType.CONSULTA_METRICA.value
    assert contract.metric == "faturamento"
    assert topic == "faturamento:2026-05"
    assert len(semantic_hash) == 64
    provider.chat.assert_awaited_once()
