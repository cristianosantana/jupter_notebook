"""
Orquestrador Modular para Maestro de Agentes.

Implementa:
1. SkillLoader: Carrega SKILLs dinamicamente com YAML frontmatter
2. ModelRouter: resolve o modelo OpenAI por agente (``Settings`` / ``.env``)
3. ModularOrchestrator: Agent loop com decomposição de tasks
"""

import asyncio
import json
import logging
import time
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from dataclasses import dataclass
from uuid import UUID, uuid4

from ai_provider.base import ModelProvider
from app.analytics_aggregate_engine import run_analytics_aggregate
from app.analytics_session_datasets import (
    get_dataset_id_for_cache_key,
    increment_aggregate_calls,
    inject_dataset_handles_into_json_text,
    load_dataset_for_aggregate,
    register_run_analytics_result,
)
from app.mcp_session_cache import (
    append_cache_entry,
    build_mcp_cache_digest_section,
    find_cache_entry,
    mcp_cache_key,
    entries_fingerprint,
)
from app.message_lifecycle import pop_first_segment, strip_leading_orphan_tools
from app.context_budget import shrink_chat_messages_to_budget
from app.history_payload import (
    build_compact_history_messages_for_llm,
    latest_user_text_for_semantic,
)
from app.prompt_assembly import build_effective_system_text, build_system_package
from app.prompt_messages import (
    _estimate_prompt_tokens_messages_plus_skill,
    _estimate_tokens_from_text,
    _estimate_tokens_from_tool_dicts,
    _messages_with_skill,
    estimate_full_prompt_tokens,
)
from app.tool_truncation import safe_truncate_tool_content
from app.context_semantic_contract import build_host_retrieve_ok_detail
from app.pipeline_critique import format_critique_message, parse_critique_response
from app.routing_tools import (
    MAESTRO_TOOLS_ONLY,
    ROUTE_TO_SPECIALIST_TOOL_NAME,
    SPECIALIST_AGENTS,
    parse_route_arguments,
    specialist_from_text_fallback,
)
from app.virtual_tools import (
    ANALYTICS_AGGREGATE_SESSION_TOOL_NAME,
    analytics_aggregate_session_openai_tool,
)
from app.agent_trace import (
    AgentTraceLogger,
    activate_openai_chat_stats_for_run,
    get_trace_logger,
    llm_phase_context,
    reset_trace_logger,
    set_trace_logger,
    take_openai_chat_stats,
)
from app.config import Settings, get_settings, resolve_agent_trace_dir
from app.orchestrator_analysis import analise
from app.orchestrator_flow import resolve_orchestrator_flow_mode
from app.orchestrator_llm_budget import llm_budget_begin_run, llm_budget_end_run, was_llm_cap_hit
from app.content_blocks import split_reply_and_blocks
from app.orchestrator_sm import TurnPhase, log_phase, run_linear_turn
from app.orchestrator_state import (
    build_tool_registry_context_markdown,
    ensure_orchestrator_state_block,
    ephemeral_tool_results,
    find_tool_result_text,
    put_tool_result,
    tool_excluded_from_state_store,
)
from mcp_client.client import Client
from mcp.types import CallToolResult, TextContent, Tool  # pyright: ignore[reportMissingImports]

_logger_orch = logging.getLogger(__name__)

# Tipos de agente (alinhado com ``Settings.orchestrator_agent_types``; manter sincronizado).
AgentType = Literal[
    "maestro",
    "analise_os",
    "clusterizacao",
    "visualizador",
    "agregador",
    "projecoes",
    "verificador",
    "compositor_layout",
]


@dataclass
class SkillMetadata:
    """Metadados extraídos do frontmatter YAML do SKILL."""
    model: str
    context_budget: int
    max_tokens: int
    temperature: float
    role: str
    agent_type: AgentType | None = None


class SkillLoader:
    """Carrega SKILLs .md com YAML frontmatter e os cacheiza."""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._cache: dict[str, tuple[str, SkillMetadata]] = {}

    def load_skill(self, skill_id: str) -> tuple[str, SkillMetadata]:
        """Carrega SKILL por id de ficheiro (ex.: ``analise_os``, ``avaliador_critico``)."""
        key = str(skill_id)
        if key in self._cache:
            return self._cache[key]

        skill_file = self.skills_dir / f"{key}.md"
        if not skill_file.is_file():
            raise FileNotFoundError(f"SKILL not found: {skill_file}")

        content = skill_file.read_text(encoding="utf-8")
        skill_text, metadata = self._parse_skill(content)

        self._cache[key] = (skill_text, metadata)
        return skill_text, metadata

    @staticmethod
    def _parse_skill(content: str) -> tuple[str, SkillMetadata]:
        """Extrai YAML frontmatter e retorna (skill_text, metadata)."""
        # Padrão: --- \n yaml \n --- \n conteúdo
        match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
        if not match:
            raise ValueError("SKILL deve conter YAML frontmatter entre ---")

        yaml_str, skill_body = match.groups()

        # Parse YAML simplificado (evita dependência extra)
        metadata = SkillLoader._parse_yaml(yaml_str)
        return skill_body.strip(), metadata

    @staticmethod
    def _parse_yaml(yaml_str: str) -> SkillMetadata:
        """Parse simplificado de YAML frontmatter."""
        lines = yaml_str.strip().split("\n")
        data = {}
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                # Converte tipos básicos
                if value.isdigit():
                    data[key] = int(value)
                elif value.replace(".", "", 1).isdigit():
                    data[key] = float(value)
                else:
                    data[key] = value

        raw_model = str(data.get("model", "sonnet")).strip().lower()

        return SkillMetadata(
            model=raw_model,
            context_budget=data.get("context_budget", 100000),
            max_tokens=data.get("max_tokens", 2000),
            temperature=data.get("temperature", 0.5),
            role=data.get("role", "analyst"),
            agent_type=data.get("agent_type"),
        )


class ModelRouter:
    """Resolve o identificador do modelo OpenAI por agente (``Settings`` / ``.env``)."""

    @staticmethod
    def get_model(agent_type: AgentType | str, settings: Settings | None = None) -> str:
        """Nome do modelo na API (override por agente ou ``openai_model``)."""
        st = settings or get_settings()
        return st.effective_model_for_agent(str(agent_type))


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    s = str(raw).strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


def _mcp_result_to_text(result: CallToolResult) -> str:
    parts: list[str] = []
    for block in result.content:
        if block.type == "text":
            parts.append(block.text)
        else:
            parts.append(block.model_dump_json())
    text = "\n".join(parts) if parts else ""
    if result.isError:
        return text or "Erro ao executar a ferramenta."
    return text if text else "(sem conteúdo textual)"


class ModularOrchestrator:
    """
    Orquestrador Modular com suporte a múltiplos agentes especializados.

    Flow:
    1. Usuário envia pergunta ao Maestro
    2. Maestro roteía para agente correto (analise_os, clusterizacao, etc.)
    3. Agente especializado executa com seu SKILL e ferramentas
    4. Resultado retorna ao usuário
    """

    def __init__(
        self,
        model: ModelProvider,
        client: Client,
        skills_dir: Path | None = None,
    ):
        self.model = model
        self.client = client
        self.messages: list[dict[str, Any]] = []
        self._message_times: list[float] = []
        self.tools: list[Tool] | None = None

        # Inicializa SkillLoader
        if skills_dir is None:
            skills_dir = Path(__file__).resolve().parent / "skills"
        self.skill_loader = SkillLoader(skills_dir)
        self.current_agent: AgentType = "maestro"
        self.current_skill: str = ""
        self.current_metadata: SkillMetadata | None = None
        self._entity_glossary: str = ""
        self._entity_glossary_cache: OrderedDict[UUID, str] = OrderedDict()
        self._session_metadata: dict[str, Any] | None = None
        self._session_id_for_cache: UUID | None = None
        self._semantic_retrieval_markdown: str | None = None
        self._semantic_instrument_for_response: dict[str, Any] | None = None
        self._mcp_parallel_sem: asyncio.Semaphore | None = None
        self._orch_ephemeral_state: dict[str, Any] | None = None
        self._turn_timings: list[dict[str, Any]] = []
        self._orchestrator_flow_mode: str = "legacy"

    def _timing_mark(self, name: str, duration_ms: float) -> None:
        self._turn_timings.append(
            {"substep": str(name), "ms": round(float(duration_ms), 3)}
        )

    def _mcp_parallel_semaphore(self) -> asyncio.Semaphore:
        if self._mcp_parallel_sem is None:
            n = max(1, int(get_settings().orchestrator_parallel_tool_calls_max_concurrent))
            self._mcp_parallel_sem = asyncio.Semaphore(n)
        return self._mcp_parallel_sem

    async def _call_mcp_tool_bounded(self, name: str, args: dict[str, Any]) -> CallToolResult:
        t0 = time.perf_counter()
        result: CallToolResult | None = None
        fonte = "rede_mcp"
        analise(
            "mcp_chamada_início",
            tool=name,
            args_resumo=args,
            timeout_s=float(get_settings().orchestrator_mcp_tool_call_timeout_seconds),
        )
        try:
            if not tool_excluded_from_state_store(name):
                hit = find_tool_result_text(self._orch_state_block(), name, args)
                if hit:
                    txt, is_err = hit
                    fonte = "cache_orchestrator_state"
                    self._observer_append(
                        "orchestrator_state_mcp_hit",
                        {"tool": name, "key_prefix": mcp_cache_key(name, args)[:16]},
                    )
                    result = CallToolResult(
                        content=[TextContent(type="text", text=txt)],
                        isError=is_err,
                    )
                    return result
            st = get_settings()
            tout = float(st.orchestrator_mcp_tool_call_timeout_seconds)
            async with self._mcp_parallel_semaphore():
                if tout > 0:
                    result = await asyncio.wait_for(
                        self.client.call_tool(name, args),
                        timeout=tout,
                    )
                else:
                    result = await self.client.call_tool(name, args)
            return result
        finally:
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            analise(
                "mcp_chamada_fim",
                tool=name,
                fonte=fonte,
                duration_ms=dt_ms,
                is_error=bool(getattr(result, "isError", False)) if result is not None else None,
            )
            tr_m = get_trace_logger()
            if tr_m:
                tr_m.record(
                    "mcp.tool_call.timing_ms",
                    tool=name,
                    duration_ms=dt_ms,
                )

    def _specialist_tool_calls_parallel_mcp_eligible(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> bool:
        st = get_settings()
        if not st.orchestrator_parallel_tool_calls_enabled or len(tool_calls) <= 1:
            return False
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name")
            if not name:
                return False
            if name == ANALYTICS_AGGREGATE_SESSION_TOOL_NAME:
                return False
            if name == ROUTE_TO_SPECIALIST_TOOL_NAME and self.current_agent != "maestro":
                return False
            args = _parse_tool_arguments(fn.get("arguments"))
            use_cache = self._use_mcp_session_cache() and name != ROUTE_TO_SPECIALIST_TOOL_NAME
            ck_tool = mcp_cache_key(name, args) if use_cache else ""
            if use_cache and self._session_metadata is not None:
                hit = find_cache_entry(self._session_metadata, ck_tool)
                if hit and hit.get("result_text"):
                    return False
            if name == "context_retrieve_similar" and self._session_metadata is not None:
                q_arg = str(args.get("query") or "").strip()
                s_arg = str(args.get("session_id") or "").strip().lower()
                host_q = str(
                    self._session_metadata.get("_host_retrieve_query_normalized") or ""
                ).strip()
                host_sid = str(
                    self._session_metadata.get("_host_retrieve_session_id") or ""
                ).strip().lower()
                cached = self._session_metadata.get("_host_context_retrieve_full_json")
                if cached and host_q == q_arg and host_sid == s_arg:
                    return False
        return True

    async def _dispatch_specialist_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        tools_used: list[dict[str, Any]],
    ) -> None:
        nms = [
            str((tc.get("function") or {}).get("name") or "")
            for tc in tool_calls
        ]
        analise(
            "dispatch_tools",
            agent=self.current_agent,
            n=len(tool_calls),
            paralelo=self._specialist_tool_calls_parallel_mcp_eligible(tool_calls),
            tools=nms,
        )
        if self._specialist_tool_calls_parallel_mcp_eligible(tool_calls):
            parsed: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = str(fn.get("name") or "")
                args = _parse_tool_arguments(fn.get("arguments"))
                parsed.append((tc, name, args))
            mcp_results = await asyncio.gather(
                *[self._call_mcp_tool_bounded(n, a) for _tc, n, a in parsed],
                return_exceptions=True,
            )
            if any(isinstance(r, Exception) for r in mcp_results):
                for r, (_tc, n, _a) in zip(mcp_results, parsed):
                    if isinstance(r, Exception):
                        _logger_orch.warning("parallel MCP tool %s: %s", n, r)
                for tc in tool_calls:
                    await self._execute_single_tool_call(tc, tools_used)
                return
            for (tc, _name, _args), res in zip(parsed, mcp_results):
                await self._execute_single_tool_call(
                    tc, tools_used, mcp_result_override=res
                )
            return
        for tc in tool_calls:
            await self._execute_single_tool_call(tc, tools_used)

    @staticmethod
    def _glossary_cache_key(session_id: UUID | None) -> UUID:
        if session_id is not None:
            return session_id
        return get_settings().orchestrator_glossary_cache_anonymous_key()

    def _glossary_cache_get(self, session_id: UUID | None) -> str | None:
        st = get_settings()
        if not st.entity_glossary_session_cache_enabled:
            return None
        key = self._glossary_cache_key(session_id)
        val = self._entity_glossary_cache.get(key)
        if val is None:
            return None
        self._entity_glossary_cache.move_to_end(key)
        return val

    def _glossary_cache_set(self, session_id: UUID | None, markdown: str) -> None:
        st = get_settings()
        if not st.entity_glossary_session_cache_enabled:
            return
        key = self._glossary_cache_key(session_id)
        self._entity_glossary_cache[key] = markdown
        self._entity_glossary_cache.move_to_end(key)
        max_n = max(1, int(st.entity_glossary_session_cache_max))
        while len(self._entity_glossary_cache) > max_n:
            self._entity_glossary_cache.popitem(last=False)

    def _glossary_cache_invalidate(self, session_id: UUID | None) -> None:
        if not get_settings().entity_glossary_session_cache_enabled:
            return
        self._entity_glossary_cache.pop(self._glossary_cache_key(session_id), None)

    async def load_tools(self):
        """Carrega ferramentas do MCP server."""
        tools = await self.client.list_tools()
        self.tools = tools

    async def set_agent(self, agent_type: AgentType) -> None:
        """Muda agente ativo, carregando seu SKILL."""
        if agent_type == self.current_agent:
            if not self.current_skill:
                self.current_skill, self.current_metadata = self.skill_loader.load_skill(agent_type)
            return

        print(f"🔄 Switching agent: {self.current_agent} → {agent_type}")
        self.current_skill, self.current_metadata = self.skill_loader.load_skill(agent_type)
        self.current_agent = agent_type
        self.messages.clear()  # Limpa histórico ao trocar agente
        self._message_times.clear()

    async def reset_conversation(self, session_id: UUID | None = None) -> None:
        """Limpa histórico e reposiciona no Maestro (novo tópico)."""
        self.messages.clear()
        self._message_times.clear()
        self._entity_glossary = ""
        await self.set_agent("maestro")
        if session_id is not None:
            self._glossary_cache_invalidate(session_id)
        else:
            self._glossary_cache_invalidate(None)

    def hydrate_session_state(
        self,
        agent_type: AgentType,
        messages: list[dict[str, Any]],
        message_times: list[float] | None = None,
        session_id: UUID | None = None,
    ) -> None:
        """
        Repõe histórico e agente sem `set_agent` (evita limpar mensagens ao trocar de sessão).
        Usado para reidratar a partir do PostgreSQL.
        """
        if agent_type != self.current_agent:
            self.current_skill, self.current_metadata = self.skill_loader.load_skill(agent_type)
            self.current_agent = agent_type
        elif not self.current_skill:
            self.current_skill, self.current_metadata = self.skill_loader.load_skill(agent_type)
        self.messages = [dict(m) for m in messages]
        if message_times and len(message_times) == len(self.messages):
            self._message_times = list(message_times)
        else:
            self._message_times = [time.time() for _ in self.messages]
        if session_id is not None:
            cached = self._glossary_cache_get(session_id)
            self._entity_glossary = cached.strip() if (cached and cached.strip()) else ""
        else:
            self._entity_glossary = ""

    def _session_meta(self) -> dict[str, Any]:
        return self._session_metadata if self._session_metadata is not None else {}

    def _orch_init_state_for_run(self) -> None:
        """Inicializa ``orchestrator_state`` em metadata ou estado efémero por turno."""
        self._orch_ephemeral_state = None
        if self._session_metadata is not None:
            ensure_orchestrator_state_block(self._session_metadata)
        else:
            self._orch_ephemeral_state = ephemeral_tool_results()

    def _orch_state_block(self) -> dict[str, Any]:
        if self._session_metadata is not None:
            return ensure_orchestrator_state_block(self._session_metadata)
        if self._orch_ephemeral_state is None:
            self._orch_ephemeral_state = ephemeral_tool_results()
        return self._orch_ephemeral_state

    def _orchestrator_state_context_markdown(self) -> str:
        try:
            return build_tool_registry_context_markdown(self._orch_state_block()).strip()
        except Exception:
            return ""

    def _use_mcp_session_cache(self) -> bool:
        return self._session_metadata is not None and self._session_id_for_cache is not None

    def _utc_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _observer_append(self, event_type: str, detail: Any) -> None:
        st = get_settings()
        bypass = event_type.startswith("host_context_retrieve") or (
            event_type == "tool_context_retrieve_deduped"
        )
        if not bypass and not st.observer_agent_enabled:
            return
        if self._session_metadata is None:
            if bypass:
                _logger_orch.info(
                    "semantic_context.%s (sem session_metadata) %s",
                    event_type,
                    detail,
                )
            return
        slot = self._session_metadata.setdefault("observer_log", {})
        ents = slot.setdefault("entries", [])
        ents.append(
            {
                "ts": self._utc_iso(),
                "event_type": event_type,
                "agent": self.current_agent,
                "detail": detail,
            }
        )
        cap = max(10, int(st.observer_log_max_entries))
        if len(ents) > cap:
            del ents[0 : len(ents) - cap]
        if bypass:
            _logger_orch.info("semantic_context.%s %s", event_type, detail)

    def _build_system_text_sync(self) -> str:
        """System para orçamento de poda (digest Python apenas, sem LLM)."""
        st = get_settings()
        digest = build_mcp_cache_digest_section(
            self._session_meta(),
            st,
            semantic_retrieval_markdown=self._semantic_retrieval_markdown,
        )
        tp_payload = MAESTRO_TOOLS_ONLY if self.current_agent == "maestro" else None
        return build_effective_system_text(
            agent=self.current_agent,
            skill_body=self.current_skill or "",
            entity_glossary_markdown=self._entity_glossary or "",
            mcp_digest_markdown=digest,
            session_metadata=self._session_meta(),
            tools_openai_payload=tp_payload,
            mcp_tools=self.tools,
            settings=st,
        )

    async def _digest_for_system_async(self) -> str:
        st = get_settings()
        md = self._session_meta()
        base = build_mcp_cache_digest_section(
            md,
            st,
            semantic_retrieval_markdown=self._semantic_retrieval_markdown,
        )
        entries = (md.get("mcp_tool_cache") or {}).get("entries") or []
        if not st.mcp_cache_digest_llm_enabled or not entries:
            return base
        fp = entries_fingerprint(entries)
        cached = md.get("mcp_digest_llm_cache") or {}
        if (
            st.mcp_cache_digest_llm_reuse_hash
            and cached.get("entries_hash") == fp
            and cached.get("digest_markdown")
        ):
            return str(cached["digest_markdown"])
        trig = (st.mcp_cache_digest_llm_trigger or "").strip().lower()
        if trig == "when_base_too_long" and len(base) < int(st.mcp_cache_digest_llm_min_chars_to_run):
            return base
        refined = await self._llm_refine_mcp_digest(base)
        if refined:
            slot = md.setdefault("mcp_digest_llm_cache", {})
            slot["entries_hash"] = fp
            slot["digest_markdown"] = refined[: int(st.mcp_cache_digest_llm_max_output_chars)]
            slot["generated_at"] = self._utc_iso()
            return str(slot["digest_markdown"])
        return base

    async def _llm_refine_mcp_digest(self, base_digest: str) -> str | None:
        st = get_settings()
        path = Path(__file__).resolve().parent / "prompts" / "internal" / "mcp_digest_editor.md"
        if not path.is_file():
            return None
        system = path.read_text(encoding="utf-8").strip()
        budget = int(st.mcp_cache_digest_llm_max_output_chars)
        user = (
            f"Orçamento máximo de saída: {budget} caracteres.\n\n"
            f"Digest base:\n\n{base_digest[:8000]}"
        )
        model_o = (st.mcp_cache_digest_llm_model or "").strip() or None
        try:
            with llm_phase_context("mcp_digest_llm"):
                resp = await asyncio.wait_for(
                    self.model.chat(
                        [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        tools=None,
                        model_override=model_o,
                    ),
                    timeout=float(st.mcp_cache_digest_llm_timeout_seconds),
                )
            return str((resp or {}).get("content") or "").strip() or None
        except (asyncio.TimeoutError, Exception) as e:
            _logger_orch.warning("mcp digest LLM refine failed: %s", e)
            self._observer_append(
                "mcp_digest_llm_failed",
                {
                    "error": type(e).__name__,
                    "timeout": isinstance(e, asyncio.TimeoutError),
                },
            )
            return None

    async def _build_system_text_async(self) -> str:
        st = get_settings()
        digest = await self._digest_for_system_async()
        tp_payload = MAESTRO_TOOLS_ONLY if self.current_agent == "maestro" else None
        return build_effective_system_text(
            agent=self.current_agent,
            skill_body=self.current_skill or "",
            entity_glossary_markdown=self._entity_glossary or "",
            mcp_digest_markdown=digest,
            session_metadata=self._session_meta(),
            tools_openai_payload=tp_payload,
            mcp_tools=self.tools,
            settings=st,
        )

    async def _build_system_package_async(self) -> tuple[str, str]:
        st = get_settings()
        digest = await self._digest_for_system_async()
        tp_payload = MAESTRO_TOOLS_ONLY if self.current_agent == "maestro" else None
        return build_system_package(
            agent=self.current_agent,
            skill_body=self.current_skill or "",
            entity_glossary_markdown=self._entity_glossary or "",
            mcp_digest_markdown=digest,
            session_metadata=self._session_meta(),
            tools_openai_payload=tp_payload,
            mcp_tools=self.tools,
            settings=st,
        )

    async def _openai_messages_for_turn(
        self,
        *,
        query_for_semantic: str,
        tools_payload: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        st = get_settings()
        embed_fn = getattr(self.model, "embed_texts", None)
        if not st.orchestrator_history_semantic_enabled or not callable(embed_fn):
            embed_fn = None
        msgs_work, _note = await build_compact_history_messages_for_llm(
            self.messages,
            self._session_meta(),
            embed_texts=embed_fn,
            query_fallback=query_for_semantic,
            settings=st,
        )
        orch_ctx = self._orchestrator_state_context_markdown()
        if orch_ctx:
            msgs_work = [
                {
                    "role": "user",
                    "content": (
                        "### Estado do host (ferramentas já executadas)\n\n"
                        f"{orch_ctx}\n\n### Fim do estado"
                    ),
                    "_orch_synthetic": True,
                },
                *msgs_work,
            ]
        if st.orchestrator_system_layer_split_enabled:
            core, ctx = await self._build_system_package_async()
            core = core.strip()
            ctx_st = (ctx or "").strip()
            if ctx_st:
                wrap = (
                    "### Contexto de apoio (somente leitura)\n\n"
                    + ctx_st
                    + "\n\n### Fim do contexto"
                )
                msgs_work = [
                    {"role": "user", "content": wrap, "_orch_synthetic": True},
                    *msgs_work,
                ]
            merged = _messages_with_skill(core, msgs_work)
            skill_est = core
        else:
            sys_t = await self._build_system_text_async()
            merged = _messages_with_skill(sys_t, msgs_work)
            skill_est = sys_t
        merged = shrink_chat_messages_to_budget(skill_est, merged, tools_payload, st)
        tlog = get_trace_logger()
        if tlog and st.orchestrator_trace_system_chars:
            et = estimate_full_prompt_tokens(skill_est, merged, tools_payload)
            tlog.record(
                "orchestrator.llm_payload.stats",
                estimated_prompt_tokens=et,
                system_est_chars=len(skill_est),
                payload_messages=len(merged),
                history_compact=st.orchestrator_history_compact_enabled,
                system_layer_split=st.orchestrator_system_layer_split_enabled,
            )
        return merged

    async def _observer_narrative(self, user_input: str, tools_used: list[dict[str, Any]]) -> None:
        st = get_settings()
        if not st.observer_agent_enabled or self._session_metadata is None:
            return
        path = Path(__file__).resolve().parent / "prompts" / "internal" / "observer.md"
        if not path.is_file():
            return
        system = path.read_text(encoding="utf-8").strip()
        payload = {
            "user_excerpt": user_input[:2000],
            "agent_final": self.current_agent,
            "tools_used": tools_used[-40:],
            "observer_events": (self._session_metadata.get("observer_log") or {}).get("entries", [])[-80:],
        }
        user = json.dumps(payload, ensure_ascii=False)[:120_000]
        model_o = (st.observer_agent_model or "").strip() or None
        try:
            with llm_phase_context("observer_narrative"):
                resp = await self.model.chat(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    tools=None,
                    model_override=model_o,
                )
            text = str((resp or {}).get("content") or "").strip()
            if not text:
                return
            cap = max(500, int(st.observer_narrative_max_chars))
            if len(text) > cap:
                text = text[:cap] + "…"
            slot = self._session_metadata.setdefault("observer_log", {})
            narr = slot.setdefault("narratives", [])
            narr.append(
                {
                    "ts": self._utc_iso(),
                    "markdown": text,
                }
            )
            nmax = max(1, int(st.observer_narratives_max))
            if len(narr) > nmax:
                del narr[0 : len(narr) - nmax]
        except Exception as e:
            _logger_orch.warning("observer narrative failed: %s", e)

    async def _run_f3_pipeline(
        self,
        result: dict[str, Any],
        user_input: str,
    ) -> dict[str, Any]:
        st = get_settings()
        md = self._session_meta()
        if self.current_agent == "maestro":
            return result
        assistant = result.get("assistant") or {}
        text = str(assistant.get("content") or "")
        digest = build_mcp_cache_digest_section(
            md,
            st,
            semantic_retrieval_markdown=self._semantic_retrieval_markdown,
        )

        if st.pipeline_verifier_enabled:
            try:
                v_skill, _ = self.skill_loader.load_skill("verificador")
            except (FileNotFoundError, ValueError):
                v_skill = "Verificador: valida números contra digest e responde VEREDITO: APROVADO|PARCIAL|REPROVADO."
            depth = (st.verification_depth or "smoke").strip()
            v_user = (
                f"Profundidade: {depth}\n\n"
                f"Pedido utilizador:\n{user_input[:4000]}\n\n"
                f"Resposta candidata:\n{text[:12000]}\n\n"
                f"Digest MCP:\n{digest[:8000]}"
            )
            try:
                mo_v = st.resolve_orchestrator_model_for_agent("verificador")
                with llm_phase_context("pipeline_verifier"):
                    v_resp = await self.model.chat(
                        [
                            {"role": "system", "content": v_skill},
                            {"role": "user", "content": v_user},
                        ],
                        tools=None,
                        model_override=mo_v,
                    )
                verdict = str((v_resp or {}).get("content") or "").strip()
                if verdict:
                    md["verification_status"] = verdict[:2000]
                    md["verification_raw"] = verdict
                    self._observer_append("pipeline_verifier", {"chars": len(verdict)})
            except Exception as e:
                _logger_orch.warning("verifier pipeline failed: %s", e)

        if st.pipeline_compositor_enabled:
            skip_c = (
                st.pipeline_skip_compositor_when_formatador_succeeds
                and bool(md.get("formatador_ui_applied"))
            )
            if skip_c:
                self._observer_append(
                    "pipeline_compositor",
                    {"skipped": True, "reason": "formatador_ui_applied"},
                )
            allow = not skip_c
            vs = str(md.get("verification_status") or "")
            if st.pipeline_verifier_enabled and "REPROVADO" in vs.upper():
                allow = False
            if allow:
                try:
                    c_skill, _ = self.skill_loader.load_skill("compositor_layout")
                except (FileNotFoundError, ValueError):
                    c_skill = (
                        "Compositor: devolve **só** JSON válido "
                        '{"version":1,"content_blocks":[{"type":"p","markdown":"..."}]}'
                    )
                c_user = f"Texto aprovado ou candidato:\n{text[:16000]}"
                try:
                    mo_c = st.resolve_orchestrator_model_for_agent("compositor_layout")
                    with llm_phase_context("pipeline_compositor"):
                        c_resp = await self.model.chat(
                            [
                                {"role": "system", "content": c_skill},
                                {"role": "user", "content": c_user},
                            ],
                            tools=None,
                            model_override=mo_c,
                        )
                    raw = str((c_resp or {}).get("content") or "").strip()
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            arr = None
                            for _k in ("content_blocks", "blocks"):
                                _v = parsed.get(_k)
                                if isinstance(_v, list):
                                    arr = _v
                                    break
                            if arr is not None:
                                md["layout_blocks"] = parsed
                                self._observer_append(
                                    "pipeline_compositor",
                                    {"blocks": len(arr)},
                                )
                    except json.JSONDecodeError:
                        md["layout_blocks"] = {"version": 1, "raw": raw[:8000]}
                except Exception as e:
                    _logger_orch.warning("compositor pipeline failed: %s", e)

        return result

    async def _llm_critical_evaluate(
        self,
        user_input: str,
        result: dict[str, Any],
    ):
        st = get_settings()
        try:
            skill, _ = self.skill_loader.load_skill("avaliador_critico")
        except (FileNotFoundError, ValueError):
            skill = (
                "Avaliador crítico. Responde **só** JSON: "
                '{"decisao":"APROVAR"|"DEVOLVER","justificativa_curta":"",'
                '"pontos_a_acrescentar":[],"exige_novos_dados":false,"exige_pesquisa_web":false}'
            )
        digest = await self._digest_for_system_async()
        text = str((result.get("assistant") or {}).get("content") or "")
        payload = {
            "pergunta": user_input[:6000],
            "resposta_candidata": text[:16000],
            "digest_mcp": digest[:12000],
        }
        mo = st.resolve_orchestrator_model_for_agent("avaliador_critico")
        try:
            with llm_phase_context("orchestrator:avaliador_critico"):
                resp = await self.model.chat(
                    [
                        {"role": "system", "content": skill},
                        {
                            "role": "user",
                            "content": json.dumps(payload, ensure_ascii=False)[:120_000],
                        },
                    ],
                    tools=None,
                    model_override=mo,
                )
            raw = str((resp or {}).get("content") or "")
        except Exception as e:
            _logger_orch.warning("critical evaluator failed: %s", e)
            raw = (
                '{"decisao":"APROVAR","justificativa_curta":"avaliador indisponível",'
                '"pontos_a_acrescentar":[]}'
            )
        return parse_critique_response(raw)

    async def _run_critique_refine_loop(
        self,
        result: dict[str, Any],
        user_input: str,
        tools_used: list[dict[str, Any]],
        step: int,
    ) -> tuple[dict[str, Any], int]:
        st = get_settings()
        if not st.pipeline_critical_evaluator_enabled:
            return result, step
        md = self._session_meta()
        max_dev = max(1, int(st.orchestrator_max_critique_rounds))
        devolutions = 0
        while True:
            print(
                f"🔄 [avaliador_critico] {self.current_agent} → avaliador_critico "
                f"(rodada {devolutions + 1}, max devoluções: {max_dev})"
            )
            verdict = await self._llm_critical_evaluate(user_input, result)
            md["critique_last"] = {
                "devolucoes_feitas": devolutions,
                "decisao": verdict.decisao,
                "justificativa_curta": verdict.justificativa_curta,
                "exige_novos_dados": verdict.exige_novos_dados,
                "exige_pesquisa_web": verdict.exige_pesquisa_web,
            }
            self._observer_append(
                "critique_evaluator",
                {"devolucoes": devolutions, "decisao": verdict.decisao},
            )
            print(
                f"🔄 [avaliador_critico] decisão: {verdict.decisao} "
                f"({verdict.justificativa_curta[:120] + '…' if len(verdict.justificativa_curta) > 120 else verdict.justificativa_curta})"
            )
            if verdict.aprovar:
                return result, step
            if devolutions >= max_dev:
                md["critique_forced_stop"] = True
                note = (
                    "\n\n*[Resposta após o máximo de devoluções do avaliador "
                    f"({max_dev}); pode haver lacunas.]*"
                )
                ac = dict(result.get("assistant") or {})
                ac["content"] = str(ac.get("content") or "") + note
                result = {**result, "assistant": ac}
                return result, step
            devolutions += 1
            print(
                f"🔄 [avaliador_critico] DEVOLVER → voltar a {self.current_agent} "
                f"(tools={'sim' if (verdict.exige_novos_dados or verdict.exige_pesquisa_web) else 'não'})"
            )
            self._append_message({
                "role": "system",
                "content": format_critique_message(verdict),
            })
            tools_payload: list[dict[str, Any]] | None = None
            if verdict.exige_novos_dados or verdict.exige_pesquisa_web:
                tools_payload = self._tools_payload_for_specialist()
            result, step = await self._run_specialist_loop(
                tools_payload, tools_used, step
            )

    async def _run_formatador_ui(
        self,
        result: dict[str, Any],
        user_input: str,
    ) -> dict[str, Any]:
        st = get_settings()
        if not st.pipeline_formatador_ui_enabled:
            return result
        md = self._session_meta()
        text = str((result.get("assistant") or {}).get("content") or "")
        if not text.strip():
            return result
        _disp, blocks_existing = split_reply_and_blocks(text)
        if blocks_existing is not None:
            md["formatador_ui_applied"] = True
            md["layout_blocks"] = blocks_existing
            self._observer_append(
                "formatador_ui",
                {"has_blocks": True, "shortcut": True},
            )
            return result
        fm: SkillMetadata | None = None
        try:
            skill, fm = self.skill_loader.load_skill("formatador_ui")
        except (FileNotFoundError, ValueError):
            skill = (
                "Formatador UI: preserva factos; no fim um fenced ```json com "
                '{"version":1,"content_blocks":[{"type":"paragraph","text":"..."}]}'
            )
        mo = st.resolve_orchestrator_model_for_agent("formatador_ui")
        if (mo is None or not str(mo).strip()) and fm is not None:
            sm = str(fm.model or "").strip()
            if sm:
                mo = sm
        u = (
            "Pedido original (contexto):\n"
            + user_input[:4000]
            + "\n\nTexto aprovado a formatar:\n"
            + text[:24000]
        )
        print(f"🔄 [formatador_ui] {self.current_agent} → formatador_ui (chamada ao modelo)")
        try:
            with llm_phase_context("orchestrator:formatador_ui"):
                resp = await asyncio.wait_for(
                    self.model.chat(
                        [
                            {"role": "system", "content": skill},
                            {"role": "user", "content": u},
                        ],
                        tools=None,
                        model_override=mo,
                    ),
                    timeout=float(st.formatador_ui_timeout_seconds),
                )
            out = str((resp or {}).get("content") or "").strip()
        except asyncio.TimeoutError:
            _logger_orch.warning("formatador_ui timeout after %.1fs", st.formatador_ui_timeout_seconds)
            return result
        except Exception as e:
            _logger_orch.warning("formatador_ui failed: %s", e)
            return result
        if not out:
            return result
        _, blocks = split_reply_and_blocks(out)
        ac = dict(result.get("assistant") or {})
        ac["content"] = out
        result = {**result, "assistant": ac}
        if blocks is not None:
            md["formatador_ui_applied"] = True
            md["layout_blocks"] = blocks
        self._observer_append("formatador_ui", {"has_blocks": blocks is not None})
        return result

    async def _refresh_entity_glossary(self, session_id: UUID | None = None) -> None:
        st = get_settings()
        tlog = get_trace_logger()
        if not st.entity_glossary_enabled:
            self._entity_glossary = ""
            _logger_orch.info("entity_glossary skipped: entity_glossary_enabled=false")
            if tlog:
                tlog.record(
                    "orchestrator.entity_glossary.skipped",
                    reason="entity_glossary_enabled_false",
                )
            return
        if self.client is None or self.client.session is None:
            self._entity_glossary = ""
            _logger_orch.warning("entity_glossary skipped: MCP client session not ready")
            if tlog:
                tlog.record(
                    "orchestrator.entity_glossary.skipped",
                    reason="mcp_session_not_ready",
                )
            return
        cached = self._glossary_cache_get(session_id)
        if cached is not None and cached.strip():
            self._entity_glossary = cached
            stats_out = {
                "glossary_chars_in_memory": len(self._entity_glossary or ""),
                "skill_base_chars": len(self.current_skill or ""),
                "effective_system_text_chars": len(self._build_system_text_sync()),
                "glossary_source": "session_cache",
            }
            _logger_orch.info(
                "entity_glossary from session cache: chars=%s",
                stats_out["glossary_chars_in_memory"],
            )
            if tlog:
                tlog.record("orchestrator.entity_glossary.loaded", **stats_out)
            return
        gql_args = {
            "max_chars": st.entity_glossary_max_chars,
            "include_demais_registos": st.entity_glossary_include_demais_registos,
        }
        gname = st.entity_glossary_mcp_tool
        if self._use_mcp_session_cache() and self._session_metadata is not None:
            ck_g = mcp_cache_key(gname, gql_args)
            hit_g = find_cache_entry(self._session_metadata, ck_g)
            if hit_g and hit_g.get("result_text"):
                try:
                    data_g = json.loads(str(hit_g["result_text"]))
                    if isinstance(data_g, dict) and "markdown" in data_g:
                        markdown_g = str(data_g.get("markdown", ""))
                        self._entity_glossary = markdown_g
                        self._glossary_cache_set(session_id, markdown_g)
                        self._observer_append(
                            "tool_cache_hit",
                            {"tool": gname},
                        )
                        stats_out = {
                            "glossary_chars_in_memory": len(self._entity_glossary or ""),
                            "skill_base_chars": len(self.current_skill or ""),
                            "effective_system_text_chars": len(self._build_system_text_sync()),
                            "glossary_source": "mcp_session_cache",
                        }
                        _logger_orch.info(
                            "entity_glossary from mcp_tool_cache: chars=%s",
                            stats_out["glossary_chars_in_memory"],
                        )
                        if tlog:
                            tlog.record("orchestrator.entity_glossary.loaded", **stats_out)
                        return
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
        try:
            mcp_result = await self._call_mcp_tool_bounded(gname, gql_args)
            raw = _mcp_result_to_text(mcp_result)
            if mcp_result.isError:
                raise RuntimeError(raw or "get_entity_glossary_markdown isError")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError(f"glossário MCP: JSON inválido: {type(data)}")
            if "markdown" not in data:
                raise RuntimeError(str(data.get("error", "resposta MCP sem markdown")))
            markdown = str(data.get("markdown", ""))
            raw_stats = data.get("stats")
            stats = raw_stats if isinstance(raw_stats, dict) else {}
            self._entity_glossary = markdown
            self._glossary_cache_set(session_id, markdown)
            if not tool_excluded_from_state_store(gname):
                put_tool_result(
                    self._orch_state_block(),
                    str(gname),
                    gql_args,
                    raw,
                    is_error=False,
                )
            if self._use_mcp_session_cache() and self._session_metadata is not None and not mcp_result.isError:
                append_cache_entry(
                    self._session_metadata,
                    cache_key=mcp_cache_key(gname, gql_args),
                    tool_name=gname,
                    args=gql_args,
                    result_text=raw,
                )
                self._observer_append("tool_call", {"tool": gname, "source": "mcp"})
            stats_out = {
                **stats,
                "glossary_chars_in_memory": len(self._entity_glossary or ""),
                "skill_base_chars": len(self.current_skill or ""),
                "effective_system_text_chars": len(self._build_system_text_sync()),
                "glossary_source": "mcp_tool",
            }
            _logger_orch.info("entity_glossary loaded (counts/stats): %s", stats)
            _logger_orch.info(
                "entity_glossary fused into system text: glossary_chars=%s skill_chars=%s merged_chars=%s",
                stats_out["glossary_chars_in_memory"],
                stats_out["skill_base_chars"],
                stats_out["effective_system_text_chars"],
            )
            if tlog:
                tlog.record("orchestrator.entity_glossary.loaded", **stats_out)
        except Exception as e:
            self._entity_glossary = ""
            err_s = str(e)
            if "2003" in err_s or "Can't connect to MySQL" in err_s:
                _logger_orch.warning(
                    "entity_glossary load failed: MySQL inalcançável (Settings.mysql_host=%r). "
                    "O subprocesso MCP carrega project_mcp_v1/.env com override; se o host no .env "
                    "for localhost/127.0.0.1, o servidor MySQL tem de escutar aí ou altere MYSQL_HOST "
                    "(ex.: nome do serviço Docker, IP da máquina). Erro: %s",
                    st.mysql_host,
                    e,
                    exc_info=True,
                )
            else:
                _logger_orch.warning("entity_glossary load failed: %s", e, exc_info=True)
            if tlog:
                tlog.record(
                    "orchestrator.entity_glossary.failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )

    def _append_message(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)
        self._message_times.append(time.time())

    def _strip_leading_orphan_tools(self) -> None:
        strip_leading_orphan_tools(self.messages, self._message_times)

    def _estimate_tools_tokens(self) -> int:
        """Tokens aproximados do bloco `tools` enviado ao modelo no passo atual."""
        if self.current_agent == "maestro":
            return _estimate_tokens_from_tool_dicts(MAESTRO_TOOLS_ONLY)
        if not self.tools:
            return 0
        total = 128  # cabeçalho / estrutura do bloco tools
        for t in self.tools:
            try:
                total += _estimate_tokens_from_text(t.model_dump_json())
            except Exception:
                total += _estimate_tokens_from_text(str(t))
        return total

    def _effective_input_token_cap(self) -> int | None:
        """
        Limite estimado para mensagens + SKILL, reservando max_tokens da resposta
        e o custo declarado das ferramentas dentro de context_budget.
        """
        meta = self.current_metadata
        if meta is None or meta.context_budget <= 0:
            return None
        reserved_out = max(0, meta.max_tokens)
        tools_est = self._estimate_tools_tokens()
        margin = max(0, int(get_settings().orchestrator_context_budget_safety_margin))
        available = (
            meta.context_budget
            - reserved_out
            - tools_est
            - margin
        )
        # Mantém um mínimo para não esvaziar o histórico por arredondamento agressivo.
        return max(256, available)

    def _prune_messages(self) -> None:
        """TTL por segmento; poda por segmentos só acima do limiar de tokens (ou cap / tecto de mensagens)."""
        if len(self.messages) != len(self._message_times):
            self._message_times = [time.time() for _ in self.messages]

        st = get_settings()
        now = time.time()
        cutoff = now - float(st.orchestrator_max_message_age_seconds)

        while (
            self.messages
            and self._message_times
            and self._message_times[0] < cutoff
            and not self.messages[0].get("_orch_anchor")
        ):
            if not pop_first_segment(self.messages, self._message_times):
                self.messages.pop(0)
                self._message_times.pop(0)
            self._strip_leading_orphan_tools()

        self._strip_leading_orphan_tools()

        cap = self._effective_input_token_cap()
        t_thr = max(1, int(st.orchestrator_history_prune_token_threshold))
        a_tgt = max(256, int(t_thr * float(st.orchestrator_history_prune_target_fraction)))
        abs_cap = max(100, int(st.orchestrator_history_abs_message_cap))
        respect = st.orchestrator_history_prune_respect_skill_budget

        def _est() -> int:
            return _estimate_prompt_tokens_messages_plus_skill(
                self._build_system_text_sync(),
                self.messages,
            )

        while self.messages:
            self._strip_leading_orphan_tools()
            e = _est()
            ln = len(self.messages)
            hard_len = ln > abs_cap
            hard_cap = bool(respect and cap is not None and e > int(cap))
            soft = e > t_thr
            if not hard_len and not hard_cap and not soft:
                break
            if soft and e <= a_tgt and not hard_len and not hard_cap:
                break
            if self.messages[0].get("_orch_anchor"):
                break
            if not pop_first_segment(self.messages, self._message_times):
                self.messages.pop(0)
                self._message_times.pop(0)
            self._strip_leading_orphan_tools()

        self._strip_leading_orphan_tools()

    def _cap_messages(self) -> None:
        self._prune_messages()

    async def _prepare_agent_for_run(
        self,
        *,
        auto_route: bool,
        target_agent: AgentType | None,
    ) -> None:
        if auto_route:
            continuing_specialist = (
                self.current_agent != "maestro" and len(self.messages) > 0
            )
            if not continuing_specialist:
                await self.set_agent("maestro")
        else:
            assert target_agent is not None
            await self.set_agent(target_agent)

    def _tools_payload_for_chat(self) -> list[dict[str, Any]] | None:
        if not self.tools:
            return None
        return [tool.model_dump() for tool in self.tools]

    def _tools_payload_for_specialist(self) -> list[dict[str, Any]] | None:
        """Tools MCP no formato OpenAI, com allowlist opcional por agente (``orchestrator_tool_allowlist_json``)."""
        base = self._tools_payload_for_chat()
        if not base:
            base = []
        st = get_settings()
        if self.current_agent not in SPECIALIST_AGENTS:
            out = base
        else:
            mp = st.specialist_mcp_tool_allowlist()
            allow = mp.get(str(self.current_agent))
            if not allow:
                out = list(base)
            else:
                out = []
                for t in base:
                    fn = t.get("function") if isinstance(t.get("function"), dict) else None
                    name = (fn.get("name") if fn else None) or t.get("name")
                    if name and str(name) in allow:
                        out.append(t)
                if not out:
                    out = list(base)
        if (
            st.analytics_aggregate_session_enabled
            and self.current_agent in SPECIALIST_AGENTS
            and self._use_mcp_session_cache()
        ):
            out = list(out)
            out.append(analytics_aggregate_session_openai_tool())
        return out if out else None

    @staticmethod
    def _maestro_tool_choice_dict() -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": ROUTE_TO_SPECIALIST_TOOL_NAME},
        }

    def _maestro_terminal_response(
        self,
        content: str,
        tools_used: list[dict[str, Any]],
        agent: AgentType,
    ) -> dict[str, Any]:
        return {
            "assistant": {"role": "assistant", "content": content},
            "tools_used": tools_used,
            "agent": agent,
        }

    async def _run_maestro_routing_phase(
        self,
        user_input: str,
        tools_used: list[dict[str, Any]],
        step: int,
        session_id: UUID | None = None,
    ) -> tuple[dict[str, Any] | None, int]:
        """
        Loop do Maestro até handoff para especialista.
        Retorna (resposta_terminal, step) — se resposta_terminal não for None, o caller deve
        devolvê-la imediatamente; caso contrário segue para o loop do especialista.
        """
        maestro_tool_choice = self._maestro_tool_choice_dict()
        st_m = get_settings()
        max_rounds_m = max(1, int(st_m.orchestrator_max_tool_rounds))
        mo_maestro = st_m.resolve_orchestrator_model_for_agent("maestro")
        while self.current_agent == "maestro":
            step += 1
            if step > max_rounds_m:
                raise RuntimeError(
                    f"Limite de {max_rounds_m} rodadas do agente excedido."
                )

            self._cap_messages()
            chat_messages = await self._openai_messages_for_turn(
                query_for_semantic=user_input,
                tools_payload=MAESTRO_TOOLS_ONLY,
            )
            with llm_phase_context("orchestrator:maestro"):
                response = await self.model.chat(
                    messages=chat_messages,
                    tools=MAESTRO_TOOLS_ONLY,
                    tool_choice=maestro_tool_choice,
                    model_override=mo_maestro,
                )
            tool_calls = response.get("tool_calls") or []
            tlm = get_trace_logger()
            if tlm:
                tlm.record("orchestrator.maestro.llm_turn", tool_calls=tool_calls)

            routed = False
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name")
                if name != ROUTE_TO_SPECIALIST_TOOL_NAME:
                    continue
                args = _parse_tool_arguments(fn.get("arguments"))
                try:
                    specialist = parse_route_arguments(args)
                except ValueError as e:
                    return (
                        self._maestro_terminal_response(
                            (
                                "Não foi possível rotear o pedido: argumentos inválidos na "
                                f"ferramenta de roteamento ({e})."
                            ),
                            tools_used,
                            self.current_agent,
                        ),
                        step,
                    )
                tools_used.append({
                    "name": ROUTE_TO_SPECIALIST_TOOL_NAME,
                    "arguments": args,
                    "ok": True,
                    "error": None,
                    "result_preview": f"handoff → {specialist}",
                })
                print(f"🎯 Handoff: maestro → {specialist}")
                self._observer_append("handoff", {"to": specialist, "args": args})
                await self.set_agent(specialist)
                stg = get_settings()
                if (
                    specialist == "analise_os"
                    and stg.entity_glossary_enabled
                    and stg.entity_glossary_on_handoff
                ):
                    await self._refresh_entity_glossary(session_id)
                self._append_message({
                    "role": "user",
                    "content": user_input,
                })
                routed = True
                break

            if routed:
                break

            if not tool_calls:
                fb = specialist_from_text_fallback(response.get("content") or "")
                if fb is not None:
                    tools_used.append({
                        "name": ROUTE_TO_SPECIALIST_TOOL_NAME,
                        "arguments": {"agent": fb, "reason": "fallback_text_token"},
                        "ok": True,
                        "error": None,
                        "result_preview": f"handoff (fallback texto) → {fb}",
                    })
                    print(f"🎯 Handoff (fallback texto): maestro → {fb}")
                    self._observer_append("handoff", {"to": fb, "reason": "fallback_text_token"})
                    await self.set_agent(fb)
                    stg = get_settings()
                    if (
                        fb == "analise_os"
                        and stg.entity_glossary_enabled
                        and stg.entity_glossary_on_handoff
                    ):
                        await self._refresh_entity_glossary(session_id)
                    self._append_message({
                        "role": "user",
                        "content": user_input,
                    })
                    break
                return (
                    self._maestro_terminal_response(
                        (
                            "Não foi possível determinar o agente especializado. "
                            "Reformula a pergunta ou indica ``target_agent`` no pedido HTTP."
                        ),
                        tools_used,
                        "maestro",
                    ),
                    step,
                )

            return (
                self._maestro_terminal_response(
                    (
                        "Resposta inesperada do Maestro (sem roteamento válido). "
                        "Tenta de novo ou usa ``target_agent`` explícito."
                    ),
                    tools_used,
                    "maestro",
                ),
                step,
            )

        return (None, step)

    async def _execute_analytics_aggregate_session_tool(
        self,
        tc_id: str,
        args: dict[str, Any],
        tools_used: list[dict[str, Any]],
    ) -> None:
        st = get_settings()
        preview_cap = max(1, int(st.orchestrator_tool_result_preview_max))

        def _fail(msg: str) -> None:
            tools_used.append({
                "name": ANALYTICS_AGGREGATE_SESSION_TOOL_NAME,
                "arguments": args,
                "ok": False,
                "error": msg,
                "result_preview": msg[:preview_cap],
            })
            self._append_message({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": json.dumps(
                    {"ok": False, "error": msg},
                    ensure_ascii=False,
                ),
            })

        if not st.analytics_aggregate_session_enabled:
            _fail("analytics_aggregate_session desactivado na configuração")
            return
        if not self._use_mcp_session_cache() or self._session_metadata is None:
            _fail("sessão sem metadata/cache — agregação indisponível")
            return
        if not increment_aggregate_calls(self._session_metadata, st):
            _fail("limite de chamadas analytics_aggregate_session por sessão excedido")
            return

        ds_id = str(args.get("session_dataset_id") or "").strip()
        group_by = args.get("group_by")
        aggregations = args.get("aggregations")
        if not ds_id:
            _fail("session_dataset_id obrigatório")
            return
        if not isinstance(group_by, list) or not group_by:
            _fail("group_by deve ser array não vazio")
            return
        if not isinstance(aggregations, list) or not aggregations:
            _fail("aggregations deve ser array não vazio")
            return
        gb = [str(x) for x in group_by]
        ag_list: list[dict[str, str]] = []
        for a in aggregations:
            if not isinstance(a, dict):
                _fail("cada agregação deve ser objecto")
                return
            op = str(a.get("op") or "").lower()
            col = str(a.get("column") or "")
            if op not in ("sum", "mean", "min", "max", "count"):
                _fail(f"op inválida: {op}")
                return
            if op == "count" and not col:
                ag_list.append({"op": "count", "column": ""})
            else:
                if not col:
                    _fail("column obrigatória para esta op")
                    return
                ag_list.append({"op": op, "column": col})

        filters_raw = args.get("filters")
        filters: list[dict[str, Any]] = []
        if filters_raw is not None:
            if not isinstance(filters_raw, list):
                _fail("filters deve ser array")
                return
            for f in filters_raw:
                if not isinstance(f, dict):
                    _fail("cada filtro deve ser objecto")
                    return
                filters.append(
                    {
                        "column": str(f.get("column") or ""),
                        "op": str(f.get("op") or "").lower(),
                        "value": f.get("value"),
                    }
                )

        sort_by = args.get("sort_by")
        sort_dir = str(args.get("sort_dir") or "desc")
        top_k = args.get("top_k")
        tk: int | None = None
        if top_k is not None:
            try:
                tk = int(top_k)
            except (TypeError, ValueError):
                _fail("top_k inválido")
                return
            if tk < 1:
                _fail("top_k deve ser ≥ 1")
                return
            if tk > int(st.analytics_aggregate_top_k_max):
                _fail(f"top_k acima do máximo permitido ({st.analytics_aggregate_top_k_max})")
                return

        timeout = float(st.analytics_aggregate_timeout_seconds)

        def _work() -> dict[str, Any]:
            assert self._session_metadata is not None
            rows, meta = load_dataset_for_aggregate(
                self._session_metadata,
                ds_id,
                st,
            )
            if rows is None:
                return {"ok": False, "error": meta.get("error", "load_failed")}
            sample_only = bool(meta.get("sample_only"))
            qid = str(meta.get("query_id") or "")
            for g in gb:
                if g not in rows[0]:
                    return {"ok": False, "error": f"group_by_desconhecido:{g}"}
            for f in filters:
                if f["column"] not in rows[0]:
                    return {"ok": False, "error": f"filtro_coluna:{f['column']}"}
            return run_analytics_aggregate(
                rows,
                group_by=gb,
                aggregations=ag_list,
                filters=filters,
                sort_by=str(sort_by) if sort_by else None,
                sort_dir=sort_dir,
                top_k=tk,
                sample_only=sample_only,
                query_id=qid,
            )

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=timeout)
        except asyncio.TimeoutError:
            _fail("timeout na agregação")
            return
        except Exception as e:
            _logger_orch.warning("analytics_aggregate_session error: %s", e)
            _fail("erro_interno_agregação")
            return

        text = json.dumps(result, ensure_ascii=False, default=str)
        tools_used.append({
            "name": ANALYTICS_AGGREGATE_SESSION_TOOL_NAME,
            "arguments": args,
            "ok": bool(result.get("ok")),
            "error": None if result.get("ok") else str(result.get("error")),
            "result_preview": text[:preview_cap],
        })
        self._observer_append(
            "aggregate_session",
            {
                "session_dataset_id": ds_id,
                "ok": bool(result.get("ok")),
                "groups_out": result.get("row_count") if isinstance(result, dict) else None,
            },
        )
        max_tool = max(4096, int(st.tool_message_content_max_chars))
        if len(text) > max_tool:
            text = safe_truncate_tool_content(text, max_tool)
        self._append_message({
            "role": "tool",
            "tool_call_id": tc_id,
            "content": text,
        })

    async def _execute_single_tool_call(
        self,
        tc: dict[str, Any],
        tools_used: list[dict[str, Any]],
        *,
        mcp_result_override: CallToolResult | None = None,
    ) -> None:
        tc_id = tc.get("id") or ""
        fn = tc.get("function") or {}
        name = fn.get("name")

        if not name:
            tlog = get_trace_logger()
            if tlog:
                tlog.record("orchestrator.tool.missing_name", tool_call=tc)
            self._append_message({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": "Erro: nome da ferramenta ausente na resposta do modelo.",
            })
            tools_used.append({
                "name": None,
                "arguments": {},
                "ok": False,
                "error": "nome da ferramenta ausente",
                "result_preview": None,
            })
            return

        args = _parse_tool_arguments(fn.get("arguments"))

        if name == ANALYTICS_AGGREGATE_SESSION_TOOL_NAME:
            await self._execute_analytics_aggregate_session_tool(tc_id, args, tools_used)
            return

        if name == ROUTE_TO_SPECIALIST_TOOL_NAME and self.current_agent != "maestro":
            msg = (
                "Roteamento entre agentes só é feito pelo Maestro (pedido HTTP sem "
                "`target_agent`). Como agente especialista, não podes usar "
                "`route_to_specialist`. Resolve o pedido com as ferramentas MCP "
                "disponíveis ou explica ao utilizador o que não consegues fazer "
                "neste papel."
            )
            print(
                f"⛔ [{self.current_agent}] Bloqueado: {name} "
                "(apenas Maestro pode rotear)"
            )
            tlog = get_trace_logger()
            if tlog:
                tlog.record(
                    "orchestrator.tool.blocked",
                    agent=self.current_agent,
                    tool=name,
                    arguments=args,
                )
            tools_used.append({
                "name": name,
                "arguments": args,
                "ok": False,
                "error": "route_to_specialist não permitido fora do Maestro",
                "result_preview": None,
            })
            self._append_message({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": msg,
            })
            return

        _exec_label = str(name)
        if name == "run_analytics_query":
            qid = args.get("query_id")
            if qid is not None and str(qid).strip():
                _exec_label = f"{name} query_id={qid!r}"
        print(f"⚙️  [{self.current_agent}] Executing: {_exec_label}")

        st_exec = get_settings()
        preview_cap = max(1, int(st_exec.orchestrator_tool_result_preview_max))

        use_cache = self._use_mcp_session_cache() and name != ROUTE_TO_SPECIALIST_TOOL_NAME
        ck_tool = mcp_cache_key(name, args) if use_cache else ""

        if not tool_excluded_from_state_store(str(name)):
            st_hit = find_tool_result_text(self._orch_state_block(), str(name), args)
            if st_hit:
                base_st, is_err = st_hit
                self._observer_append(
                    "orchestrator_state_hit",
                    {"tool": name, "is_error": is_err},
                )
                content = "[orch_state_hit]\n" + base_st
                preview = content[:preview_cap]
                if len(content) > preview_cap:
                    preview += "…"
                tools_used.append({
                    "name": name,
                    "arguments": args,
                    "ok": not is_err,
                    "error": None if not is_err else (base_st or "isError"),
                    "result_preview": preview,
                    "orchestrator_state_hit": True,
                })
                st_tool = get_settings()
                max_tool = max(4096, int(st_tool.tool_message_content_max_chars))
                if len(content) > max_tool:
                    content = safe_truncate_tool_content(content, max_tool, cache_key=ck_tool)
                self._append_message({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": content,
                })
                return

        if use_cache and self._session_metadata is not None:
            hit = find_cache_entry(self._session_metadata, ck_tool)
            if hit and hit.get("result_text"):
                self._observer_append(
                    "tool_cache_hit",
                    {"tool": name, "cache_key_prefix": ck_tool[:16]},
                )
                base_hit = str(hit["result_text"])
                if (
                    name == "run_analytics_query"
                    and self._session_metadata is not None
                    and '"session_dataset_id"' not in base_hit
                ):
                    ds_hit = get_dataset_id_for_cache_key(
                        self._session_metadata, ck_tool
                    )
                    if ds_hit:
                        root = self._session_metadata.get("analytics_datasets") or {}
                        inf = (root.get("by_id") or {}).get(ds_hit)
                        if isinstance(inf, dict):
                            base_hit = inject_dataset_handles_into_json_text(
                                base_hit,
                                session_dataset_id=ds_hit,
                                sample_only=bool(inf.get("sample_only")),
                            )
                if not tool_excluded_from_state_store(str(name)):
                    put_tool_result(
                        self._orch_state_block(),
                        str(name),
                        args,
                        base_hit,
                        is_error=False,
                    )
                content = "[cache_hit]\n" + base_hit
                preview = content[:preview_cap]
                if len(content) > preview_cap:
                    preview += "…"
                tools_used.append({
                    "name": name,
                    "arguments": args,
                    "ok": True,
                    "error": None,
                    "result_preview": preview,
                    "cache_hit": True,
                })
                st_tool = get_settings()
                max_tool = max(4096, int(st_tool.tool_message_content_max_chars))
                if len(content) > max_tool:
                    content = safe_truncate_tool_content(content, max_tool, cache_key=ck_tool)
                self._append_message({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": content,
                })
                return

        if name == "context_retrieve_similar" and self._session_metadata is not None:
            q_arg = str(args.get("query") or "").strip()
            s_arg = str(args.get("session_id") or "").strip().lower()
            host_q = str(
                self._session_metadata.get("_host_retrieve_query_normalized") or ""
            ).strip()
            host_sid = str(
                self._session_metadata.get("_host_retrieve_session_id") or ""
            ).strip().lower()
            cached = self._session_metadata.get("_host_context_retrieve_full_json")
            if cached and host_q == q_arg and host_sid == s_arg:
                content = str(cached)
                preview = content[:preview_cap]
                if len(content) > preview_cap:
                    preview += "…"
                tools_used.append({
                    "name": name,
                    "arguments": args,
                    "ok": True,
                    "error": None,
                    "result_preview": preview,
                    "host_retrieve_deduped": True,
                })
                self._observer_append(
                    "tool_context_retrieve_deduped",
                    {"tool": name},
                )
                if not tool_excluded_from_state_store(str(name)):
                    put_tool_result(
                        self._orch_state_block(),
                        str(name),
                        args,
                        content,
                        is_error=False,
                    )
                max_tool_d = max(4096, int(st_exec.tool_message_content_max_chars))
                if len(content) > max_tool_d:
                    content = safe_truncate_tool_content(
                        content,
                        max_tool_d,
                        cache_key=ck_tool if use_cache else None,
                    )
                self._append_message({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": content,
                })
                return

        try:
            self._observer_append("tool_cache_miss", {"tool": name})
            if mcp_result_override is not None:
                mcp_result = mcp_result_override
            else:
                mcp_result = await self._call_mcp_tool_bounded(name, args)
            content = _mcp_result_to_text(mcp_result)
            preview = content[:preview_cap]
            if len(content) > preview_cap:
                preview += "…"
            tools_used.append({
                "name": name,
                "arguments": args,
                "ok": not mcp_result.isError,
                "error": None if not mcp_result.isError else (content or "isError"),
                "result_preview": preview,
            })
            if use_cache and self._session_metadata is not None and not mcp_result.isError:
                if name == "run_analytics_query":
                    st_ds = get_settings()
                    if st_ds.analytics_session_datasets_enabled:
                        ds_new = register_run_analytics_result(
                            self._session_metadata,
                            full_result_text=content,
                            args=args,
                            cache_key=ck_tool,
                            session_id=self._session_id_for_cache,
                            settings=st_ds,
                        )
                        if ds_new:
                            root = self._session_metadata.get("analytics_datasets") or {}
                            inf = (root.get("by_id") or {}).get(ds_new) or {}
                            content = inject_dataset_handles_into_json_text(
                                content,
                                session_dataset_id=ds_new,
                                sample_only=bool(inf.get("sample_only")),
                            )
                            self._observer_append(
                                "dataset_registered",
                                {
                                    "session_dataset_id": ds_new,
                                    "query_id": args.get("query_id"),
                                },
                            )
                append_cache_entry(
                    self._session_metadata,
                    cache_key=ck_tool,
                    tool_name=str(name),
                    args=args,
                    result_text=content,
                )
                self._observer_append("tool_call", {"tool": name, "source": "mcp"})
            if not tool_excluded_from_state_store(str(name)):
                put_tool_result(
                    self._orch_state_block(),
                    str(name),
                    args,
                    content,
                    is_error=bool(mcp_result.isError),
                )
        except Exception as e:
            content = f"Erro ao chamar a ferramenta: {e}"
            tools_used.append({
                "name": name,
                "arguments": args,
                "ok": False,
                "error": str(e),
                "result_preview": None,
            })
            self._observer_append("error", {"tool": name, "error": str(e)})
            if not tool_excluded_from_state_store(str(name)):
                put_tool_result(
                    self._orch_state_block(),
                    str(name),
                    args,
                    content,
                    is_error=True,
                )

        st_tool = get_settings()
        max_tool = max(4096, int(st_tool.tool_message_content_max_chars))
        if len(content) > max_tool:
            content = safe_truncate_tool_content(
                content,
                max_tool,
                cache_key=ck_tool if use_cache else None,
            )

        self._append_message({
            "role": "tool",
            "tool_call_id": tc_id,
            "content": content,
        })

    @staticmethod
    def _fast_skeleton_allowed_tool_names(
        tools_payload: list[dict[str, Any]] | None,
    ) -> frozenset[str]:
        names: set[str] = set()
        if not tools_payload:
            return frozenset()
        for t in tools_payload:
            fn = t.get("function") if isinstance(t.get("function"), dict) else None
            n = (fn.get("name") if fn else None) or t.get("name")
            if n:
                names.add(str(n))
        return frozenset(names)

    def _parse_fast_skeleton_plan_json(self, raw: str) -> list[dict[str, Any]] | None:
        s = (raw or "").strip()
        if not s:
            return None
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z0-9]*\s*\n?", "", s)
            s = re.sub(r"\n?```\s*$", "", s).strip()
        brace = s.find("{")
        if brace < 0:
            return None
        s2 = s[brace:]
        end = s2.rfind("}")
        if end < 0:
            return None
        s2 = s2[: end + 1]
        try:
            data = json.loads(s2)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        pt = data.get("planned_tools")
        if pt is None or not isinstance(pt, list):
            return None
        out: list[dict[str, Any]] = []
        for it in pt:
            if isinstance(it, dict):
                out.append(it)
        return out

    @staticmethod
    def _validate_fast_skeleton_plan(
        planned: list[dict[str, Any]],
        allowed: frozenset[str],
        max_items: int,
    ) -> list[dict[str, Any]] | None:
        out: list[dict[str, Any]] = []
        for item in planned[:max_items]:
            if not isinstance(item, dict):
                return None
            name = str(item.get("name") or "").strip()
            if name not in allowed:
                return None
            args = item.get("arguments")
            if args is None:
                args = {}
            elif not isinstance(args, dict):
                return None
            out.append({"name": name, "arguments": args})
        return out

    @staticmethod
    def _synthetic_tool_calls_from_plan(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for p in plan:
            tid = f"call_fs_{uuid4().hex[:26]}"
            tool_calls.append(
                {
                    "id": tid,
                    "type": "function",
                    "function": {
                        "name": p["name"],
                        "arguments": json.dumps(
                            p.get("arguments") or {},
                            ensure_ascii=False,
                        ),
                    },
                }
            )
        return tool_calls

    async def _run_specialist_fast_skeleton(
        self,
        tools_payload: list[dict[str, Any]] | None,
        tools_used: list[dict[str, Any]],
        step: int,
    ) -> tuple[dict[str, Any], int]:
        """
        Plano JSON (sem tools na API) → ``tool_calls`` sintéticos → dispatch MCP → síntese.
        Se o plano for inválido, faz fallback para ``_run_specialist_loop``.
        """
        allowed = self._fast_skeleton_allowed_tool_names(tools_payload)
        st_sp = get_settings()
        mo_spec = st_sp.resolve_orchestrator_model_for_agent(self.current_agent)
        max_items = 6

        analise(
            "fast_skeleton_início",
            agent=self.current_agent,
            tools_allowlist_n=len(allowed),
            tools_allowlist_amostra=sorted(allowed)[:20],
            modelo=mo_spec,
        )

        self._cap_messages()
        base_msgs = await self._openai_messages_for_turn(
            query_for_semantic=latest_user_text_for_semantic(self.messages),
            tools_payload=tools_payload,
        )
        names_sorted = sorted(allowed)
        names_hint = ", ".join(names_sorted[:72])
        if len(names_sorted) > 72:
            names_hint += ", …"
        plan_user = (
            "Planeamento interno (modo fast_skeleton): devolve APENAS um objecto JSON válido "
            '(sem cercas markdown) no formato {"planned_tools":[{"name":"<nome>","arguments":{}}]} '
            f"com no máximo {max_items} ferramentas. "
            f"Nomes permitidos: {names_hint}. "
            'Se não precisares de ferramentas, usa {"planned_tools":[]}.'
        )
        plan_messages = [
            *base_msgs,
            {"role": "user", "content": plan_user, "_orch_synthetic": True},
        ]

        planned_raw: list[dict[str, Any]] | None = None
        try:
            with llm_phase_context(f"orchestrator:specialist:{self.current_agent}:fast_plan"):
                plan_resp = await self.model.chat(
                    plan_messages,
                    tools=None,
                    model_override=mo_spec,
                )
            raw_text = str((plan_resp or {}).get("content") or "").strip()
            analise(
                "fast_skeleton_resposta_plano_llm",
                agent=self.current_agent,
                raw_preview=raw_text[:500],
            )
            planned_raw = self._parse_fast_skeleton_plan_json(raw_text)
        except Exception as e:
            _logger_orch.warning("fast_skeleton plano LLM: %s", e)
            planned_raw = None

        if planned_raw is None:
            analise("fast_skeleton_fallback", motivo="json_parse_ou_llm_falhou", passo=step)
            return await self._run_specialist_loop(tools_payload, tools_used, step)

        validated = self._validate_fast_skeleton_plan(planned_raw, allowed, max_items)
        if validated is None:
            analise(
                "fast_skeleton_fallback",
                motivo="plano_inválido_vs_allowlist",
                plano_bruto_amostra=planned_raw,
                passo=step,
            )
            return await self._run_specialist_loop(tools_payload, tools_used, step)

        analise(
            "fast_skeleton_plano_ok",
            n_tools=len(validated),
            planeamento=validated,
        )

        if validated:
            synth_assistant: dict[str, Any] = {
                "role": "assistant",
                "content": "[fast_skeleton: execução planeada de ferramentas]",
                "tool_calls": self._synthetic_tool_calls_from_plan(validated),
            }
            self._append_message(synth_assistant)
            tlog = get_trace_logger()
            if tlog:
                tlog.record(
                    "orchestrator.specialist.fast_skeleton.tool_calls",
                    agent=self.current_agent,
                    tool_calls=synth_assistant["tool_calls"],
                )
            await self._dispatch_specialist_tool_calls(
                synth_assistant["tool_calls"],
                tools_used,
            )
            step += 1

        self._cap_messages()
        # Síntese não usa tools na API; passar ``tools_payload=None`` evita que o shrink
        # reserve tokens para schemas MCP (heurística) e corta menos os resultados ``tool``.
        chat_messages = await self._openai_messages_for_turn(
            query_for_semantic=latest_user_text_for_semantic(self.messages),
            tools_payload=None,
        )
        with llm_phase_context(f"orchestrator:specialist:{self.current_agent}:fast_synth"):
            response = await self.model.chat(
                chat_messages,
                tools=None,
                model_override=mo_spec,
            )
        if response.get("tool_calls"):
            _logger_orch.warning(
                "fast_skeleton: modelo de síntese pediu tools; ignorando tool_calls."
            )
            analise(
                "fast_skeleton_síntese_pediu_tools",
                ignorar=True,
                tool_calls=response.get("tool_calls"),
            )
            response = dict(response)
            response.pop("tool_calls", None)

        self._append_message(response)
        analise(
            "fast_skeleton_fim",
            agent=self.current_agent,
            tools_usadas_n=len(tools_used),
            última_resposta_preview=(response.get("content") or "")[:300],
        )
        return (
            {
                "assistant": response,
                "tools_used": tools_used,
                "agent": self.current_agent,
            },
            step,
        )

    async def _run_specialist_loop(
        self,
        tools_payload: list[dict[str, Any]] | None,
        tools_used: list[dict[str, Any]],
        step: int,
    ) -> tuple[dict[str, Any], int]:
        st_sp = get_settings()
        max_rounds_sp = max(1, int(st_sp.orchestrator_max_tool_rounds))
        while True:
            step += 1
            if step > max_rounds_sp:
                raise RuntimeError(
                    f"Limite de {max_rounds_sp} rodadas do agente excedido."
                )

            analise(
                "specialist_loop_volta",
                agent=self.current_agent,
                volta=step,
                máximo=max_rounds_sp,
            )

            self._cap_messages()
            chat_messages = await self._openai_messages_for_turn(
                query_for_semantic=latest_user_text_for_semantic(self.messages),
                tools_payload=tools_payload,
            )
            mo_spec = st_sp.resolve_orchestrator_model_for_agent(self.current_agent)
            analise(
                "specialist_llm_chat_início",
                agent=self.current_agent,
                volta=step,
                modelo=mo_spec,
                tools_payload_n=len(tools_payload or []),
            )
            with llm_phase_context(f"orchestrator:specialist:{self.current_agent}"):
                response = await self.model.chat(
                    messages=chat_messages,
                    tools=tools_payload,
                    model_override=mo_spec,
                )

            analise(
                "specialist_llm_chat_fim",
                agent=self.current_agent,
                volta=step,
                tem_tool_calls=bool(response.get("tool_calls")),
                content_preview=str(response.get("content") or "")[:280],
            )

            tool_calls = response.get("tool_calls")
            if tool_calls:
                response.setdefault(
                    "content",
                    "[Agent is requesting tool execution]",
                )
                tlog = get_trace_logger()
                if tlog:
                    tlog.record(
                        "orchestrator.specialist.tool_calls_raw",
                        agent=self.current_agent,
                        tool_calls=tool_calls,
                    )

            self._append_message(response)

            if not tool_calls:
                analise(
                    "specialist_loop_fim_sem_tools",
                    agent=self.current_agent,
                    volta=step,
                    tools_usadas_n=len(tools_used),
                )
                return (
                    {
                        "assistant": response,
                        "tools_used": tools_used,
                        "agent": self.current_agent,
                    },
                    step,
                )

            requested: list[str] = []
            for tc in tool_calls:
                fn = tc.get("function") or {}
                n = fn.get("name")
                if not n:
                    continue
                if n == "run_analytics_query":
                    a = _parse_tool_arguments(fn.get("arguments"))
                    qid = a.get("query_id")
                    if qid is not None and str(qid).strip():
                        requested.append(f"{n}(query_id={qid!r})")
                    else:
                        requested.append(str(n))
                else:
                    requested.append(str(n))
            print(f"🔧 [{self.current_agent}] Tool request: {requested}")
            analise(
                "specialist_llm_pediu_tools",
                agent=self.current_agent,
                volta=step,
                tools=requested,
            )

            await self._dispatch_specialist_tool_calls(tool_calls, tools_used)

    def _semantic_debug_payload(self, event_type: str, detail: dict[str, Any]) -> None:
        st = get_settings()
        if st.semantic_context_debug_in_chat_response:
            self._semantic_instrument_for_response = {
                "event_type": event_type,
                "detail": detail,
            }

    async def _inject_semantic_context_for_specialist(self, user_input: str) -> None:
        """Pré-chamada host a ``context_retrieve_similar`` (digest semântico; não bloqueia o turno)."""
        self._semantic_retrieval_markdown = None
        st = get_settings()

        def _skip(reason: str) -> None:
            d = {"reason": reason}
            self._observer_append("host_context_retrieve_skipped", d)
            self._semantic_debug_payload("host_context_retrieve_skipped", d)

        if not st.context_retrieve_host_inject_enabled:
            _skip("inject_disabled")
            return
        if self._session_id_for_cache is None:
            _skip("no_session_id")
            return
        if self.current_agent == "maestro":
            _skip("maestro_phase")
            return
        text = (user_input or "").strip()
        if len(text) < 3:
            _skip("query_too_short")
            return
        low = text.lower()
        if low in ("oi", "olá", "ola", "ok", "sim", "não", "nao", "obrigado", "obrigada"):
            _skip("greeting_or_meta")
            return
        try:
            res = await asyncio.wait_for(
                self._call_mcp_tool_bounded(
                    "context_retrieve_similar",
                    {
                        "session_id": str(self._session_id_for_cache),
                        "query": text,
                        "top_n": st.context_retrieve_default_top_n,
                        "top_m_per_session": st.context_retrieve_default_top_m,
                        "max_context_chars": st.context_retrieve_max_context_chars,
                    },
                ),
                timeout=float(st.context_retrieve_timeout_seconds),
            )
            body = _mcp_result_to_text(res)
            data = json.loads(body)
        except (json.JSONDecodeError, TypeError) as e:
            d = {"error": f"json:{e}"}
            self._observer_append("host_context_retrieve_failed", d)
            self._semantic_debug_payload("host_context_retrieve_failed", d)
            return
        except Exception as e:
            _logger_orch.warning("host context_retrieve_similar: %s", e)
            d = {"error": str(e)[:400]}
            self._observer_append("host_context_retrieve_failed", d)
            self._semantic_debug_payload("host_context_retrieve_failed", d)
            return
        if not isinstance(data, dict) or not data.get("ok"):
            d = {"reason": "ok_false", "error": (data or {}).get("error") if isinstance(data, dict) else None}
            self._observer_append("host_context_retrieve_skipped", d)
            self._semantic_debug_payload("host_context_retrieve_skipped", d)
            return
        ic = data.get("injected_context")
        if ic is None:
            _skip("ok_but_no_injected_context")
            return
        if not str(ic).strip():
            _skip("ok_but_empty_injected")
            return
        cap = st.context_retrieve_max_context_chars
        self._semantic_retrieval_markdown = str(ic)[:cap]
        if self._session_metadata is not None:
            self._session_metadata["_host_context_retrieve_full_json"] = body
            self._session_metadata["_host_retrieve_query_normalized"] = text
            self._session_metadata["_host_retrieve_session_id"] = str(
                self._session_id_for_cache
            )
        cr_args = {
            "session_id": str(self._session_id_for_cache),
            "query": text,
            "top_n": st.context_retrieve_default_top_n,
            "top_m_per_session": st.context_retrieve_default_top_m,
            "max_context_chars": st.context_retrieve_max_context_chars,
        }
        if not tool_excluded_from_state_store("context_retrieve_similar"):
            put_tool_result(
                self._orch_state_block(),
                "context_retrieve_similar",
                cr_args,
                body,
                is_error=False,
            )
        detail_ok = build_host_retrieve_ok_detail(data, len(self._semantic_retrieval_markdown or ""))
        self._observer_append("host_context_retrieve_ok", detail_ok)
        self._semantic_debug_payload("host_context_retrieve_ok", detail_ok)
        tlog = get_trace_logger()
        if tlog:
            tlog.record(
                "semantic_context.host_inject",
                payload=json.dumps(detail_ok, ensure_ascii=False)[:2000],
            )

    async def run(
        self,
        user_input: str,
        target_agent: AgentType | None = None,
        session_id: UUID | None = None,
        session_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Executa agent loop.

        Se ``target_agent`` for None, o Maestro corre primeiro (só tool virtual
        ``route_to_specialist``), faz handoff para o especialista e só então
        expõe ferramentas MCP.

        ``session_metadata`` é mutado in-place quando PostgreSQL persiste a sessão
        (cache MCP, observador, pipeline F3, memory).
        """
        self._session_metadata = session_metadata
        self._session_id_for_cache = session_id
        self._semantic_retrieval_markdown = None
        self._semantic_instrument_for_response = None
        if self._session_metadata is not None:
            # Evita que flags do turno anterior saltem o compositor na F3.
            self._session_metadata.pop("formatador_ui_applied", None)

        self._orch_init_state_for_run()

        auto_route = target_agent is None
        tools_used: list[dict[str, Any]] = []

        trace_token = None
        self._trace_run_id = None
        st = get_settings()
        flow_mode = resolve_orchestrator_flow_mode(st)
        self._orchestrator_flow_mode = flow_mode
        self._turn_timings.clear()
        llm_budget_begin_run(int(st.orchestrator_max_llm_calls_per_request or 0))
        analise(
            "orquestrador_run_preparar",
            fluxo_resolvido=flow_mode,
            agente_corrente=self.current_agent,
            target_agent=str(target_agent),
            session_id=str(session_id) if session_id else None,
            auto_route=auto_route,
            llm_cap=int(st.orchestrator_max_llm_calls_per_request or 0),
            entrada_preview=(user_input or "")[:320],
        )
        trace_root = resolve_agent_trace_dir(st)
        if trace_root is not None:
            trace_root.mkdir(parents=True, exist_ok=True)
            sid_str = str(session_id) if session_id is not None else None
            tr0 = AgentTraceLogger.start_run(
                trace_root,
                max_value_chars=st.agent_trace_max_field_chars,
                session_id=sid_str,
            )
            self._trace_run_id = tr0.run_id
            trace_token = set_trace_logger(tr0)
            activate_openai_chat_stats_for_run()
            tr0.record(
                "orchestrator.run.start",
                user_input=user_input,
                target_agent=target_agent,
                current_agent=self.current_agent,
                orchestrator_flow_mode=flow_mode,
            )

        await self._prepare_agent_for_run(
            auto_route=auto_route,
            target_agent=target_agent,
        )
        log_phase(TurnPhase.PREPARE_AGENT, agent=self.current_agent)

        st0 = get_settings()
        if st0.entity_glossary_enabled and not (self._entity_glossary or "").strip():
            await self._refresh_entity_glossary(session_id)
            log_phase(TurnPhase.ENTITY_GLOSSARY)
            analise("orquestrador_entity_glossary_refreshed", session_id=str(session_id) if session_id else None)

        try:
            analise(
                "orquestrador_run_linear_turn_início",
                fluxo=self._orchestrator_flow_mode,
                agente=self.current_agent,
            )
            out = await run_linear_turn(
                self,
                user_input=user_input,
                auto_route=auto_route,
                target_agent=target_agent,
                session_id=session_id,
                tools_used=tools_used,
            )
            cap_hit = was_llm_cap_hit()
            out["orchestrator_flow_mode"] = self._orchestrator_flow_mode
            out["orchestrator_llm_cap_exceeded"] = cap_hit
            if self._session_metadata is not None and cap_hit:
                self._session_metadata["orchestrator_llm_cap_exceeded"] = True
            analise(
                "orquestrador_run_linear_turn_fim_ok",
                fluxo=out.get("orchestrator_flow_mode"),
                agente_final=out.get("agent"),
                tools_usadas_n=len(out.get("tools_used") or []),
                llm_cap_excedido=cap_hit,
                timings_subpassos=list(self._turn_timings),
            )
            return out

        finally:
            self._cap_messages()
            for m in self.messages:
                m.pop("_orch_anchor", None)
            oai_stats = take_openai_chat_stats()
            tr_end = get_trace_logger()
            cap_hit_finally = was_llm_cap_hit()
            analise(
                "orquestrador_run_finally",
                agente=self.current_agent,
                mensagens_n=len(self.messages),
                fluxo=self._orchestrator_flow_mode,
                llm_cap_excedido=cap_hit_finally,
                timings_subpassos=list(self._turn_timings),
            )
            if tr_end:
                if oai_stats is not None and oai_stats.calls_initiated > 0:
                    summary = oai_stats.to_summary_fields()
                    if self._turn_timings:
                        summary = {**summary, "turn_substep_ms": list(self._turn_timings)}
                    tr_end.record(
                        "openai.chat_completions.summary",
                        **summary,
                    )
                fin: dict[str, Any] = {
                    "messages_count": len(self.messages),
                    "current_agent": self.current_agent,
                    "orchestrator_flow_mode": self._orchestrator_flow_mode,
                    "orchestrator_llm_cap_exceeded": cap_hit_finally,
                }
                if self._turn_timings:
                    fin["turn_substep_ms"] = list(self._turn_timings)
                tr_end.record("orchestrator.run.finally", **fin)
            llm_budget_end_run()
            if trace_token is not None:
                reset_trace_logger(trace_token)
            self._trace_run_id = None
            if self._session_metadata is not None:
                for _k in (
                    "_host_context_retrieve_full_json",
                    "_host_retrieve_query_normalized",
                    "_host_retrieve_session_id",
                ):
                    self._session_metadata.pop(_k, None)
            self._session_metadata = None
            self._session_id_for_cache = None
            self._semantic_retrieval_markdown = None
            self._orch_ephemeral_state = None
