"""Dedupe de ``context_retrieve_similar`` quando o host já obteve o mesmo corpo no turno."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.orchestrator import ModularOrchestrator
from mcp.types import CallToolResult, TextContent

_SKILLS = Path(__file__).resolve().parent.parent / "app" / "skills"


def test_context_retrieve_similar_dedupes_when_host_prefilled():
    async def _run():
        meta: dict = {}
        body = json.dumps(
            {
                "ok": True,
                "injected_context": "## pre",
                "sessions": [],
                "messages_preview": [],
            },
            ensure_ascii=False,
        )
        meta["_host_context_retrieve_full_json"] = body
        meta["_host_retrieve_query_normalized"] = "Volume de OS último trimestre"
        meta["_host_retrieve_session_id"] = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        client = MagicMock()
        client.list_tools = AsyncMock(return_value=[])
        client.call_tool = AsyncMock(
            return_value=CallToolResult(
                content=[TextContent(type="text", text=body)],
                isError=False,
            )
        )

        orch = ModularOrchestrator(MagicMock(), client, skills_dir=_SKILLS)
        await orch.load_tools()
        orch.current_agent = "analise_os"
        orch._session_metadata = meta
        from uuid import UUID

        orch._session_id_for_cache = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        tools_used: list = []
        await orch._execute_single_tool_call(
            {
                "id": "call_dup",
                "function": {
                    "name": "context_retrieve_similar",
                    "arguments": json.dumps(
                        {
                            "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "query": "Volume de OS último trimestre",
                        }
                    ),
                },
            },
            tools_used,
        )

        await orch._execute_single_tool_call(
            {
                "id": "call_other",
                "function": {
                    "name": "context_retrieve_similar",
                    "arguments": json.dumps(
                        {
                            "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "query": "outra coisa diferente",
                        }
                    ),
                },
            },
            tools_used,
        )

        assert client.call_tool.await_count == 1
        assert tools_used[0].get("host_retrieve_deduped") is True
        assert tools_used[1].get("host_retrieve_deduped") is None

    asyncio.run(_run())
