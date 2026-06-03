"""
Narrator Runtime (Fase 5.2) — fecha o ciclo cognitivo chamando o LLM.

Recebe :class:`~CognitiveOrchestrationResult`, monta mensagens com salvaguardas
anti-alucinação, chama o :class:`~LLMProvider` e devolve :class:`NarrationResult`.
"""

from __future__ import annotations

import logging
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
from orion_mcp_v3.prompts import get_prompt_registry
from orion_mcp_v3.runtime.cognitive_orchestrator import CognitiveOrchestrationResult

_LOG = logging.getLogger(__name__)


_PROMPTS = get_prompt_registry()
_SYSTEM_PREAMBLE = _PROMPTS.get_text("narrator.base")
_COVERAGE_TEMPLATE = _PROMPTS.get_fragment("narrator.base", "coverage_template")
_EVIDENCE_TEMPLATE = _PROMPTS.get_fragment("narrator.base", "evidence_template")
_DIRECT_ANSWER_LITERAL_TEMPLATE = _PROMPTS.get_fragment("narrator.base", "direct_answer_literal")
_REASONING_TEMPLATE = _PROMPTS.get_fragment("narrator.base", "reasoning_template")


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
            direct_answer_set = b.metadata.get("direct_answer_set")
            if isinstance(direct_answer_set, Mapping) and direct_answer_set.get("collection_slug"):
                row_count = b.metadata.get("row_count")
                confidence = b.metadata.get("confidence", b.relevance_score)
                collection = direct_answer_set.get("collection_slug") or "direct_answer_set"
                parts = [f"coleção {collection}"]
                if row_count is not None:
                    parts.append(f"{row_count} registro(s) analisado(s)")
                if confidence is not None:
                    parts.append(f"confiança {confidence}")
                lines.append("Cobertura da evidência estruturada: " + "; ".join(parts))
            else:
                lines.append(_EVIDENCE_TEMPLATE.format(summary=b.text))
    return "\n".join(lines) if lines else ""


def _extract_reasoning_note(result: CognitiveOrchestrationResult) -> str:
    for b in result.packed_blocks:
        if b.metadata.get("fusion_kind") != "reasoning_result":
            continue
        answer_mode = b.metadata.get("answer_mode")
        prefix = f"answer_mode: {answer_mode}\n" if answer_mode else ""
        return _REASONING_TEMPLATE.format(reasoning_json=f"{prefix}{b.text}")
    return ""


def _reasoning_answer_mode(result: CognitiveOrchestrationResult) -> str | None:
    for b in result.packed_blocks:
        if b.metadata.get("fusion_kind") == "reasoning_result":
            mode = b.metadata.get("answer_mode")
            return str(mode) if mode else None
    return None


def _direct_answer_requires_literal_preservation(result: CognitiveOrchestrationResult) -> bool:
    if _reasoning_answer_mode(result) == "literal":
        return True
    for b in result.packed_blocks:
        direct = b.metadata.get("direct_answer")
        if not isinstance(direct, Mapping):
            continue
        plan = direct.get("plan")
        if not isinstance(plan, Mapping):
            continue
        scope = plan.get("result_scope")
        if isinstance(scope, Mapping) and scope.get("mode") == "all":
            return True
        if plan.get("operation") == "list":
            return True
    return False


def _build_narrator_messages(
    result: CognitiveOrchestrationResult,
    *,
    system_preamble: str | None = None,
    extra_instructions: str = "",
) -> list[ChatMessage]:
    """Monta as mensagens do chat para o LLM."""
    preamble = system_preamble or _SYSTEM_PREAMBLE
    coverage = _extract_coverage_note(result)
    reasoning = _extract_reasoning_note(result)
    system_text = preamble.strip()
    if _direct_answer_requires_literal_preservation(result):
        system_text += _DIRECT_ANSWER_LITERAL_TEMPLATE
    if reasoning:
        system_text += "\n" + reasoning.strip()
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
        _LOG.info(
            "narrator: provider=%s reply_chars=%d",
            type(self._provider).__name__,
            len(llm_resp.text or ""),
        )

        safeguards = [
            "anti_hallucination_preamble",
            "coverage_note_injected" if _extract_coverage_note(result) else "no_coverage_data",
            "reasoning_result_present" if _reasoning_answer_mode(result) else "no_reasoning_result",
            "evidence_cited" if any(
                b.metadata.get("fusion_kind") == "evidence" for b in result.packed_blocks
            ) else "no_evidence",
        ]
        mode = _reasoning_answer_mode(result)
        if mode:
            safeguards.append(f"answer_mode_{mode}")
        if _direct_answer_requires_literal_preservation(result):
            safeguards.append("direct_answer_literal_preservation")

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
        reply_chars = 0
        try:
            async for chunk in self._provider.stream(messages, **llm_kwargs):
                reply_chars += len(chunk.delta or "")
                yield chunk
        finally:
            _LOG.info(
                "narrator_stream: provider=%s reply_chars=%d",
                type(self._provider).__name__,
                reply_chars,
            )
