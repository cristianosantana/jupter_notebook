"""Primeira mensagem sem session_id/user_id; resposta inclui ambos."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orion_mcp_v2.main import build_app


class _FakeMysql:
    async def execute(self, query_id: str, params: dict):
        return {
            "rows": [{"concessionaria": "X", "ticket_medio": 1500.0}],
            "query_id": query_id,
            "row_count": 1,
        }


def test_chat_json_first_message_without_ids() -> None:
    app = build_app()
    with TestClient(app) as c:
        c.app.state.orchestrator._mysql = _FakeMysql()
        r = c.post(
            "/api/v1/chat",
            json={
                "message": "Qual o ticket médio?",
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert len(data.get("session_id", "")) >= 4
    assert len(data.get("user_id", "")) >= 1


def test_chat_second_message_same_session_keeps_user_when_pg_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Com estado persistido (repo.load devolve sessão), segundo pedido só com session_id mantém user_id."""
    from orion_mcp_v2.state.models import ConversationStateV2

    app = build_app()
    with TestClient(app) as c:
        orch = c.app.state.orchestrator
        orch._mysql = _FakeMysql()

        existing = ConversationStateV2(
            session_id="sess-roundtrip",
            user_id="user-stable",
            messages=[],
        )

        async def fake_load(sid: str):
            if sid == "sess-roundtrip":
                return existing
            return None

        monkeypatch.setattr(orch.state_repository, "load", fake_load)

        r = c.post(
            "/api/v1/chat",
            json={
                "message": "Olá",
                "session_id": "sess-roundtrip",
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            },
        )
    assert r.status_code == 200
    assert r.json().get("user_id") == "user-stable"
