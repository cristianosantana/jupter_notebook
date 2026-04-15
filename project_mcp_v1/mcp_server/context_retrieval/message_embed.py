"""
Embeddings por mensagem em ``conversation_message_embeddings`` (ingestão batch).

Usado pela tool MCP ``context_embed_messages`` e opcionalmente por ``scripts/embed_sessions_from_db.py``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from context_retrieval.embedder import embed_texts_batched
from context_retrieval.pool import get_pg_pool
from context_retrieval.prefilter import load_messages_for_retrieve
from context_retrieval.repository import (
    fetch_message_embeddings,
    fetch_recent_messages,
    upsert_message_embeddings_batch,
)

_logger = logging.getLogger(__name__)


async def run_embed_messages_for_session(
    session_id: UUID,
    *,
    limit: int,
    anchor_query: str | None,
) -> dict[str, Any]:
    """
    Para ``session_id``, selecciona até ``limit`` mensagens (recentes ou via ILIKE se ``anchor_query``),
    gera embeddings em falta para ``context_embedding_model`` e faz UPSERT na tabela por mensagem.
    """
    from app.config import get_settings

    st = get_settings()
    model = (st.context_embedding_model or "text-embedding-3-small").strip()
    lim_cap = max(1, min(int(limit), 200))
    like_lim = max(1, min(int(st.context_like_prefilter_limit), 200))
    win = max(8, int(st.context_message_candidate_window))
    bs = max(1, min(int(st.context_message_embed_batch_size), 2048))

    try:
        pool = await get_pg_pool()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    async with pool.acquire() as conn:
        sess_ok = await conn.fetchval(
            "SELECT 1 FROM sessions WHERE session_id = $1",
            session_id,
        )
        if not sess_ok:
            return {"ok": False, "error": "sessão não encontrada"}

        anchor = (anchor_query or "").strip() or None
        if anchor:
            msgs, _, _mode = await load_messages_for_retrieve(
                conn,
                session_id,
                anchor,
                like_limit=like_lim,
                window_cap=min(win, lim_cap),
            )
            msgs = msgs[-lim_cap:] if len(msgs) > lim_cap else msgs
        else:
            msgs = await fetch_recent_messages(conn, session_id, max_messages=lim_cap)

        if not msgs:
            return {
                "ok": True,
                "embedded": 0,
                "skipped": 0,
                "model": model,
                "session_id": str(session_id),
            }

        ids = [int(m["id"]) for m in msgs]
        existing = await fetch_message_embeddings(conn, ids, model=model)

        to_compute: list[dict[str, Any]] = []
        for m in msgs:
            mid = int(m["id"])
            v = existing.get(mid)
            if v is None or len(v) < 1:
                to_compute.append(m)

        skipped = len(msgs) - len(to_compute)
        if not to_compute:
            return {
                "ok": True,
                "embedded": 0,
                "skipped": skipped,
                "model": model,
                "session_id": str(session_id),
            }

        texts = [f"{m['role']}: {m['content']}"[:6000] for m in to_compute]
        try:
            vecs = await embed_texts_batched(texts, model=model, batch_size=bs)
        except Exception as e:
            _logger.exception("run_embed_messages_for_session embed")
            return {"ok": False, "error": str(e)[:500], "model": model}

        if len(vecs) != len(to_compute):
            return {"ok": False, "error": "inconsistência embed/textos", "model": model}

        rows = [(int(m["id"]), session_id, model, vecs[i]) for i, m in enumerate(to_compute)]
        try:
            n = await upsert_message_embeddings_batch(conn, rows)
        except Exception as e:
            _logger.exception("run_embed_messages_for_session upsert")
            return {"ok": False, "error": str(e)[:500], "model": model}

        return {
            "ok": True,
            "embedded": len(to_compute),
            "skipped": skipped,
            "model": model,
            "session_id": str(session_id),
            "upserted": n,
        }
