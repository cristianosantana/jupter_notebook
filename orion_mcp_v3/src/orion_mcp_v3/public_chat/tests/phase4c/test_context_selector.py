"""Testes Fase 4C — selecção de contexto."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from orion_mcp_v3.protocols.llm import LLMResponse
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.section_parser import parse_document
from orion_mcp_v3.public_chat.infrastructure.context_selector import PublicContextSelector
from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry
from orion_mcp_v3.public_chat.tests.phase4.fixtures import march_hit


@pytest.mark.asyncio
async def test_context_selector_picks_payment_section() -> None:
    document = parse_document(march_hit())
    provider = AsyncMock()
    payment_section = next(
        section for section in document.sections if "pagamento" in section.title.lower()
    )
    catalog_id = f"{document.source_hit_id}:{payment_section.id}"
    provider.chat.return_value = LLMResponse(
        text=json.dumps(
            {
                "selected_section_ids": [catalog_id],
                "reason": "pergunta sobre forma de pagamento",
            }
        )
    )
    selector = PublicContextSelector(provider)
    contract = IntentContract(
        intent="consulta_metrica",
        period="2026-03",
        operation=PublicOperationType.RANKING_ASC.value,
        dimension="forma_pagamento",
        confidence=0.8,
    )
    selected = await selector.select(
        "qual a forma de pagamento foi pior em março de 2026?",
        contract=contract,
        documents=(document,),
    )
    assert selected.degraded is False
    assert len(selected.sections) == 1
    assert "pagamento" in selected.sections[0].title.lower()


@pytest.mark.asyncio
async def test_context_selector_fallback_degraded() -> None:
    document = parse_document(march_hit())
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(text="not-json")
    selector = PublicContextSelector(provider)
    contract = IntentContract(intent="geral", confidence=0.5)
    selected = await selector.select("pergunta?", contract=contract, documents=(document,))
    assert selected.degraded is True
    assert len(selected.sections) == len(document.sections)


def test_selector_prompt_forbids_answering() -> None:
    prompt = get_public_chat_prompt_registry().get_text("public_chat_context_selector.system")
    assert "Nunca responda" in prompt
    assert "Nunca calcule rankings" in prompt
