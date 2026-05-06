#!/usr/bin/env python3
from __future__ import annotations

from fastapi.testclient import TestClient

from orion_mcp.api.main import create_app


def main() -> None:
    with TestClient(create_app()) as c:
        r = c.get("/openapi.json")
        r.raise_for_status()
        spec = r.json()
        paths = spec.get("paths", {})
        assert "/api/v1/chat" in paths, "OpenAPI deve expor /api/v1/chat"
        assert "/api/v1/chat/stream" in paths, "OpenAPI deve expor /api/v1/chat/stream"
    print("validate_openapi: OK")


if __name__ == "__main__":
    main()
