"""
Gatilhos para actualizar metadata com resumos / notas (memory prompts).

Com `memory_prompts_enabled=false`, todas as funções são no-op.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.agent_trace import llm_phase_context
from app.config import Settings, get_settings

_logger = logging.getLogger(__name__)
_MEMORY_DIR = Path(__file__).resolve().parent / "prompts" / "memory"


def _read_memory_prompt(name: str) -> str:
    path = _MEMORY_DIR / name
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


async def run_memory_llm(
    provider: Any,
    *,
    prompt_file: str,
    user_payload: str,
    settings: Settings | None = None,
) -> str | None:
    """
    Uma chamada LLM sem tools (system = ficheiro memory, user = payload).
    Retorna texto do assistente ou None se desligado / erro.
    """
    st = settings or get_settings()
    if not st.memory_prompts_enabled:
        return None
    system = _read_memory_prompt(prompt_file)
    if not system:
        _logger.debug("memory prompt missing: %s", prompt_file)
        return None
    try:
        with llm_phase_context(f"memory:{prompt_file}"):
            msg = await provider.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_payload[:120_000]},
                ],
                tools=None,
            )
        return str((msg or {}).get("content") or "").strip() or None
    except Exception as e:
        _logger.warning("memory llm failed (%s): %s", prompt_file, e)
        return None


async def maybe_update_conversation_summary(
    provider: Any,
    metadata: dict[str, Any],
    transcript_excerpt: str,
    settings: Settings | None = None,
) -> None:
    st = settings or get_settings()
    if not (st.memory_prompts_enabled and st.memory_conversation_summary_enabled):
        return
    out = await run_memory_llm(
        provider,
        prompt_file="conversation-summary.md",
        user_payload=transcript_excerpt,
        settings=st,
    )
    if out:
        metadata["conversation_summary"] = out


async def maybe_update_session_notes(
    provider: Any,
    metadata: dict[str, Any],
    context_blob: str,
    settings: Settings | None = None,
) -> None:
    st = settings or get_settings()
    if not (st.memory_prompts_enabled and st.memory_session_notes_enabled):
        return
    out = await run_memory_llm(
        provider,
        prompt_file="session-notes.md",
        user_payload=context_blob,
        settings=st,
    )
    if out:
        try:
            metadata["session_notes"] = json.loads(out)
        except json.JSONDecodeError:
            metadata["session_notes"] = {"raw": out}


async def maybe_run_memory_extraction(
    provider: Any,
    metadata: dict[str, Any],
    dense_transcript: str,
    settings: Settings | None = None,
) -> None:
    st = settings or get_settings()
    if not (st.memory_prompts_enabled and st.memory_extraction_enabled):
        return
    out = await run_memory_llm(
        provider,
        prompt_file="memory-extraction.md",
        user_payload=dense_transcript,
        settings=st,
    )
    if not out:
        return
    try:
        parsed = json.loads(out)
        if isinstance(parsed, list):
            cur = metadata.get("extracted_memory")
            if not isinstance(cur, list):
                cur = []
            metadata["extracted_memory"] = cur + parsed
    except json.JSONDecodeError:
        pass
