"""C1: o processo da API não deve arrancar nem importar o servidor/cliente MCP."""

from __future__ import annotations

from pathlib import Path


def test_main_module_source_has_no_mcp_server_runtime():
    import orion_mcp_v2.main as main_mod

    src = Path(main_mod.__file__).read_text(encoding="utf-8")
    assert "mcp_server_standalone" not in src
    assert "FastMCP" not in src
    assert "fastmcp" not in src


def test_fastapi_app_has_no_mcp_routes():
    from orion_mcp_v2.main import build_app

    app = build_app()
    for r in app.routes:
        path = getattr(r, "path", "") or ""
        assert not path.startswith("/mcp")
        assert "/mcp/" not in path


def test_openapi_paths_are_chat_and_health_only_chat_ns():
    """Smoke: rotas públicas esperadas não incluem servidor MCP embutido."""
    from fastapi.testclient import TestClient

    from orion_mcp_v2.main import build_app

    with TestClient(build_app()) as c:
        spec = c.get("/openapi.json").json()
    paths = list(spec.get("paths", {}).keys())
    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/stream" in paths
