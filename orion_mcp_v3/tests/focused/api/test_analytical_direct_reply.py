"""Resposta analítica directa — sem chamada ao narrador LLM."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from orion_mcp_v3.api.main import create_app
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST
from orion_mcp_v3.protocols.llm import (
    ChatMessage,
    LLMResponse,
    LLMResponseMeta,
    LLMStreamChunk,
)


class CountingLLMProvider:
    def __init__(self) -> None:
        self.chat_calls = 0

    async def generate(self, prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        return LLMResponse(text="{}", meta=LLMResponseMeta(model="fake"))

    async def chat(self, messages: list[ChatMessage], **kwargs):  # type: ignore[no-untyped-def]
        self.chat_calls += 1
        return LLMResponse(text="narrador não deveria ser chamado", meta=LLMResponseMeta(model="fake"))

    async def stream(self, messages: list[ChatMessage], **kwargs):  # type: ignore[no-untyped-def]
        self.chat_calls += 1
        yield LLMStreamChunk(delta="narrador stream", finish_reason="stop")


def _client(provider: CountingLLMProvider) -> TestClient:
    rows = [
        {
            "forma_pagamento": "pix",
            "qtd_recebimentos": 150,
            "total_recebido": 85000.0,
            "ticket_medio": 566.67,
            "percentual_total": 45.5,
        },
    ]
    mysql = MagicMock()
    mysql.select = AsyncMock(return_value=rows)
    executor = AnalyticsExecutor(mysql, ANALYTICS_ALLOWLIST, default_limit=1000)
    app = create_app(
        llm_provider=provider,
        analytics_executor=executor,
        analytics_allowlist=ANALYTICS_ALLOWLIST,
    )
    return TestClient(app)


def test_analytical_with_evidence_skips_narrator_llm_call() -> None:
    provider = CountingLLMProvider()
    client = _client(provider)

    r = client.post(
        "/api/v1/chat",
        json={"message": "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["model"] == "direct_evidence"
    assert "direct_evidence_reply" in body["meta"]["safeguards"]
    assert body["reply"] != "narrador não deveria ser chamado"
    assert body["reply"].strip()


def test_conversational_still_uses_narrator() -> None:
    provider = CountingLLMProvider()
    client = _client(provider)

    r = client.post("/api/v1/chat", json={"message": "olá, como você pode ajudar?"})

    assert r.status_code == 200
    assert r.json()["reply"] == "narrador não deveria ser chamado"
    assert r.json()["meta"]["model"] != "direct_evidence"
