"""Resolução de session_id / user_id para o pedido de chat."""

from __future__ import annotations

import uuid

from orion_mcp_v2.state.repository import StateRepository


async def resolve_chat_identity(
    repo: StateRepository,
    *,
    session_id: str | None,
    user_id: str | None,
) -> tuple[str, str]:
    """
    - Sem session_id: nova sessão (UUID).
    - Com session_id e sem user_id: recupera user_id do estado persistido, senão novo UUID.
    - Com user_id: usa-o (sessão criada ou existente conforme session_id).
    """
    sid = session_id if session_id else str(uuid.uuid4())
    if user_id:
        return sid, user_id
    state = await repo.load(sid)
    if state is not None:
        return sid, state.user_id
    return sid, str(uuid.uuid4())
