import pytest
from pydantic import ValidationError

from orion_mcp.api.schemas import ChatRequest
from orion_mcp.core.config.settings import get_settings
from orion_mcp.mcp_adapter.queries import ALLOWED_QUERY_IDS


def _any_query_id() -> str:
    return next(iter(ALLOWED_QUERY_IDS))


def test_chat_request_rejects_unknown_query_id() -> None:
    with pytest.raises(ValidationError, match="query_id"):
        ChatRequest(message="x", query_id="__not_in_catalog__")


def test_chat_request_domain_requires_grpc_target(monkeypatch: pytest.MonkeyPatch) -> None:
    from orion_mcp.core.config.settings import Settings

    monkeypatch.setattr(
        "orion_mcp.api.schemas.get_settings",
        lambda: Settings(mcp_grpc_target=None),
    )
    with pytest.raises(ValidationError, match="GRPC_TARGET|grpc|catalogadas"):
        ChatRequest(message="x", query_id=_any_query_id())


def test_chat_request_domain_ok_when_grpc_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORION_MCP_GRPC_TARGET", "127.0.0.1:59999")
    get_settings.cache_clear()
    try:
        req = ChatRequest(message="x", query_id=_any_query_id(), limit=50)
        assert req.query_id == _any_query_id()
        assert req.limit == 50
    finally:
        monkeypatch.delenv("ORION_MCP_GRPC_TARGET", raising=False)
        get_settings.cache_clear()
