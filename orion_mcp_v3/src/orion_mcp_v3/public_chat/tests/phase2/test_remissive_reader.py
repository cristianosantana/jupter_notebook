from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from orion_mcp_v3.public_chat.infrastructure import remissive_reader
from orion_mcp_v3.public_chat.infrastructure.remissive_reader import PublicRemissiveReader


def test_remissive_reader_global_sql_has_no_user_id_filter() -> None:
    source = inspect.getsource(remissive_reader)
    assert '"user_id"' not in source
    assert "ivfflat.probes" in source
    assert "memory_embeddings" in source


@pytest.mark.asyncio
async def test_remissive_reader_readonly() -> None:
    source = inspect.getsource(remissive_reader.PublicRemissiveReader)
    assert "INSERT" not in source
    assert "UPDATE" not in source
    assert "DELETE" not in source

    embed = AsyncMock()
    embed.embed.return_value = [[0.1, 0.2, 0.3]]
    conn = AsyncMock()
    conn.fetch.return_value = []
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = lambda: tx

    reader = PublicRemissiveReader(pool, embed, probes=10, limit=3)
    await reader.search_origin_ids("faturamento maio")

    execute_sql = str(conn.execute.await_args.args[0])
    assert "ivfflat.probes" in execute_sql
    fetch_sql = str(conn.fetch.await_args.args[0])
    assert "memory_embeddings" in fetch_sql
    assert "user_id" not in fetch_sql
