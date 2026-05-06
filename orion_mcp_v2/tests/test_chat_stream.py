import json

from fastapi.testclient import TestClient

from orion_mcp_v2.main import build_app


def _parse_sse_events(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


class _FakeMysql:
    async def execute(self, query_id: str, params: dict):
        return {
            "rows": [{"concessionaria": "X", "ticket_medio": 1500.0}],
            "query_id": query_id,
            "row_count": 1,
        }


def test_chat_stream_sse_tokens_and_done() -> None:
    app = build_app()
    with TestClient(app) as c:
        c.app.state.orchestrator._mysql = _FakeMysql()
        with c.stream(
            "POST",
            "/api/v1/chat/stream",
            json={
                "session_id": "s-stream-1",
                "user_id": "u1",
                "message": "Qual o ticket médio?",
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            },
        ) as r:
            assert r.status_code == 200
            assert r.headers.get("content-type", "").startswith("text/event-stream")
            body = "".join(r.iter_text())

    events = _parse_sse_events(body)
    types = [e.get("type") for e in events]
    assert "token" in types, events
    done = [e for e in events if e.get("type") == "done"]
    assert len(done) == 1
    assert done[0].get("session_id") == "s-stream-1"
    assert done[0].get("user_id") == "u1"
    assert "payload" in done[0]
    assert "metrics" in done[0]
    tokens = [e for e in events if e.get("type") == "token"]
    assert all((e.get("delta") or "") != "" for e in tokens)


def test_chat_stream_openapi_path() -> None:
    app = build_app()
    with TestClient(app) as c:
        spec = c.get("/openapi.json").json()
    assert "/api/v1/chat/stream" in spec.get("paths", {})
