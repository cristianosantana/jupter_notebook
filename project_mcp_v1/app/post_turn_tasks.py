"""
Pós-processamento de turno (memória, observador, índice de contexto) fora do caminho crítico HTTP.

Corre após a resposta ao cliente (FastAPI BackgroundTasks) com ``asyncio.gather`` onde seguro.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.agent_trace import llm_phase_context
from app.config import Settings, get_settings
from app.context_index_service import maybe_run_sync_context_index_refresh
from app.memory_prompts import (
    maybe_update_conversation_summary,
    maybe_update_session_notes,
)
from app.session_store import SessionStore
from mcp_client.client import Client

_logger = logging.getLogger(__name__)


def merge_post_turn_metadata_from_db_row(
    session_metadata: dict[str, Any],
    db_row: dict[str, Any] | None,
) -> None:
    """
    Evita que ``update_session_metadata`` apague chaves escritas em background no turno anterior.

    Copia de ``sessions.metadata`` (se existir) para o dict in-memory: ``conversation_summary``,
    ``session_notes``, e ``observer_log.narratives`` quando o DB tiver mais conteúdo que o local.
    """
    if not db_row:
        return
    raw = db_row.get("metadata")
    dbm = dict(raw) if isinstance(raw, dict) else {}
    if not dbm:
        return
    for k in ("conversation_summary", "session_notes"):
        if k in dbm:
            session_metadata[k] = copy.deepcopy(dbm[k])
    db_ol = dbm.get("observer_log")
    if not isinstance(db_ol, dict):
        return
    loc_ol = session_metadata.setdefault("observer_log", {})
    if not isinstance(loc_ol, dict):
        session_metadata["observer_log"] = copy.deepcopy(db_ol)
        return
    db_narr = db_ol.get("narratives")
    loc_narr = loc_ol.get("narratives")
    if isinstance(db_narr, list) and (
        not isinstance(loc_narr, list) or len(db_narr) > len(loc_narr)
    ):
        loc_ol["narratives"] = copy.deepcopy(db_narr)


async def run_observer_narrative_to_metadata(
    *,
    model: Any,
    metadata: dict[str, Any],
    user_input: str,
    tools_used: list[dict[str, Any]],
    agent_final: str,
    settings: Settings,
) -> None:
    if not settings.observer_agent_enabled:
        return
    path = Path(__file__).resolve().parent / "prompts" / "internal" / "observer.md"
    if not path.is_file():
        return
    system = path.read_text(encoding="utf-8").strip()
    payload = {
        "user_excerpt": user_input[:2000],
        "agent_final": agent_final,
        "tools_used": tools_used[-40:],
        "observer_events": (metadata.get("observer_log") or {}).get("entries", [])[-80:],
    }
    user = json.dumps(payload, ensure_ascii=False)[:120_000]
    model_o = (settings.observer_agent_model or "").strip() or None
    try:
        with llm_phase_context("observer_narrative"):
            resp = await model.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=None,
                model_override=model_o,
            )
        text = str((resp or {}).get("content") or "").strip()
        if not text:
            return
        cap = max(500, int(settings.observer_narrative_max_chars))
        if len(text) > cap:
            text = text[:cap] + "…"
        slot = metadata.setdefault("observer_log", {})
        narr = slot.setdefault("narratives", [])
        narr.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "markdown": text,
            }
        )
        nmax = max(1, int(settings.observer_narratives_max))
        if len(narr) > nmax:
            del narr[0 : len(narr) - nmax]
    except Exception as e:
        _logger.warning("observer narrative (background) failed: %s", e)


def _log_gather_result(name: str, result: Any) -> None:
    if isinstance(result, Exception):
        _logger.warning("post-turn task %s failed: %s", name, result, exc_info=result)


async def run_all_post_turn_work(
    *,
    store: SessionStore,
    mcp_client: Client,
    session_id: UUID,
    model: Any,
    metadata_snapshot: dict[str, Any],
    user_input: str,
    tools_used: list[dict[str, Any]],
    agent_final: str,
    transcript_excerpt: str,
    settings: Settings | None = None,
) -> None:
    """
    Memória (2 LLMs) + observador + refresh de índice em paralelo; depois ``merge_session_metadata``.
    """
    st = settings or get_settings()
    md = copy.deepcopy(metadata_snapshot)

    excerpt = (transcript_excerpt or "").strip() or user_input[:2000]

    async def _notes() -> None:
        await maybe_update_session_notes(
            model,
            md,
            json.dumps(
                {"last_agent": agent_final, "user_excerpt": user_input[:1200]},
                ensure_ascii=False,
            ),
            st,
        )

    async def _summary() -> None:
        await maybe_update_conversation_summary(model, md, excerpt, st)

    async def _obs() -> None:
        await run_observer_narrative_to_metadata(
            model=model,
            metadata=md,
            user_input=user_input,
            tools_used=list(tools_used),
            agent_final=agent_final,
            settings=st,
        )

    async def _index() -> None:
        await maybe_run_sync_context_index_refresh(
            store,
            mcp_client,
            str(session_id),
            settings=st,
        )

    results = await asyncio.gather(
        _notes(),
        _summary(),
        _obs(),
        _index(),
        return_exceptions=True,
    )
    for name, res in zip(("session_notes", "conversation_summary", "observer", "index"), results):
        _log_gather_result(name, res)

    patch: dict[str, Any] = {}
    if "conversation_summary" in md:
        patch["conversation_summary"] = md["conversation_summary"]
    if "session_notes" in md:
        patch["session_notes"] = md["session_notes"]
    if "observer_log" in md:
        patch["observer_log"] = md["observer_log"]
    if patch:
        try:
            await store.merge_session_metadata(session_id, patch)
        except Exception as e:
            _logger.warning("merge_session_metadata after post-turn: %s", e)
