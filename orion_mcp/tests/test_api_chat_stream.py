import json

from fastapi.testclient import TestClient

from orion_mcp.api.main import create_app


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


def test_chat_stream_sse_tokens_and_done() -> None:
    with TestClient(create_app()) as c:
        with c.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"session_id": "s-stream-1", "message": "mostra analytics", "strategy": "fast"},
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
    assert "payload" in done[0]
    assert "metrics" in done[0]
    tokens = [e for e in events if e.get("type") == "token"]
    assert all((e.get("delta") or "") != "" for e in tokens)


def test_chat_stream_openapi_path() -> None:
    with TestClient(create_app()) as c:
        spec = c.get("/openapi.json").json()
    assert "/api/v1/chat/stream" in spec.get("paths", {})
