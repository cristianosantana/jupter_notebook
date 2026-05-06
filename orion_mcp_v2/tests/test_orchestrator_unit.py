import pytest

from orion_mcp_v2.cache.redis_memory import MemoryRedisStore
from orion_mcp_v2.config.settings import Settings
from orion_mcp_v2.core.orchestrator.orchestrator import OrionOrchestratorV2
from orion_mcp_v2.db.mysql.query_executor import AnalyticsQueryExecutor
from orion_mcp_v2.llm_provider.openai_provider import OpenAIChatService
from orion_mcp_v2.skill.loader import load_all_skills
from orion_mcp_v2.state.repository import StateRepository


class FakeMysql:
    async def execute(self, query_id: str, params: dict):
        return {
            "rows": [{"concessionaria": "X", "ticket_medio": 1500.0}],
            "query_id": query_id,
            "row_count": 1,
        }


@pytest.mark.asyncio
async def test_run_turn_without_pg_redis():
    settings = Settings()
    repo = StateRepository(None)
    mysql = FakeMysql()
    mem = MemoryRedisStore(None, ttl_seconds=3600)
    skills = load_all_skills()
    llm = OpenAIChatService(settings)
    orch = OrionOrchestratorV2(settings, repo, mysql, mem, skills, llm)
    r = await orch.run_turn(
        session_id="sess-test",
        user_id="user-1",
        message="Qual o ticket médio?",
        date_from="2026-01-01",
        date_to="2026-01-31",
    )
    assert "ticket" in r.reply.lower() or "mock" in r.reply.lower()
    assert r.metadata.get("query_id")
