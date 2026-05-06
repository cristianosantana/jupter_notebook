"""Testes unitários de resolve_chat_identity."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from orion_mcp_v2.route.chat_context import resolve_chat_identity
from orion_mcp_v2.state.models import ConversationStateV2


@pytest.mark.asyncio
async def test_resolve_generates_both_when_missing() -> None:
    repo = AsyncMock()
    repo.load = AsyncMock(return_value=None)
    sid, uid = await resolve_chat_identity(repo, session_id=None, user_id=None)
    assert len(sid) == 36
    assert len(uid) == 36


@pytest.mark.asyncio
async def test_resolve_user_from_existing_state() -> None:
    state = ConversationStateV2(session_id="sess-known", user_id="user-persisted", messages=[])
    repo = AsyncMock()
    repo.load = AsyncMock(return_value=state)
    sid, uid = await resolve_chat_identity(repo, session_id="sess-known", user_id=None)
    assert sid == "sess-known"
    assert uid == "user-persisted"


@pytest.mark.asyncio
async def test_resolve_explicit_user_without_session() -> None:
    repo = AsyncMock()
    repo.load = AsyncMock(return_value=None)
    sid, uid = await resolve_chat_identity(repo, session_id=None, user_id="fixed-user")
    assert len(sid) == 36
    assert uid == "fixed-user"
