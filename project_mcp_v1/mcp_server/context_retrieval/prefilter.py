"""ILIKE primeiro, depois embeddings só sobre candidatos (B2b)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from context_retrieval.like_pattern import question_to_ilike_pattern
from context_retrieval.repository import fetch_recent_messages, ilike_candidate_messages


async def load_messages_for_retrieve(
    conn: asyncpg.Connection,
    session_id: UUID,
    query: str,
    *,
    like_limit: int,
    window_cap: int,
) -> tuple[list[dict[str, Any]], int, str]:
    """
    Devolve mensagens candidatas: primeiro ILIKE sobre ``query``; se vazio, fallback
    às últimas ``min(12, window_cap)`` mensagens por ordem temporal.
    """
    pattern = question_to_ilike_pattern(query)
    raw = await ilike_candidate_messages(
        conn, session_id, pattern=pattern, limit=like_limit
    )
    if raw:
        ordered = list(reversed(raw))
        msgs: list[dict[str, Any]] = [
            {"id": int(x["id"]), "role": x["role"], "content": str(x.get("content") or "")}
            for x in ordered
        ]
        return msgs, len(msgs), "ilike"
    fb = max(4, min(12, int(window_cap)))
    msgs = await fetch_recent_messages(conn, session_id, max_messages=fb)
    return msgs, 0, "fallback"
