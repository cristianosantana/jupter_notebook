"""Fase 6 — API de produto: session manager, FastAPI chat endpoint, SSE streaming."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from orion_mcp_v3.api.main import create_app
from orion_mcp_v3.api.models import ChatRequest, ChatResponse, HealthResponse
from orion_mcp_v3.protocols.llm import EchoLLMProvider, NullLLMProvider
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


def test_session_manager_record_user_message() -> None:
    sm = SessionManager()
    s = sm.get_or_create("s1")
    msg = sm.record_user_message(s, "olá")
    assert msg.content == "olá"
    assert msg.role == "user"
    assert s.turn_count == 1
    assert s.state.cognitive_phase == CognitivePhase.RETRIEVING


def test_session_manager_record_assistant_message() -> None:
    sm = SessionManager()
    s = sm.get_or_create("s1")
    sm.record_user_message(s, "olá")
    sm.record_assistant_message(s, "oi!")
    assert s.state.cognitive_phase == CognitivePhase.IDLE
    msgs = sm.get_recent_messages(s)
    assert len(msgs) == 2


def test_session_manager_memory_window() -> None:
    sm = SessionManager(memory_window=2)
    s = sm.get_or_create("s1")
    for i in range(5):
        sm.record_user_message(s, f"msg {i}")
    recent = sm.get_recent_messages(s)
    assert len(recent) == 2


def test_session_manager_list_sessions() -> None:
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


def test_health_endpoint() -> None:
    client = _make_client()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


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


def test_chat_response_model_structure() -> None:
    req = ChatRequest(message="teste")
    assert req.message == "teste"
    assert req.stream is False
    assert req.policy == "balanced"


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
