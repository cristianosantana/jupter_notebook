"""Fase 6 — API de produto: session manager, FastAPI chat endpoint, SSE streaming."""

from __future__ import annotations

import json
from collections.abc import Sequence

from fastapi.testclient import TestClient

from orion_mcp_v3.api.main import create_app
from orion_mcp_v3.api.models import ChatRequest, ChatResponse, HealthResponse
from orion_mcp_v3.api.email_sender import EmailSendResult
from orion_mcp_v3.protocols.llm import (
    ChatMessage,
    EchoLLMProvider,
    LLMResponse,
    LLMResponseMeta,
    LLMStreamChunk,
    NullLLMProvider,
)
from orion_mcp_v3.runtime import Session, SessionManager
from orion_mcp_v3.runtime.context_state import CognitivePhase


# ── 6.2 Session Manager ─────────────────────────────────────────────


def test_session_manager_creates_session_with_uuid() -> None:
    sm = SessionManager()
    s = sm.get_or_create()
    assert s.conversation_id
    assert len(s.conversation_id) > 10


def test_session_manager_get_same_id() -> None:
    sm = SessionManager()
    s1 = sm.get_or_create("abc")
    s2 = sm.get_or_create("abc")
    assert s1 is s2


async def test_session_manager_record_user_message() -> None:
    sm = SessionManager()
    s = sm.get_or_create("s1")
    msg = await sm.record_user_message(s, "olá")
    assert msg.content == "olá"
    assert msg.role == "user"
    assert s.turn_count == 1
    assert s.state.cognitive_phase == CognitivePhase.RETRIEVING


async def test_session_manager_record_assistant_message() -> None:
    sm = SessionManager()
    s = sm.get_or_create("s1")
    await sm.record_user_message(s, "olá")
    await sm.record_assistant_message(s, "oi!")
    assert s.state.cognitive_phase == CognitivePhase.IDLE
    msgs = await sm.get_recent_messages(s)
    assert len(msgs) == 2


async def test_session_manager_memory_window() -> None:
    sm = SessionManager(memory_window=2)
    s = sm.get_or_create("s1")
    for i in range(5):
        await sm.record_user_message(s, f"msg {i}")
    recent = await sm.get_recent_messages(s)
    assert len(recent) == 2


async def test_session_manager_list_sessions() -> None:
    sm = SessionManager()
    sm.get_or_create("a")
    sm.get_or_create("b")
    assert set(sm.list_sessions()) == {"a", "b"}


def test_session_update_phase() -> None:
    sm = SessionManager()
    s = sm.get_or_create("x")
    sm.update_phase(s, CognitivePhase.NARRATING)
    assert s.state.cognitive_phase == CognitivePhase.NARRATING


# ── 6.1 FastAPI ──────────────────────────────────────────────────────


def _make_client(provider=None) -> TestClient:
    app = create_app(llm_provider=provider or NullLLMProvider())
    return TestClient(app)


class FakeEmailSender:
    def __init__(self, result: EmailSendResult | None = None) -> None:
        self.calls = []
        self.result = result or EmailSendResult(status="sent", to="destino@local.test", message="enviado")

    async def send_response(self, request):  # type: ignore[no-untyped-def]
        self.calls.append(request)
        return self.result


class IntentThenNarrationProvider:
    def __init__(self) -> None:
        self.chat_calls = 0

    async def generate(self, prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        return LLMResponse(text="narrativa ok", meta=LLMResponseMeta(model="fake"))

    async def chat(self, messages: Sequence[ChatMessage], **kwargs):  # type: ignore[no-untyped-def]
        self.chat_calls += 1
        if self.chat_calls == 1:
            return LLMResponse(
                text=json.dumps(
                    {
                        "intent_type": "comparative",
                        "operation": "delta",
                        "needs_analytics": True,
                        "needs_memory": True,
                        "needs_comparison": True,
                        "metric": "sales",
                        "dimension": "seller",
                        "date_ranges": [
                            {
                                "label": "março",
                                "date_from": "2026-03-01",
                                "date_to": "2026-03-31",
                            },
                            {
                                "label": "abril",
                                "date_from": "2026-04-01",
                                "date_to": "2026-04-30",
                            },
                        ],
                        "source_periods": "explicit",
                        "inherits_from_previous": [],
                        "confidence": 0.92,
                    }
                ),
                meta=LLMResponseMeta(model="fake"),
            )
        return LLMResponse(text="narrativa ok", meta=LLMResponseMeta(model="fake"))

    async def stream(self, messages: Sequence[ChatMessage], **kwargs):  # type: ignore[no-untyped-def]
        yield LLMStreamChunk(delta="narrativa ok", finish_reason="stop")


def test_health_endpoint() -> None:
    client = _make_client()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_chat_options_endpoint() -> None:
    client = _make_client()
    r = client.get("/api/v1/chat/options")
    assert r.status_code == 200
    j = r.json()
    assert "policies" in j and "analytical" in j["policies"]
    assert j["max_tokens_min"] == 64
    assert j["max_tokens_max"] == 32000
    assert isinstance(j["max_tokens_presets"], list)


def test_sessions_list_endpoint() -> None:
    client = _make_client(NullLLMProvider())
    assert client.get("/api/v1/sessions").json()["sessions"] == []
    client.post("/api/v1/chat", json={"message": "olá lista", "conversation_id": "sess-api-list"})
    rows = client.get("/api/v1/sessions").json()["sessions"]
    assert any(s["conversation_id"] == "sess-api-list" for s in rows)
    row = next(s for s in rows if s["conversation_id"] == "sess-api-list")
    assert "messages" in row
    assert isinstance(row["messages"], list)
    assert len(row["messages"]) >= 2
    assert row["messages"][0]["role"] == "user"
    assert row["messages"][0]["content"] == "olá lista"
    assert "message_id" in row["messages"][0]
    assert "created_at" in row["messages"][0]


def test_chat_first_message_with_null_conversation_id() -> None:
    client = _make_client(NullLLMProvider(fixed_response="ok"))
    r = client.post("/api/v1/chat", json={"message": "primeira", "conversation_id": None})
    assert r.status_code == 200
    cid = r.json()["meta"]["conversation_id"]
    assert cid
    r2 = client.post("/api/v1/chat", json={"message": "segunda", "conversation_id": cid})
    assert r2.json()["meta"]["conversation_id"] == cid


def test_chat_endpoint_basic() -> None:
    client = _make_client(NullLLMProvider(fixed_response="resposta fixa"))
    r = client.post("/api/v1/chat", json={"message": "olá"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "resposta fixa"
    assert "meta" in body
    assert body["meta"]["conversation_id"]
    assert body["meta"]["finish_reason"]
    assert "safeguards" in body["meta"]


def test_chat_endpoint_with_conversation_id() -> None:
    client = _make_client(NullLLMProvider())
    r1 = client.post("/api/v1/chat", json={"message": "hi", "conversation_id": "my-session"})
    assert r1.status_code == 200
    assert r1.json()["meta"]["conversation_id"] == "my-session"
    r2 = client.post("/api/v1/chat", json={"message": "hi again", "conversation_id": "my-session"})
    assert r2.json()["meta"]["conversation_id"] == "my-session"


def test_chat_endpoint_with_echo_provider() -> None:
    client = _make_client(EchoLLMProvider())
    r = client.post("/api/v1/chat", json={"message": "faturamento dos clientes"})
    assert r.status_code == 200
    assert "faturamento" in r.json()["reply"].lower() or "Echo" in r.json()["reply"]


def test_chat_endpoint_analytical_policy() -> None:
    client = _make_client(NullLLMProvider())
    r = client.post("/api/v1/chat", json={"message": "top vendas", "policy": "analytical"})
    assert r.status_code == 200


def test_chat_endpoint_returns_cognitive_intent() -> None:
    client = _make_client(NullLLMProvider())
    r = client.post("/api/v1/chat", json={"message": "mostre o faturamento total"})
    assert r.status_code == 200
    meta = r.json()["meta"]
    assert meta["cognitive_intent"] is not None


def test_chat_uses_llm_intent_contract_when_valid() -> None:
    provider = IntentThenNarrationProvider()
    client = _make_client(provider)

    r = client.post(
        "/api/v1/chat",
        json={
            "message": "faça uma comparação entre março e abril de 2026 por vendedor",
            "policy": "analytical",
        },
    )

    assert r.status_code == 200
    assert r.json()["meta"]["cognitive_intent"] == "comparative"
    assert provider.chat_calls >= 2


def test_chat_endpoint_invalid_message() -> None:
    client = _make_client()
    r = client.post("/api/v1/chat", json={"message": ""})
    assert r.status_code == 422


def test_chat_endpoint_sse_streaming() -> None:
    client = _make_client(EchoLLMProvider())
    r = client.post(
        "/api/v1/chat",
        json={"message": "dados de vendas", "stream": True},
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")

    events = []
    for line in r.text.split("\n"):
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            events.append(payload)

    assert len(events) >= 2
    deltas = [e.get("delta", "") for e in events if "delta" in e]
    assert any(d for d in deltas)
    done_events = [e for e in events if e.get("done")]
    assert len(done_events) == 1
    assert done_events[0]["conversation_id"]


def test_chat_endpoint_sse_streaming_sends_email_after_stream() -> None:
    sender = FakeEmailSender()
    app = create_app(llm_provider=EchoLLMProvider(), email_sender=sender)
    client = TestClient(app)

    r = client.post(
        "/api/v1/chat",
        json={"message": "dados de vendas", "stream": True, "email_to": "destino@local.test"},
    )

    assert r.status_code == 200
    events = [json.loads(line[6:]) for line in r.text.split("\n") if line.startswith("data: ")]
    deltas = [e.get("delta", "") for e in events if "delta" in e]
    done = next(e for e in events if e.get("done"))

    assert len(sender.calls) == 1
    assert sender.calls[0].to == "destino@local.test"
    assert sender.calls[0].body == "".join(deltas)
    assert done["email_delivery"]["status"] == "sent"


def test_chat_response_model_structure() -> None:
    req = ChatRequest(message="teste")
    assert req.message == "teste"
    assert req.stream is False
    assert req.policy == "balanced"
    assert req.email_to is None
    assert req.email_subject is None


def test_chat_without_email_to_does_not_send_email() -> None:
    sender = FakeEmailSender()
    app = create_app(llm_provider=NullLLMProvider(fixed_response="resposta fixa"), email_sender=sender)
    client = TestClient(app)

    r = client.post("/api/v1/chat", json={"message": "olá"})

    assert r.status_code == 200
    assert sender.calls == []
    assert r.json()["meta"]["email_delivery"]["status"] == "not_requested"


def test_chat_with_email_to_sends_response_email() -> None:
    sender = FakeEmailSender()
    app = create_app(llm_provider=NullLLMProvider(fixed_response="resposta fixa"), email_sender=sender)
    client = TestClient(app)

    r = client.post(
        "/api/v1/chat",
        json={
            "message": "olá",
            "email_to": "destino@local.test",
            "email_subject": "Minha resposta",
        },
    )

    assert r.status_code == 200
    assert len(sender.calls) == 1
    assert sender.calls[0].to == "destino@local.test"
    assert sender.calls[0].subject == "Minha resposta"
    assert sender.calls[0].body == "resposta fixa"
    assert r.json()["meta"]["email_delivery"]["status"] == "sent"


def test_chat_email_failure_does_not_fail_chat_response() -> None:
    sender = FakeEmailSender(EmailSendResult(status="failed", to="destino@local.test", message="falha smtp"))
    app = create_app(llm_provider=NullLLMProvider(fixed_response="resposta fixa"), email_sender=sender)
    client = TestClient(app)

    r = client.post(
        "/api/v1/chat",
        json={"message": "olá", "email_to": "destino@local.test"},
    )

    assert r.status_code == 200
    assert r.json()["reply"] == "resposta fixa"
    assert r.json()["meta"]["email_delivery"]["status"] == "failed"


# ── 6.1+ Analytics pipeline na rota de chat ──────────────────────────


def _make_client_with_analytics(
    provider=None,
    mock_rows: list | None = None,
) -> TestClient:
    from unittest.mock import AsyncMock, MagicMock

    from orion_mcp_v3.broker.executor import AnalyticsExecutor
    from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST

    rows = mock_rows or [
        {"forma_pagamento": "pix", "qtd_recebimentos": 150, "total_recebido": 85000.0, "ticket_medio": 566.67, "percentual_total": 45.5},
        {"forma_pagamento": "cartao credito", "qtd_recebimentos": 100, "total_recebido": 62000.0, "ticket_medio": 620.0, "percentual_total": 33.2},
    ]
    mysql = MagicMock()
    mysql.select = AsyncMock(return_value=rows)
    executor = AnalyticsExecutor(mysql, ANALYTICS_ALLOWLIST, default_limit=1000)

    app = create_app(
        llm_provider=provider or EchoLLMProvider(),
        analytics_executor=executor,
        analytics_allowlist=ANALYTICS_ALLOWLIST,
    )
    return TestClient(app)


def test_chat_analytical_with_evidence() -> None:
    client = _make_client_with_analytics()
    r = client.post(
        "/api/v1/chat",
        json={"message": "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"},
    )
    assert r.status_code == 200
    body = r.json()
    meta = body["meta"]
    safeguards = meta.get("safeguards", [])
    assert "no_evidence" not in safeguards, (
        f"Resposta não deveria ter 'no_evidence' nos safeguards: {safeguards}"
    )
    assert "no_coverage_data" not in safeguards, (
        f"Com evidência no prompt, não deveria haver 'no_coverage_data': {safeguards}"
    )
    assert "evidence_cited" in safeguards
    assert "coverage_note_injected" in safeguards


def test_chat_analytical_without_executor() -> None:
    client = _make_client(NullLLMProvider())
    r = client.post(
        "/api/v1/chat",
        json={"message": "Qual forma de pagamento domina o faturamento?"},
    )
    assert r.status_code == 200


def test_chat_forma_pagamento_sem_palavra_faturamento_com_executor_injectado() -> None:
    """Regressão: intenção analítica sem keyword 'faturamento' + broker activo."""
    client = _make_client_with_analytics()
    r = client.post(
        "/api/v1/chat",
        json={"message": "Qual forma de pagamento domina entre janeiro e abril de 2026?"},
    )
    assert r.status_code == 200
    assert "no_evidence" not in r.json()["meta"].get("safeguards", [])
