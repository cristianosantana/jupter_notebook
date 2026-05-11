from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.llm.provider import MockLLMProvider, OpenAILLMProvider


@pytest.mark.asyncio
async def test_mock_generate_stream_yields_chunks() -> None:
    llm = MockLLMProvider()
    chunks: list[str] = []
    async for c in llm.generate_stream("hello world", model="m", temperature=0.0, max_tokens=10):
        chunks.append(c)
    assert len(chunks) == 3
    assert "".join(chunks).startswith("[mock:m]")


@pytest.mark.asyncio
async def test_mock_generate_stream_prefixes_system_when_set() -> None:
    llm = MockLLMProvider()
    chunks: list[str] = []
    async for c in llm.generate_stream(
        "hi",
        model="m",
        temperature=0.0,
        max_tokens=10,
        system_prompt="Sys Orion",
    ):
        chunks.append(c)
    joined = "".join(chunks)
    assert "[system]" in joined
    assert "Sys Orion" in joined
    assert "[mock:m]" in joined


@pytest.mark.asyncio
async def test_mock_generate_equals_join_stream() -> None:
    llm = MockLLMProvider()
    full = await llm.generate("abc" * 100, model="x", temperature=0.1, max_tokens=50)
    parts: list[str] = []
    async for c in llm.generate_stream("abc" * 100, model="x", temperature=0.1, max_tokens=50):
        parts.append(c)
    assert full == "".join(parts)


@pytest.mark.asyncio
async def test_openai_generate_stream_yields_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stream OpenAI simulado: apenas deltas de texto."""

    class _Delta:
        def __init__(self, content: str | None) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str | None) -> None:
            self.delta = _Delta(content)

    class _Chunk:
        def __init__(self, content: str | None) -> None:
            self.choices = [_Choice(content)] if content is not None else []

    async def fake_stream() -> Any:
        yield _Chunk("Hel")
        yield _Chunk("lo")

    mock_create = AsyncMock(return_value=fake_stream())
    client = MagicMock()
    client.chat.completions.create = mock_create
    settings = Settings(openai_api_key="sk-test")
    llm = OpenAILLMProvider(client, settings)  # type: ignore[arg-type]

    out: list[str] = []
    async for d in llm.generate_stream(
        "p",
        model="gpt-test",
        temperature=0.2,
        max_tokens=8,
        system_prompt="Tu és o Orion.",
    ):
        out.append(d)

    assert out == ["Hel", "lo"]
    mock_create.assert_awaited()
    kwargs = mock_create.await_args.kwargs
    assert kwargs.get("stream") is True
    msgs = kwargs.get("messages") or []
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "Orion" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "p"}


@pytest.mark.asyncio
async def test_openai_generate_stream_user_only_without_system(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Delta:
        def __init__(self, content: str | None) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str | None) -> None:
            self.delta = _Delta(content)

    class _Chunk:
        def __init__(self, content: str | None) -> None:
            self.choices = [_Choice(content)] if content is not None else []

    async def fake_stream() -> Any:
        yield _Chunk("x")

    mock_create = AsyncMock(return_value=fake_stream())
    client = MagicMock()
    client.chat.completions.create = mock_create
    settings = Settings(openai_api_key="sk-test")
    llm = OpenAILLMProvider(client, settings)  # type: ignore[arg-type]

    out: list[str] = []
    async for d in llm.generate_stream("only-user", model="gpt-test", temperature=0.2, max_tokens=8):
        out.append(d)
    assert out == ["x"]
    msgs = mock_create.await_args.kwargs.get("messages") or []
    assert msgs == [{"role": "user", "content": "only-user"}]
