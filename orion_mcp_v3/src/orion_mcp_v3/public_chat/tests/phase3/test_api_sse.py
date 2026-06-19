from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from orion_mcp_v3.public_chat.api.routes import create_public_ask_router
from orion_mcp_v3.public_chat.application.consulta_turn_runner import ConsultaTurnRunner, TurnResult
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings
from orion_mcp_v3.public_chat.domain.errors import InvalidParentQuestionError
from orion_mcp_v3.public_chat.integration.fastapi import mount_public_chat


@pytest.mark.asyncio
async def test_api_returns_assembled_json() -> None:
    question_id = uuid4()
    thread_id = uuid4()
    response_id = uuid4()

    runner = AsyncMock(spec=ConsultaTurnRunner)
    runner.run_turn_with_metadata.return_value = (
        TurnResult(
            question_id=question_id,
            thread_id=thread_id,
            parent_question_id=None,
            topic="geral",
            semantic_hash="abc",
            response_id=response_id,
            presentation_delivered="Olá, resposta completa.",
            cached=False,
        ),
        "Olá, resposta completa.",
    )

    async def _resolve_runner():
        return runner

    app = FastAPI()
    app.include_router(
        create_public_ask_router(_resolve_runner),
        prefix="/api/v1",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/public/ask",
            json={"message": "oi"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["message"] == "Olá, resposta completa."
    assert body["cached"] is False
    assert body["question_id"] == str(question_id)
    runner.run_turn_with_metadata.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_disabled_503(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_CHAT_ENABLED", "false")
    monkeypatch.delenv("PUBLIC_CHAT_POSTGRES_URL", raising=False)
    monkeypatch.delenv("PUBLIC_CHAT_LLM_API_KEY", raising=False)

    app = FastAPI()
    state: dict = {}
    mount_public_chat(app, shared_state=state, llm_provider=None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/public/ask",
            json={"message": "oi"},
        )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_invalid_parent_question_400() -> None:
    runner = AsyncMock(spec=ConsultaTurnRunner)
    runner.run_turn_with_metadata.side_effect = InvalidParentQuestionError("missing-parent")

    async def _resolve_runner():
        return runner

    app = FastAPI()
    app.include_router(
        create_public_ask_router(_resolve_runner),
        prefix="/api/v1",
    )

    parent_id = str(uuid4())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/public/ask",
            json={"message": "follow-up", "parent_question_id": parent_id},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_enabled_with_injected_runner() -> None:
    question_id = uuid4()
    thread_id = uuid4()
    response_id = uuid4()

    runner = AsyncMock(spec=ConsultaTurnRunner)
    runner.run_turn_with_metadata.return_value = (
        TurnResult(
            question_id=question_id,
            thread_id=thread_id,
            parent_question_id=None,
            topic="geral",
            semantic_hash="h",
            response_id=response_id,
            presentation_delivered="Resposta.",
            cached=True,
        ),
        "Resposta.",
    )

    app = FastAPI()
    state = {
        "public_chat_settings": PublicChatSettings(
            enabled=True,
            postgres_url="postgresql://x",
            llm_api_key="sk-test",
            embedding_api_key="sk-test",
        ),
        "public_chat_runner": runner,
    }
    mount_public_chat(app, shared_state=state, llm_provider=None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/public/ask",
            json={"message": "oi"},
        )

    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert response.json()["message"] == "Resposta."
