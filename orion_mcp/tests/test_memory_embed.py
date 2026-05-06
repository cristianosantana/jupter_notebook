from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion_mcp.core.config.settings import Settings, get_settings
from orion_mcp.core.memory.embed_pipeline import run_embed_and_insert
from orion_mcp.core.memory.index_queue import (
    build_memory_index_content,
    build_memory_index_metadata,
    enqueue_memory_embed,
    maybe_enqueue_memory_index_after_chat,
)
from orion_mcp.core.state.models import State


def test_build_memory_index_content_user_only() -> None:
    assert build_memory_index_content("hello", None) == "hello"


def test_build_memory_index_content_with_reply() -> None:
    c = build_memory_index_content("u", "r")
    assert "u" in c and "[resposta]" in c and "r" in c


def test_build_memory_index_metadata() -> None:
    s = State(intent="general", current_metric="m1", entities={"quoted": ["A"]})
    m = build_memory_index_metadata(s)
    assert m["intent"] == "general" and m["metric"] == "m1" and m["entity"] == "A"


@pytest.mark.asyncio
async def test_run_embed_and_insert_inserts_row() -> None:
    get_settings.cache_clear()
    settings = Settings(
        openai_api_key="sk-test",
        database_url="postgresql://u:p@127.0.0.1:9/db",
        embedding_dimensions=256,
        enable_long_memory=True,
    )
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()

    with (
        patch("orion_mcp.core.memory.embed_pipeline.embed_text", new_callable=AsyncMock) as emb,
        patch("orion_mcp.core.memory.embed_pipeline.asyncpg.connect", new_callable=AsyncMock) as connect,
    ):
        emb.return_value = [0.01] * 256
        connect.return_value = mock_conn
        await run_embed_and_insert(
            session_id="s1",
            content="texto a indexar",
            metadata={"source": "test"},
            settings=settings,
        )
    connect.assert_called_once()
    mock_conn.execute.assert_called_once()
    mock_conn.close.assert_called_once()


def test_enqueue_memory_embed_calls_delay() -> None:
    with patch("orion_mcp.infra.queue.celery_app.embed_memory_task") as t:
        t.delay = MagicMock()
        enqueue_memory_embed(session_id="sid", content="c", metadata={"k": 1})
        t.delay.assert_called_once_with(session_id="sid", content="c", metadata={"k": 1})


def test_maybe_enqueue_skips_without_long_memory() -> None:
    s = Settings(enable_long_memory=False, enable_memory_index_worker=True)
    with patch("orion_mcp.core.memory.index_queue.enqueue_memory_embed") as enq:
        maybe_enqueue_memory_index_after_chat(
            settings=s,
            pool=MagicMock(),
            session_id="x",
            state=State(),
            user_input="hi",
            assistant_text="bye",
        )
        enq.assert_not_called()


def test_maybe_enqueue_skips_without_pool() -> None:
    s = Settings(enable_long_memory=True, enable_memory_index_worker=True)
    with patch("orion_mcp.core.memory.index_queue.enqueue_memory_embed") as enq:
        maybe_enqueue_memory_index_after_chat(
            settings=s,
            pool=None,
            session_id="x",
            state=State(),
            user_input="hi",
            assistant_text="bye",
        )
        enq.assert_not_called()


class _FakeConn:
    async def fetch(self, *args: object, **kwargs: object) -> list:
        return []


class _FakePool:
    @asynccontextmanager
    async def acquire(self):
        yield _FakeConn()


@pytest.mark.asyncio
async def test_orchestrator_enqueues_after_generate_response() -> None:
    from orion_mcp.core.orchestrator.orchestrator import Orchestrator
    from orion_mcp.core.tools.registry import ToolRegistry
    from orion_mcp.infra.cache.tool_cache import MemoryToolCache
    from orion_mcp.infra.db.state_repository import MemoryStateRepository
    from orion_mcp.core.strategy import Strategy

    get_settings.cache_clear()
    settings = Settings(
        openai_api_key=None,
        enable_long_memory=True,
        enable_memory_index_worker=True,
    )
    repo = MemoryStateRepository()
    tools = ToolRegistry(settings, MemoryToolCache())
    pool = _FakePool()
    orch = Orchestrator.build(settings, repo, tools, pool=pool)
    with patch("orion_mcp.core.memory.index_queue.enqueue_memory_embed") as enq:
        r = await orch.handle_chat(
            session_id="sess1",
            user_input="preciso de dados",
            strategy=Strategy.fast,
        )
    assert r.payload.get("kind") == "chat"
    enq.assert_called_once()
    call_kw = enq.call_args.kwargs
    assert call_kw["session_id"] == "sess1"
    assert "preciso de dados" in call_kw["content"]
    assert call_kw["metadata"].get("source") == "chat_turn"
