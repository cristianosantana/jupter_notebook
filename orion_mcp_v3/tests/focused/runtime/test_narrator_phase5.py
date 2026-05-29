"""Fase 5 — Narrador LLM: protocols, providers, narrator runtime."""

from __future__ import annotations

import asyncio

from orion_mcp_v3.protocols.llm import (
    ChatMessage,
    EchoLLMProvider,
    LLMProvider,
    LLMResponse,
    LLMResponseMeta,
    LLMStreamChunk,
    LLMUsage,
    NullLLMProvider,
)
from orion_mcp_v3.runtime import (
    AttentionPolicy,
    CognitiveNarrator,
    CognitiveOrchestrator,
    NarrationResult,
)


# ── 5.1 LLM Contracts ───────────────────────────────────────────────


def test_llm_usage_defaults() -> None:
    u = LLMUsage()
    assert u.prompt_tokens == 0
    assert u.total_tokens == 0


def test_llm_response_meta_defaults() -> None:
    m = LLMResponseMeta()
    assert m.finish_reason == "stop"
    assert m.latency_ms == 0.0


def test_llm_response_has_text_and_meta() -> None:
    r = LLMResponse(text="hello", meta=LLMResponseMeta(finish_reason="stop", model="test"))
    assert r.text == "hello"
    assert r.meta.model == "test"


def test_chat_message_fields() -> None:
    m = ChatMessage(role="user", content="olá")
    assert m.role == "user"
    assert m.content == "olá"


def test_null_provider_returns_fixed() -> None:
    p = NullLLMProvider(fixed_response="teste fixo")
    r = asyncio.run(p.generate("qualquer"))
    assert r.text == "teste fixo"
    assert r.meta.finish_reason == "null_provider"


def test_null_provider_chat() -> None:
    p = NullLLMProvider()
    msgs = [ChatMessage("user", "hi")]
    r = asyncio.run(p.chat(msgs))
    assert "NullLLM" in r.text


def test_null_provider_stream() -> None:
    p = NullLLMProvider(fixed_response="stream test")

    async def collect():
        chunks = []
        async for c in p.stream([ChatMessage("user", "x")]):
            chunks.append(c)
        return chunks

    chunks = asyncio.run(collect())
    assert len(chunks) >= 1
    assert isinstance(chunks[0], LLMStreamChunk)
    assert chunks[0].delta == "stream test"


def test_echo_provider_generate() -> None:
    p = EchoLLMProvider()
    r = asyncio.run(p.generate("olá mundo"))
    assert "olá mundo" in r.text
    assert r.meta.model == "echo"
    assert r.meta.usage.prompt_tokens > 0


def test_echo_provider_chat() -> None:
    p = EchoLLMProvider()
    msgs = [ChatMessage("user", "faturamento")]
    r = asyncio.run(p.chat(msgs))
    assert "faturamento" in r.text


def test_echo_provider_stream() -> None:
    p = EchoLLMProvider()

    async def collect():
        chunks = []
        async for c in p.stream([ChatMessage("user", "dados")]):
            chunks.append(c)
        return chunks

    chunks = asyncio.run(collect())
    assert len(chunks) >= 1
    full = "".join(c.delta for c in chunks)
    assert "dados" in full


def test_null_provider_is_llm_provider() -> None:
    p = NullLLMProvider()
    assert isinstance(p, LLMProvider)


def test_echo_provider_is_llm_provider() -> None:
    p = EchoLLMProvider()
    assert isinstance(p, LLMProvider)


# ── 5.2 Narrator Runtime ────────────────────────────────────────────


def _make_orchestration_result():
    orch = CognitiveOrchestrator()
    return orch.finalize_prompt(
        "qual o faturamento total?",
        policy=AttentionPolicy.ANALYTICAL,
        max_tokens=512,
    )


def test_narrator_with_null_provider() -> None:
    result = _make_orchestration_result()
    narrator = CognitiveNarrator(NullLLMProvider())
    nr = asyncio.run(narrator.narrate(result))
    assert isinstance(nr, NarrationResult)
    assert "NullLLM" in nr.narration
    assert len(nr.messages_sent) >= 2
    assert nr.messages_sent[0].role == "system"
    assert "anti_hallucination_preamble" in nr.safeguards_applied


def test_narrator_with_echo_provider() -> None:
    result = _make_orchestration_result()
    narrator = CognitiveNarrator(EchoLLMProvider())
    nr = asyncio.run(narrator.narrate(result))
    assert nr.narration
    assert "[Echo]" in nr.narration
    assert nr.llm_response.meta.model == "echo"


def test_narrator_system_message_contains_anti_hallucination() -> None:
    result = _make_orchestration_result()
    narrator = CognitiveNarrator(NullLLMProvider())
    nr = asyncio.run(narrator.narrate(result))
    sys_msg = nr.messages_sent[0].content
    assert "Não invente" in sys_msg
    assert "resumo estatístico" in sys_msg
    assert "dados amostrados" in sys_msg
    assert "sem acesso à totalidade" in sys_msg


def test_narrator_extra_instructions() -> None:
    result = _make_orchestration_result()
    narrator = CognitiveNarrator(
        NullLLMProvider(),
        extra_instructions="Responda sempre em português.",
    )
    nr = asyncio.run(narrator.narrate(result))
    sys_msg = nr.messages_sent[0].content
    assert "português" in sys_msg


def test_narrator_custom_preamble() -> None:
    result = _make_orchestration_result()
    narrator = CognitiveNarrator(
        NullLLMProvider(),
        system_preamble="Custom preamble here.",
    )
    nr = asyncio.run(narrator.narrate(result))
    assert nr.messages_sent[0].content.startswith("Custom preamble")


def test_narrator_stream() -> None:
    result = _make_orchestration_result()
    narrator = CognitiveNarrator(EchoLLMProvider())

    async def collect():
        chunks = []
        async for c in narrator.narrate_stream(result):
            chunks.append(c)
        return chunks

    chunks = asyncio.run(collect())
    assert len(chunks) >= 1
    full = "".join(c.delta for c in chunks)
    assert len(full) > 0


def test_narrator_with_evidence_coverage() -> None:
    from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
    from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
    from orion_mcp_v3.runtime.provenance import CoverageInfo

    evidence = EvidenceBlock(
        summary="Média de faturamento: R$ 42k",
        insights={"trends": {"direction": "up"}},
        metrics={"value_key": "amt", "input_rows": 120},
        confidence=0.82,
        coverage=CoverageInfo(labels={"rows_in": 120}, notes="evidence"),
    )

    orch = CognitiveOrchestrator()
    result = orch.finalize_prompt(
        "qual o faturamento?",
        policy=AttentionPolicy.ANALYTICAL,
        evidence=evidence,
        max_tokens=1024,
    )

    narrator = CognitiveNarrator(EchoLLMProvider())
    nr = asyncio.run(narrator.narrate(result))
    assert "evidence_cited" in nr.safeguards_applied or "no_evidence" in nr.safeguards_applied
    assert nr.narration


def test_narrator_preserves_complete_direct_answer_instruction() -> None:
    from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
    from orion_mcp_v3.runtime.provenance import CoverageInfo

    evidence = EvidenceBlock(
        summary="Resposta direta: ticket médio por item:\n1. ppf: R$ 1.000,00",
        insights={},
        metrics={
            "answer_plan": {
                "template_slug": "itens_vendidos",
                "measure": "ticket_medio_item",
                "dimension": "item",
                "operation": "list",
                "result_scope": {"mode": "all", "limit": None},
            }
        },
        supporting_data={
            "direct_answer": {
                "plan": {
                    "operation": "list",
                    "result_scope": {"mode": "all", "limit": None},
                },
                "summary": "Resposta direta: ticket médio por item:\n1. ppf: R$ 1.000,00",
            }
        },
        confidence=0.95,
        coverage=CoverageInfo(labels={"rows_in": 1}, notes="evidence"),
    )

    result = CognitiveOrchestrator().finalize_prompt(
        "Qual o ticket médio por item do período?",
        policy=AttentionPolicy.ANALYTICAL,
        evidence=evidence,
        max_tokens=1024,
    )
    nr = asyncio.run(CognitiveNarrator(NullLLMProvider()).narrate(result))
    sys_msg = nr.messages_sent[0].content

    assert "preserve literalmente a seção `Resposta direta:`" in sys_msg
    assert "não produza visão geral" in sys_msg
    assert "direct_answer_literal_preservation" in nr.safeguards_applied


def test_narration_result_fields() -> None:
    result = _make_orchestration_result()
    narrator = CognitiveNarrator(NullLLMProvider())
    nr = asyncio.run(narrator.narrate(result))
    assert isinstance(nr.narration, str)
    assert isinstance(nr.llm_response, LLMResponse)
    assert isinstance(nr.messages_sent, tuple)
    assert isinstance(nr.coverage_note, str)
    assert isinstance(nr.safeguards_applied, tuple)
