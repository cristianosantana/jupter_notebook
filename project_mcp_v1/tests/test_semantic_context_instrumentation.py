"""Instrumentação do inject host de contexto semântico (observer + detalhe MCP)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.context_semantic_contract import (
    CONTEXT_RETRIEVE_EMPTY_INDEX_MARKER,
    build_host_retrieve_ok_detail,
    is_empty_index_placeholder,
)
from app.orchestrator import ModularOrchestrator
from mcp.types import CallToolResult, TextContent

_SKILLS = Path(__file__).resolve().parent.parent / "app" / "skills"


def _stub_settings(**overrides):
    from app.config import get_settings

    base = get_settings()
    return base.model_copy(update=overrides)


def test_inject_skip_no_session_id_observer_entry():
    async def _run():
        meta: dict = {"observer_log": {"entries": []}}
        client = MagicMock()
        client.call_tool = AsyncMock()
        orch = ModularOrchestrator(MagicMock(), client, skills_dir=_SKILLS)
        orch._session_metadata = meta
        orch._session_id_for_cache = None
        orch.current_agent = "analise_os"
        st = _stub_settings()
        with patch("app.orchestrator.get_settings", return_value=st):
            await orch._inject_semantic_context_for_specialist("pergunta longa")
        client.call_tool.assert_not_called()
        ents = meta.get("observer_log", {}).get("entries", [])
        assert any(
            e.get("event_type") == "host_context_retrieve_skipped"
            and e.get("detail", {}).get("reason") == "no_session_id"
            for e in ents
        )

    asyncio.run(_run())


def test_inject_ok_enriched_detail_and_placeholder_flag():
    async def _run():
        body = json.dumps(
            {
                "ok": True,
                "injected_context": f"_{CONTEXT_RETRIEVE_EMPTY_INDEX_MARKER} ou sem embeddings._",
                "sessions": [{"session_id": "a", "score": 0.1}],
                "messages_preview": [{"message_id": 1, "score": 0.2}],
                "like_prefilter": [
                    {"session_id": "x", "mode": "ilike", "candidates": 2, "ilike_hits": 2},
                    {"session_id": "y", "mode": "fallback", "candidates": 3, "ilike_hits": 0},
                ],
            },
            ensure_ascii=False,
        )
        meta: dict = {"observer_log": {"entries": []}}
        client = MagicMock()
        client.call_tool = AsyncMock(
            return_value=CallToolResult(
                content=[TextContent(type="text", text=body)],
                isError=False,
            )
        )
        orch = ModularOrchestrator(MagicMock(), client, skills_dir=_SKILLS)
        orch._session_metadata = meta
        orch._session_id_for_cache = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        orch.current_agent = "analise_os"
        st = _stub_settings(
            semantic_context_debug_in_chat_response=True,
            context_retrieve_host_inject_enabled=True,
        )
        with patch("app.orchestrator.get_settings", return_value=st):
            await orch._inject_semantic_context_for_specialist("pergunta longa")
        ents = meta.get("observer_log", {}).get("entries", [])
        ok_ev = [e for e in ents if e.get("event_type") == "host_context_retrieve_ok"]
        assert len(ok_ev) == 1
        d = ok_ev[0]["detail"]
        assert d["chars"] > 0
        assert d["sessions_count"] == 1
        assert d["messages_preview_count"] == 1
        assert d["index_placeholder"] is True
        assert d["like_prefilter"]["modes"]["ilike"] == 1
        assert d["like_prefilter"]["modes"]["fallback"] == 1
        assert orch._semantic_instrument_for_response is not None
        assert orch._semantic_instrument_for_response["event_type"] == "host_context_retrieve_ok"

    asyncio.run(_run())


def test_build_host_retrieve_ok_detail_real_content_not_placeholder():
    data = {
        "ok": True,
        "injected_context": "### Sessão real",
        "sessions": [],
        "messages_preview": [],
        "like_prefilter": [],
    }
    d = build_host_retrieve_ok_detail(data, 100)
    assert d["index_placeholder"] is False


def test_is_empty_index_placeholder():
    assert is_empty_index_placeholder(f"x {CONTEXT_RETRIEVE_EMPTY_INDEX_MARKER} y")
    assert not is_empty_index_placeholder("só contexto real")
