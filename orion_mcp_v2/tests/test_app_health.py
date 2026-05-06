from fastapi.testclient import TestClient

from orion_mcp_v2.main import build_app


def test_health():
    app = build_app()
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
