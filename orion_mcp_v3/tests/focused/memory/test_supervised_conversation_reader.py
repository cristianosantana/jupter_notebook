from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from orion_mcp_v3.memory.supervised_conversation_reader import SupervisedConversationReader


@pytest.mark.asyncio
async def test_reader_reads_conversation_state_and_turn_embeddings_without_writes() -> None:
    start = datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc)

    conn = AsyncMock()
    conn.fetch.return_value = [
        {
            "session_id": "sess-1",
            "user_id": "sistema_background",
            "messages": [
                {"role": "user", "content": "Qual foi o faturamento?"},
                {"role": "assistant", "content": "Faturamento validado."},
            ],
            "indexed_turns": [
                {
                    "message_id": "sess-1:1",
                    "role": "user",
                    "content": "Qual foi o faturamento?",
                    "created_at": "2026-06-09T12:00:00+00:00",
                }
            ],
        }
    ]
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    windows = await SupervisedConversationReader(pool).read_window(start, end, limit=50)

    assert len(windows) == 1
    assert windows[0].session_id == "sess-1"
    assert windows[0].messages[0]["content"] == "Qual foi o faturamento?"
    assert windows[0].indexed_turns[0]["message_id"] == "sess-1:1"
    conn.fetch.assert_awaited_once()
    sql = conn.fetch.await_args.args[0].upper()
    assert "SELECT" in sql
    assert "CONVERSATION_STATE" in sql
    assert "CHAT_TURN_EMBEDDINGS" in sql
    assert "CS.CREATED_AT >= $1" in sql
    assert "CS.DISTILLED_AT IS NULL" in sql
    assert "INSERT" not in sql
    assert "UPDATE" not in sql
    assert "DELETE" not in sql
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_reader_decodes_jsonb_returned_as_text() -> None:
    start = datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc)

    conn = AsyncMock()
    conn.fetch.return_value = [
        {
            "session_id": "sess-json",
            "user_id": "sistema_background",
            "messages": json.dumps(
                [
                    {"role": "user", "content": "Faca o fechamento gerencial"},
                    {"role": "assistant", "content": "Fechamento validado."},
                ]
            ),
            "indexed_turns": json.dumps(
                [
                    {
                        "message_id": "sess-json:1",
                        "role": "user",
                        "content": "Faca o fechamento gerencial",
                    }
                ]
            ),
        }
    ]
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    windows = await SupervisedConversationReader(pool).read_window(start, end)

    assert windows[0].messages[0]["content"] == "Faca o fechamento gerencial"
    assert windows[0].messages[1]["content"] == "Fechamento validado."
    assert windows[0].indexed_turns[0]["message_id"] == "sess-json:1"


@pytest.mark.asyncio
async def test_reader_marks_windows_as_distilled_after_successful_persist() -> None:
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    await SupervisedConversationReader(pool).mark_processed(
        [
            MagicMock(session_id="2941564f-8d3a-4d71-81c7-ea6cb6d2c306"),
            MagicMock(session_id="8b92a387-bba5-4653-9899-1d7c2e902891"),
        ]
    )

    conn.execute.assert_awaited_once()
    sql = conn.execute.await_args.args[0].upper()
    assert "UPDATE" in sql
    assert "CONVERSATION_STATE" in sql
    assert "DISTILLED_AT = NOW()" in sql
    assert conn.execute.await_args.args[1] == [
        "2941564f-8d3a-4d71-81c7-ea6cb6d2c306",
        "8b92a387-bba5-4653-9899-1d7c2e902891",
    ]
