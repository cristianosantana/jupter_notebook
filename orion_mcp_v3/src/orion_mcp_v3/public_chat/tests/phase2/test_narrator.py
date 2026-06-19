from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from orion_mcp_v3.protocols.llm import LLMStreamChunk
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.domain.section_parser import DocumentSection
from orion_mcp_v3.public_chat.domain.selected_context import SelectedContext
from orion_mcp_v3.public_chat.infrastructure.narrator import PublicNarrator


@pytest.mark.asyncio
async def test_narrator_fallback_no_hits() -> None:
    narrator = PublicNarrator(AsyncMock())
    contract = IntentContract(intent="geral", confidence=0.0)
    selected = SelectedContext(sections=())
    text = await narrator.render("pergunta", contract=contract, selected=selected)
    assert text == "Não encontrei informações validadas sobre isso."


@pytest.mark.asyncio
async def test_narrator_stream_mock_llm() -> None:
    provider = AsyncMock()

    async def _stream(*_args, **_kwargs):
        yield LLMStreamChunk(delta="Faturamento ")
        yield LLMStreamChunk(delta="de maio.")
        yield LLMStreamChunk(delta="", finish_reason="stop")

    provider.stream = _stream
    narrator = PublicNarrator(provider)
    knowledge = ConhecimentoRecuperado(
        hits=(
            KnowledgeHit(
                origin_id=1,
                context_key="ctx",
                category="Financeiro",
                validated_answer="100",
                key_metrics={"faturamento": 100},
            ),
        )
    )

    selected = SelectedContext(
        sections=(
            DocumentSection(
                id="s1",
                title="documento",
                body="100",
                source_hit_id=1,
                context_key="ctx",
            ),
        ),
        source_context_chars=3,
        selected_context_chars=3,
    )
    contract = IntentContract(intent="consulta_metrica", metric="faturamento", confidence=0.9)

    parts: list[str] = []
    async for delta in narrator.stream("faturamento?", contract=contract, selected=selected):
        parts.append(delta)

    assert "".join(parts) == "Faturamento de maio."
