"""
Narrator Runtime (Fase 5.2) — fecha o ciclo cognitivo chamando o LLM.

Recebe :class:`~CognitiveOrchestrationResult`, monta mensagens com salvaguardas
anti-alucinação, chama o :class:`~LLMProvider` e devolve :class:`NarrationResult`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Mapping

from orion_mcp_v3.contracts.context_block import ContextBlock
from orion_mcp_v3.protocols.llm import (
    ChatMessage,
    LLMProvider,
    LLMResponse,
    LLMResponseMeta,
    NullLLMProvider,
)
from orion_mcp_v3.runtime.cognitive_orchestrator import CognitiveOrchestrationResult


# ── Salvaguardas anti-alucinação ─────────────────────────────────────

_SYSTEM_PREAMBLE = (
    "Você é um analista de dados preciso. "
    "Responda APENAS com base nos dados e evidências fornecidos no contexto. "
    "Regras obrigatórias:\n"
    "1. Não invente números, nomes ou métricas que não estejam no contexto.\n"
    "2. Use frases como «com base no resumo estatístico fornecido…», "
    "«nos dados amostrados…», «de acordo com a evidência disponível…».\n"
    "3. Se a cobertura dos dados for parcial, diga explicitamente: "
    "«sem acesso à totalidade dos registos, esta análise cobre X de Y».\n"
    "4. Cite o período, volume e método de agregação quando disponíveis.\n"
    "5. Se não houver dados suficientes para responder, diga claramente "
    "que a informação é insuficiente — NUNCA preencha lacunas com suposições.\n"
)

_COVERAGE_TEMPLATE = (
    "\n\n[COBERTURA] Volume de dados: {volume}. "
    "Confiança do digest: {confidence}. "
    "Método de agregação: {aggregation_logic}."
)

_EVIDENCE_TEMPLATE = (
    "\n\n[EVIDÊNCIA] {summary}"
)


def _extract_coverage_note(result: CognitiveOrchestrationResult) -> str:
    """Monta nota de cobertura a partir dos blocos empacotados."""
    lines: list[str] = []
    for b in result.packed_blocks:
        vol = b.metadata.get("volume")
        agg = b.metadata.get("aggregation_logic")
        fk = b.metadata.get("fusion_kind")
        if vol is not None or agg is not None:
            conf = b.metadata.get("confidence", b.relevance_score)
            lines.append(
                _COVERAGE_TEMPLATE.format(
                    volume=vol or "n/d",
                    confidence=f"{conf}" if conf is not None else "n/d",
                    aggregation_logic=agg or "n/d",
                )
            )
        if fk == "evidence":
            lines.append(_EVIDENCE_TEMPLATE.format(summary=b.text[:600]))
    return "\n".join(lines) if lines else ""


def _build_narrator_messages(
    result: CognitiveOrchestrationResult,
    *,
    system_preamble: str | None = None,
    extra_instructions: str = "",
) -> list[ChatMessage]:
    """Monta as mensagens do chat para o LLM."""
    preamble = system_preamble or _SYSTEM_PREAMBLE
    coverage = _extract_coverage_note(result)
    system_text = preamble.strip()
    if coverage:
        system_text += "\n" + coverage.strip()
    if extra_instructions:
        system_text += "\n\n" + extra_instructions.strip()

    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_text)]

    if result.prompt_text.strip():
        messages.append(ChatMessage(role="user", content=result.prompt_text))

    return messages


# ── Resultado ────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class NarrationResult:
    """Resultado da narração: texto do LLM + metadados + mensagens enviadas."""

    narration: str
    llm_response: LLMResponse
    messages_sent: tuple[ChatMessage, ...]
    coverage_note: str
    safeguards_applied: tuple[str, ...]


# ── Narrator ─────────────────────────────────────────────────────────

class CognitiveNarrator:
    """
    Fecha o ciclo cognitivo: ``CognitiveOrchestrationResult → LLM → NarrationResult``.

    Salvaguardas anti-alucinação são injectadas no system prompt automaticamente.
    Compatível com qualquer :class:`~LLMProvider` (incluindo :class:`~NullLLMProvider`
    e :class:`~EchoLLMProvider` para testes).
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        system_preamble: str | None = None,
        extra_instructions: str = "",
    ) -> None:
        self._provider: LLMProvider = provider or NullLLMProvider()
        self._preamble = system_preamble
        self._extra = extra_instructions

    async def narrate(
        self,
        result: CognitiveOrchestrationResult,
        **llm_kwargs: Any,
    ) -> NarrationResult:
        """Monta mensagens, chama o LLM e devolve resultado com traçabilidade."""
        messages = _build_narrator_messages(
            result,
            system_preamble=self._preamble,
            extra_instructions=self._extra,
        )

        llm_resp = await self._provider.chat(messages, **llm_kwargs)

        safeguards = [
            "anti_hallucination_preamble",
            "coverage_note_injected" if _extract_coverage_note(result) else "no_coverage_data",
            "evidence_cited" if any(
                b.metadata.get("fusion_kind") == "evidence" for b in result.packed_blocks
            ) else "no_evidence",
        ]

        return NarrationResult(
            narration=llm_resp.text,
            llm_response=llm_resp,
            messages_sent=tuple(messages),
            coverage_note=_extract_coverage_note(result),
            safeguards_applied=tuple(safeguards),
        )

    async def narrate_stream(
        self,
        result: CognitiveOrchestrationResult,
        **llm_kwargs: Any,
    ):
        """Versão streaming — devolve iterador assíncrono de :class:`~LLMStreamChunk`."""
        messages = _build_narrator_messages(
            result,
            system_preamble=self._preamble,
            extra_instructions=self._extra,
        )
        async for chunk in self._provider.stream(messages, **llm_kwargs):
            yield chunk
