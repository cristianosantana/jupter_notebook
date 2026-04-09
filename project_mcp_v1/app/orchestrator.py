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
from uuid import UUID

from ai_provider.base import ModelProvider
from app.memory_prompts import (
    maybe_update_session_notes,
    maybe_update_conversation_summary,
)
from app.mcp_session_cache import (
    append_cache_entry,
    build_mcp_cache_digest_section,
    find_cache_entry,
    mcp_cache_key,
    entries_fingerprint,
)
from app.prompt_assembly import build_effective_system_text
from app.pipeline_critique import format_critique_user_message, parse_critique_response
from app.routing_tools import (
    MAESTRO_TOOLS_ONLY,
    ROUTE_TO_SPECIALIST_TOOL_NAME,
    SPECIALIST_AGENTS,
    parse_route_arguments,
    specialist_from_text_fallback,
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
from app.content_blocks import split_reply_and_blocks
from mcp_client.client import Client
from mcp.types import CallToolResult, Tool  # pyright: ignore[reportMissingImports]

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


def _strip_orch_internal_keys(msg: dict[str, Any]) -> dict[str, Any]:
    """Remove chaves internas do orquestrador (não enviar à API do modelo)."""
    return {
        k: v
        for k, v in msg.items()
        if not (isinstance(k, str) and k.startswith("_orch"))
    }


def _messages_with_skill(
    skill: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    public = [_strip_orch_internal_keys(m) for m in messages]
    if not skill:
        return list(public)
    out = list(public)
    if out and out[0].get("role") == "system":
        existing = (out[0].get("content") or "").strip()
        merged = f"{skill}\n\n{existing}".strip() if existing else skill
        out[0] = {**out[0], "content": merged}
    else:
        out.insert(0, {"role": "system", "content": skill})
    return out


def _estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    cpt = max(1, int(get_settings().orchestrator_chars_per_token_estimate))
    return max(1, (len(text) + cpt - 1) // cpt)


def _estimate_tokens_for_message(msg: dict[str, Any]) -> int:
    """Tokens aproximados de uma mensagem no formato chat (content + tool_calls)."""
    n = 4  # overhead de estrutura (role, campos)
    role = msg.get("role")
    if role is not None:
        n += _estimate_tokens_from_text(str(role))
    content = msg.get("content")
    if isinstance(content, str):
        n += _estimate_tokens_from_text(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                txt = part.get("text")
                if isinstance(txt, str):
                    n += _estimate_tokens_from_text(txt)
    tool_calls = msg.get("tool_calls")
    if tool_calls:
        n += _estimate_tokens_from_text(json.dumps(tool_calls, ensure_ascii=False))
    return n


def _estimate_prompt_tokens_messages_plus_skill(
    skill: str,
    messages: list[dict[str, Any]],
) -> int:
    """Estimativa do prompt enviado ao modelo (SKILL fundido no system + histórico)."""
    merged = _messages_with_skill(skill, messages)
    return sum(_estimate_tokens_for_message(m) for m in merged)


def _estimate_tokens_from_tool_dicts(tools: list[dict[str, Any]] | None) -> int:
    """Tokens aproximados de definições de ferramentas já serializáveis como dict (ex.: OpenAI-style)."""
    if not tools:
        return 0
    total = 128
    for t in tools:
        total += _estimate_tokens_from_text(json.dumps(t, ensure_ascii=False))
    return total


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

    def _use_mcp_session_cache(self) -> bool:
        return self._session_metadata is not None and self._session_id_for_cache is not None

    def _utc_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _observer_append(self, event_type: str, detail: Any) -> None:
        st = get_settings()
        if not st.observer_agent_enabled:
            return
        if self._session_metadata is None:
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

    def _build_system_text_sync(self) -> str:
        """System para orçamento de poda (digest Python apenas, sem LLM)."""
        st = get_settings()
        digest = build_mcp_cache_digest_section(self._session_meta(), st)
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
        base = build_mcp_cache_digest_section(md, st)
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
        digest = build_mcp_cache_digest_section(md, st)

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
                "role": "user",
                "content": format_critique_user_message(verdict),
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
        try:
            skill, _ = self.skill_loader.load_skill("formatador_ui")
        except (FileNotFoundError, ValueError):
            skill = (
                "Formatador UI: preserva factos; no fim um fenced ```json com "
                '{"version":1,"content_blocks":[{"type":"paragraph","text":"..."}]}'
            )
        mo = st.resolve_orchestrator_model_for_agent("formatador_ui")
        u = (
            "Pedido original (contexto):\n"
            + user_input[:4000]
            + "\n\nTexto aprovado a formatar:\n"
            + text[:24000]
        )
        print(f"🔄 [formatador_ui] {self.current_agent} → formatador_ui (chamada ao modelo)")
        try:
            with llm_phase_context("orchestrator:formatador_ui"):
                resp = await self.model.chat(
                    [
                        {"role": "system", "content": skill},
                        {"role": "user", "content": u},
                    ],
                    tools=None,
                    model_override=mo,
                )
            out = str((resp or {}).get("content") or "").strip()
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
            mcp_result = await self.client.call_tool(
                gname,
                gql_args,
            )
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
        while self.messages and self.messages[0].get("role") == "tool":
            self.messages.pop(0)
            self._message_times.pop(0)

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
        """TTL no início, orçamento de contexto (metadata), limite de mensagens, sem tool órfã."""
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
            self.messages.pop(0)
            self._message_times.pop(0)

        self._strip_leading_orphan_tools()

        cap = self._effective_input_token_cap()
        if cap is not None:
            while self.messages:
                if (
                    _estimate_prompt_tokens_messages_plus_skill(
                        self._build_system_text_sync(),
                        self.messages,
                    )
                    <= cap
                ):
                    break
                if self.messages[0].get("_orch_anchor"):
                    break
                self.messages.pop(0)
                self._message_times.pop(0)
                self._strip_leading_orphan_tools()

        max_hist = max(1, int(st.orchestrator_max_history_messages))
        while len(self.messages) > max_hist:
            if self.messages[0].get("_orch_anchor"):
                break
            self.messages.pop(0)
            self._message_times.pop(0)

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
            return None
        if self.current_agent not in SPECIALIST_AGENTS:
            return base
        mp = get_settings().specialist_mcp_tool_allowlist()
        allow = mp.get(str(self.current_agent))
        if not allow:
            return base
        out: list[dict[str, Any]] = []
        for t in base:
            fn = t.get("function") if isinstance(t.get("function"), dict) else None
            name = (fn.get("name") if fn else None) or t.get("name")
            if name and str(name) in allow:
                out.append(t)
        return out if out else base

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
            sys_t = await self._build_system_text_async()
            with llm_phase_context("orchestrator:maestro"):
                response = await self.model.chat(
                    messages=_messages_with_skill(
                        sys_t,
                        self.messages,
                    ),
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

    async def _execute_single_tool_call(
        self,
        tc: dict[str, Any],
        tools_used: list[dict[str, Any]],
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

        print(f"⚙️  [{self.current_agent}] Executing: {name}")

        st_exec = get_settings()
        preview_cap = max(1, int(st_exec.orchestrator_tool_result_preview_max))

        use_cache = self._use_mcp_session_cache() and name != ROUTE_TO_SPECIALIST_TOOL_NAME
        ck_tool = mcp_cache_key(name, args) if use_cache else ""

        if use_cache and self._session_metadata is not None:
            hit = find_cache_entry(self._session_metadata, ck_tool)
            if hit and hit.get("result_text"):
                self._observer_append(
                    "tool_cache_hit",
                    {"tool": name, "cache_key_prefix": ck_tool[:16]},
                )
                content = "[cache_hit]\n" + str(hit["result_text"])
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
                    content = (
                        content[:max_tool]
                        + "\n\n[Conteúdo truncado pelo orquestrador (tool_message_content_max_chars). "
                        "Reduza limit/offset, summarize=true onde aplicável, ou aumente o teto em config.]"
                    )
                self._append_message({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": content,
                })
                return

        try:
            self._observer_append("tool_cache_miss", {"tool": name})
            mcp_result = await self.client.call_tool(name, args)
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
                append_cache_entry(
                    self._session_metadata,
                    cache_key=ck_tool,
                    tool_name=str(name),
                    args=args,
                    result_text=content,
                )
                self._observer_append("tool_call", {"tool": name, "source": "mcp"})
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

        st_tool = get_settings()
        max_tool = max(4096, int(st_tool.tool_message_content_max_chars))
        if len(content) > max_tool:
            content = (
                content[:max_tool]
                + "\n\n[Conteúdo truncado pelo orquestrador (tool_message_content_max_chars). "
                "Reduza limit/offset, summarize=true onde aplicável, ou aumente o teto em config.]"
            )

        self._append_message({
            "role": "tool",
            "tool_call_id": tc_id,
            "content": content,
        })

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

            self._cap_messages()
            sys_t = await self._build_system_text_async()
            mo_spec = st_sp.resolve_orchestrator_model_for_agent(self.current_agent)
            with llm_phase_context(f"orchestrator:specialist:{self.current_agent}"):
                response = await self.model.chat(
                    messages=_messages_with_skill(
                        sys_t,
                        self.messages,
                    ),
                    tools=tools_payload,
                    model_override=mo_spec,
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
                return (
                    {
                        "assistant": response,
                        "tools_used": tools_used,
                        "agent": self.current_agent,
                    },
                    step,
                )

            requested = [
                n
                for tc in tool_calls
                if (n := tc.get("function", {}).get("name"))
            ]
            print(f"🔧 [{self.current_agent}] Tool request: {requested}")

            for tc in tool_calls:
                await self._execute_single_tool_call(tc, tools_used)

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
        if self._session_metadata is not None:
            # Evita que flags do turno anterior saltem o compositor na F3.
            self._session_metadata.pop("formatador_ui_applied", None)

        auto_route = target_agent is None
        tools_used: list[dict[str, Any]] = []

        trace_token = None
        self._trace_run_id = None
        st = get_settings()
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
            )

        await self._prepare_agent_for_run(
            auto_route=auto_route,
            target_agent=target_agent,
        )

        st0 = get_settings()
        if st0.entity_glossary_enabled and not (self._entity_glossary or "").strip():
            await self._refresh_entity_glossary(session_id)

        try:
            self._append_message({
                "role": "user",
                "content": user_input,
                "_orch_anchor": True,
            })

            tools_payload = self._tools_payload_for_specialist()
            step = 0

            if auto_route and self.current_agent == "maestro":
                early, step = await self._run_maestro_routing_phase(
                    user_input, tools_used, step, session_id=session_id
                )
                if early is not None:
                    early = await self._run_f3_pipeline(early, user_input)
                    st_mem = get_settings()
                    if self._session_metadata is not None:
                        await maybe_update_session_notes(
                            self.model,
                            self._session_metadata,
                            json.dumps(
                                {
                                    "last_agent": early.get("agent"),
                                    "user_excerpt": user_input[:1200],
                                },
                                ensure_ascii=False,
                            ),
                            st_mem,
                        )
                        excerpt = "\n".join(
                            str(m.get("content") or "")[:500]
                            for m in self.messages[-8:]
                        )
                        await maybe_update_conversation_summary(
                            self.model,
                            self._session_metadata,
                            excerpt,
                            st_mem,
                        )
                    await self._observer_narrative(user_input, tools_used)
                    if self._trace_run_id:
                        early["trace_run_id"] = self._trace_run_id
                    return early

            out, step = await self._run_specialist_loop(
                tools_payload, tools_used, step
            )
            if self.current_agent != "maestro":
                out, step = await self._run_critique_refine_loop(
                    out, user_input, tools_used, step
                )
                out = await self._run_formatador_ui(out, user_input)
            out = await self._run_f3_pipeline(out, user_input)
            st_mem = get_settings()
            if self._session_metadata is not None:
                await maybe_update_session_notes(
                    self.model,
                    self._session_metadata,
                    json.dumps(
                        {
                            "last_agent": out.get("agent"),
                            "user_excerpt": user_input[:1200],
                        },
                        ensure_ascii=False,
                    ),
                    st_mem,
                )
                excerpt = "\n".join(
                    str(m.get("content") or "")[:500]
                    for m in self.messages[-8:]
                )
                await maybe_update_conversation_summary(
                    self.model,
                    self._session_metadata,
                    excerpt,
                    st_mem,
                )
            await self._observer_narrative(user_input, tools_used)
            if self._trace_run_id:
                out["trace_run_id"] = self._trace_run_id
            return out

        finally:
            self._cap_messages()
            for m in self.messages:
                m.pop("_orch_anchor", None)
            oai_stats = take_openai_chat_stats()
            tr_end = get_trace_logger()
            if tr_end:
                if oai_stats is not None and oai_stats.calls_initiated > 0:
                    tr_end.record(
                        "openai.chat_completions.summary",
                        **oai_stats.to_summary_fields(),
                    )
                tr_end.record(
                    "orchestrator.run.finally",
                    messages_count=len(self.messages),
                    current_agent=self.current_agent,
                )
            if trace_token is not None:
                reset_trace_logger(trace_token)
            self._trace_run_id = None
            self._session_metadata = None
            self._session_id_for_cache = None
