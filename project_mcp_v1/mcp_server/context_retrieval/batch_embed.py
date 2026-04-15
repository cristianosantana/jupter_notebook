"""
Batch: gera embeddings por sessão a partir de ``conversation_messages`` (PostgreSQL).

Usado pela tool MCP ``context_embed_sessions`` e pelo script ``scripts/embed_sessions_from_db.py``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from context_retrieval.embedder import embed_texts
from context_retrieval.prefilter import load_messages_for_retrieve
from context_retrieval.pool import get_pg_pool
from context_retrieval.repository import (
    fetch_recent_messages,
    list_peer_sessions_anonymous,
    list_peer_sessions_for_user,
    resolve_user_id_for_session,
    upsert_session_embedding,
)

_logger = logging.getLogger(__name__)


def _aggregate_text_char_cap() -> int:
    """Tecto de caracteres na agregação (antes do trunc por tokens em ``embed_texts``)."""
    from app.config import get_settings

    st = get_settings()
    mt = max(256, int(st.context_embedding_max_input_tokens))
    return min(120_000, mt * 6)


async def _session_text_for_embed(
    conn: Any,
    session_id: UUID,
    max_messages: int,
) -> str:
    cap = _aggregate_text_char_cap()
    msgs = await fetch_recent_messages(conn, session_id, max_messages=max_messages)
    lines: list[str] = []
    for m in msgs[-max_messages:]:
        role = str(m.get("role") or "")
        c = str(m.get("content") or "").strip()
        if not c:
            continue
        lines.append(f"{role}: {c[:2000]}")
    return "\n".join(lines)[:cap]


async def run_embed_sessions_for_anchor_session(
    anchor_session_id: UUID,
    *,
    limit: int,
    anchor_query: str | None = None,
) -> dict[str, Any]:
    """
    Para o mesmo utilizador (ou modo anónimo) que ``anchor_session_id``, selecciona até ``limit``
    sessões com mensagens, agrega texto, gera embeddings OpenAI e grava em ``session_embeddings``.

    ``anchor_query`` opcional: agrega só mensagens que passam ILIKE (como no retrieve online).
    """
    from app.config import get_settings

    st = get_settings()
    model = (st.context_embedding_model or "text-embedding-3-small").strip()
    lim = max(1, min(int(limit), int(st.context_embed_sessions_limit_default * 4)))
    max_msg = max(8, int(st.context_message_candidate_window))
    like_lim = max(1, min(int(st.context_like_prefilter_limit), 200))
    anchor = (anchor_query or "").strip() or None

    try:
        pool = await get_pg_pool()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    processed = 0
    async with pool.acquire() as conn:
        uid = await resolve_user_id_for_session(conn, anchor_session_id)
        if uid is None:
            targets = await list_peer_sessions_anonymous(conn, anchor_session_id, limit=lim)
        else:
            targets = await list_peer_sessions_for_user(conn, uid, limit=lim)
        if not targets:
            return {"ok": True, "embedded": 0, "embedding_model": model, "note": "sem sessões com mensagens"}

        texts: list[str] = []
        ids: list[UUID] = []
        for t in targets:
            if anchor:
                msgs, _, _mode = await load_messages_for_retrieve(
                    conn,
                    t,
                    anchor,
                    like_limit=like_lim,
                    window_cap=max_msg,
                )
                if msgs:
                    lines = [
                        f"{m['role']}: {str(m.get('content') or '')[:2000]}"
                        for m in msgs
                    ]
                    txt = "\n".join(lines)[: _aggregate_text_char_cap()]
                else:
                    txt = await _session_text_for_embed(conn, t, max_msg)
            else:
                txt = await _session_text_for_embed(conn, t, max_msg)
            if len(txt.strip()) < 8:
                continue
            texts.append(txt)
            ids.append(t)

        if not texts:
            return {"ok": True, "embedded": 0, "embedding_model": model, "note": "texto vazio"}

        try:
            vecs = await embed_texts(texts, model=model)
        except Exception as e:
            _logger.exception("run_embed_sessions_for_anchor_session embed")
            return {"ok": False, "error": str(e)[:500]}

        for i, sess in enumerate(ids):
            await upsert_session_embedding(
                conn,
                session_id=sess,
                model=model,
                embedding=vecs[i],
                text_digest=texts[i][:2000],
            )
            processed += 1

    return {"ok": True, "embedded": processed, "embedding_model": model}
