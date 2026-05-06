"""Regressão: insumo ao LLM não deve incluir dump bruto de linhas SQL nem ultrapassar tetos."""

import json

import pytest

from orion_mcp_v2.cache.redis_memory import MemoryRedisStore
from orion_mcp_v2.config.settings import Settings
from orion_mcp_v2.core.orchestrator.orchestrator import OrionOrchestratorV2
from orion_mcp_v2.llm_provider.openai_provider import OpenAIChatService
from orion_mcp_v2.skill.loader import load_all_skills
from orion_mcp_v2.state.repository import StateRepository


class FakeMysqlWide:
    def __init__(self) -> None:
        self.last_rows: list[dict] = []

    async def execute(self, query_id: str, params: dict):
        rows = [{"id": i, "payload": "x" * 500} for i in range(50)]
        self.last_rows = rows
        return {"rows": rows, "query_id": query_id, "row_count": len(rows)}


@pytest.mark.asyncio
async def test_llm_prompt_has_no_raw_rows_blob():
    settings = Settings(llm_context_max_chars=12000)
    repo = StateRepository(None)
    mysql = FakeMysqlWide()
    mem = MemoryRedisStore(None, ttl_seconds=3600)
    skills = load_all_skills()
    llm = OpenAIChatService(settings)
    orch = OrionOrchestratorV2(settings, repo, mysql, mem, skills, llm)

    captured: dict[str, str] = {}

    async def _capture_complete(**kw):
        captured["system"] = kw.get("system_prompt") or ""
        captured["user"] = kw.get("user_text") or ""
        return "ok"

    llm.complete = _capture_complete  # type: ignore[method-assign]

    await orch.run_turn(
        session_id="sess-contract",
        user_id="user-c",
        message="ticket médio por concessionária",
        date_from="2026-01-01",
        date_to="2026-01-31",
    )

    blob = (captured.get("system") or "") + (captured.get("user") or "")
    raw = json.dumps(mysql.last_rows)
    assert len(blob) < len(raw) // 2, "prompt deve ser muito menor que o dump JSON de todas as linhas"
    assert "### Dados resumidos" in blob or "summary" in blob.lower()


@pytest.mark.asyncio
async def test_llm_context_max_chars_enforced():
    settings = Settings(llm_context_max_chars=800)
    repo = StateRepository(None)
    mysql = FakeMysqlWide()
    mem = MemoryRedisStore(None, ttl_seconds=3600)
    skills = load_all_skills()
    llm = OpenAIChatService(settings)
    orch = OrionOrchestratorV2(settings, repo, mysql, mem, skills, llm)

    captured: dict[str, str] = {}

    async def _capture_complete(**kw):
        captured["system"] = kw.get("system_prompt") or ""
        captured["user"] = kw.get("user_text") or ""
        return "x"

    llm.complete = _capture_complete  # type: ignore[method-assign]

    await orch.run_turn(
        session_id="sess-cap",
        user_id="user-c",
        message="teste",
        date_from="2026-01-01",
        date_to="2026-01-31",
    )

    total = len(captured.get("system") or "") + len(captured.get("user") or "")
    assert total <= 800
