from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from orion_mcp_v2.agent_debug_log import agent_debug_ndjson
from orion_mcp_v2.cache.redis_memory import MemoryRedisStore
from orion_mcp_v2.config.settings import Settings
from orion_mcp_v2.core.budget import RequestBudget
from orion_mcp_v2.core.context.builder import build_user_prompt
from orion_mcp_v2.core.context.context_caps import apply_llm_context_max_chars, skill_render_char_budgets
from orion_mcp_v2.core.data_engine.pipeline import run_data_pipeline
from orion_mcp_v2.core.decision.engine import PlannedTurn, decide_turn
from orion_mcp_v2.db.mysql.query_executor import AnalyticsQueryExecutor
from orion_mcp_v2.llm_provider.openai_provider import OpenAIChatService
from orion_mcp_v2.skill.loader import SkillRegistry
from orion_mcp_v2.skill.models import SkillSpec
from orion_mcp_v2.skill.reference_lookups_loader import append_reference_lookups_to_system
from orion_mcp_v2.state.models import ConversationStateV2
from orion_mcp_v2.state.repository import StateRepository

_logger = logging.getLogger(__name__)


def _sse_event(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@dataclass
class TurnResult:
    reply: str
    session_id: str
    user_id: str
    metadata: dict[str, Any]


@dataclass
class _PreparedLLM:
    planned: PlannedTurn
    pipeline_out: dict[str, Any]
    rows: list[Any]
    state: ConversationStateV2
    skill: SkillSpec
    sys_prompt: str
    user_prompt: str
    context_truncated: bool
    redis_blob: dict[str, Any] | None
    budget: RequestBudget


class OrionOrchestratorV2:
    def __init__(
        self,
        settings: Settings,
        repo: StateRepository,
        mysql: AnalyticsQueryExecutor,
        redis_mem: MemoryRedisStore,
        skills: SkillRegistry,
        llm: OpenAIChatService,
    ):
        self._settings = settings
        self._repo = repo
        self._mysql = mysql
        self._redis_mem = redis_mem
        self._skills = skills
        self._llm = llm

    @property
    def state_repository(self) -> StateRepository:
        return self._repo

    async def _prepare_llm(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        date_from: str | None,
        date_to: str | None,
        budget: RequestBudget,
    ) -> _PreparedLLM:
        await self._repo.ensure_user(user_id)

        state = await self._repo.load(session_id)
        if state is None:
            state = ConversationStateV2(session_id=session_id, user_id=user_id, messages=[])

        planned = decide_turn(message, date_from=date_from, date_to=date_to)

        rows_payload = await self._mysql.execute(planned.query_id, planned.params)
        rows = rows_payload.get("rows") or []
        pipeline_out = run_data_pipeline(
            rows,
            query_id=planned.query_id,
            intent=planned.intent.value,
            settings=self._settings,
        )

        redis_blob = await self._redis_mem.get_category(user_id, planned.intent.value)

        skill = self._skills.get(planned.skill_id)
        caps = skill_render_char_budgets(self._settings)
        sys_prompt = skill.render_system(
            question=message,
            data_summary=json.dumps(pipeline_out["summary"], ensure_ascii=False)[: caps["data_summary"]],
            insights="\n".join(pipeline_out.get("insights") or [])[: caps["insights"]],
            sample=json.dumps(pipeline_out["sample"], ensure_ascii=False)[: caps["sample"]],
        )
        sys_prompt = append_reference_lookups_to_system(sys_prompt, self._settings)

        recent_q = [m.content for m in state.messages if m.role == "user"][-10:]
        user_prompt = build_user_prompt(
            settings=self._settings,
            question=message,
            pipeline_out=pipeline_out,
            redis_memory=redis_blob,
            recent_user_messages=recent_q,
        )

        sys_prompt, user_prompt, truncated = apply_llm_context_max_chars(
            sys_prompt, user_prompt, self._settings
        )

        budget.record_llm()

        return _PreparedLLM(
            planned=planned,
            pipeline_out=pipeline_out,
            rows=rows,
            state=state,
            skill=skill,
            sys_prompt=sys_prompt,
            user_prompt=user_prompt,
            context_truncated=truncated,
            redis_blob=redis_blob,
            budget=budget,
        )

    def _finalize_state(
        self,
        *,
        prepared: _PreparedLLM,
        session_id: str,
        message: str,
        reply: str,
    ) -> None:
        planned = prepared.planned
        pipeline_out = prepared.pipeline_out
        rows = prepared.rows
        state = prepared.state

        signature = f"{planned.query_id}:{planned.params.get('date_from')}:{planned.params.get('date_to')}"
        state.last_data = {
            "query_id": planned.query_id,
            "summary": pipeline_out["summary"],
            "insights": pipeline_out["insights"],
            "row_count": pipeline_out["row_count"],
        }
        state.last_query_signature = signature
        state.append_exchange(message, reply)

    async def run_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> TurnResult:
        t0 = time.perf_counter()
        budget = RequestBudget(self._settings)
        prepared = await self._prepare_llm(
            session_id=session_id,
            user_id=user_id,
            message=message,
            date_from=date_from,
            date_to=date_to,
            budget=budget,
        )

        _mt = min(prepared.skill.max_tokens, self._settings.openai_max_tokens)
        agent_debug_ndjson(
            location="orchestrator.py:run_turn",
            message="llm_input_full_context",
            hypothesis_id="H_orchestrator_pre_llm",
            data={
                "session_id": session_id,
                "user_id": user_id,
                "user_message": message,
                "date_from": date_from,
                "date_to": date_to,
                "intent": prepared.planned.intent.value,
                "query_id": prepared.planned.query_id,
                "skill_id": prepared.planned.skill_id,
                "model": prepared.skill.model,
                "max_tokens": _mt,
                "context_truncated": prepared.context_truncated,
                "system_prompt": prepared.sys_prompt,
                "user_prompt": prepared.user_prompt,
                "row_count": len(prepared.rows),
            },
        )

        reply = await self._llm.complete(
            system_prompt=prepared.sys_prompt,
            user_text=prepared.user_prompt,
            model=prepared.skill.model,
            max_tokens=_mt,
        )

        self._finalize_state(prepared=prepared, session_id=session_id, message=message, reply=reply)
        await self._repo.save(prepared.state)

        elapsed = time.perf_counter() - t0
        meta = {
            "intent": prepared.planned.intent.value,
            "skill_id": prepared.planned.skill_id,
            "query_id": prepared.planned.query_id,
            "row_count": len(prepared.rows),
            "elapsed_seconds": round(elapsed, 4),
            "context_truncated": prepared.context_truncated,
            "budget": prepared.budget.snapshot(),
        }
        _logger.info("turn_ok", extra=meta)
        return TurnResult(
            reply=reply,
            session_id=session_id,
            user_id=prepared.state.user_id,
            metadata=meta,
        )

    async def handle_chat_stream(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> AsyncIterator[str]:
        t0 = time.perf_counter()
        budget = RequestBudget(self._settings)
        prepared = await self._prepare_llm(
            session_id=session_id,
            user_id=user_id,
            message=message,
            date_from=date_from,
            date_to=date_to,
            budget=budget,
        )

        chunks: list[str] = []
        async for delta in self._llm.complete_stream(
            system_prompt=prepared.sys_prompt,
            user_text=prepared.user_prompt,
            model=prepared.skill.model,
            max_tokens=min(prepared.skill.max_tokens, self._settings.openai_max_tokens),
        ):
            chunks.append(delta)
            yield _sse_event({"type": "token", "delta": delta})

        reply = "".join(chunks)
        self._finalize_state(prepared=prepared, session_id=session_id, message=message, reply=reply)
        await self._repo.save(prepared.state)

        elapsed = time.perf_counter() - t0
        meta = {
            "intent": prepared.planned.intent.value,
            "skill_id": prepared.planned.skill_id,
            "query_id": prepared.planned.query_id,
            "row_count": len(prepared.rows),
            "elapsed_seconds": round(elapsed, 4),
            "context_truncated": prepared.context_truncated,
            "budget": prepared.budget.snapshot(),
        }
        payload = {
            "reply": reply,
            "metadata": meta,
        }
        yield _sse_event(
            {
                "type": "done",
                "session_id": session_id,
                "user_id": prepared.state.user_id,
                "payload": payload,
                "metrics": meta,
            }
        )
