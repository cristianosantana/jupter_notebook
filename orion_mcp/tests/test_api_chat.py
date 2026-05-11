from fastapi.testclient import TestClient

from orion_mcp.api.main import create_app


def test_health() -> None:
    with TestClient(create_app()) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi() -> None:
    with TestClient(create_app()) as c:
        r = c.get("/openapi.json")
    assert r.status_code == 200
    assert "paths" in r.json()


def test_chat_v1_flow() -> None:
    with TestClient(create_app()) as c:
        r = c.post(
            "/api/v1/chat",
            json={"session_id": "t1", "message": "mostra analytics", "strategy": "fast"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "t1"
    assert body["metrics"]["tool_calls"] == 1


def test_chat_v1_auto_session_id() -> None:
    with TestClient(create_app()) as c:
        r = c.post(
            "/api/v1/chat",
            json={"message": "mostra analytics", "strategy": "fast"},
        )
    assert r.status_code == 200
    body = r.json()
    sid = body["session_id"]
    assert len(sid) == 36
    assert sid.count("-") == 4
    assert body["metrics"]["tool_calls"] == 1


def test_chat_v1_blank_session_id_generates_uuid() -> None:
    with TestClient(create_app()) as c:
        r = c.post(
            "/api/v1/chat",
            json={"session_id": "   ", "message": "mostra analytics", "strategy": "fast"},
        )
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert len(sid) == 36
