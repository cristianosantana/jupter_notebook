"""
Aplicação FastAPI com Orquestrador Modular.

Este arquivo substitui app/main.py para usar o novo ModularOrchestrator
com suporte a múltiplos agentes especializados.

Uso:
    uvicorn app.main_modular:app --reload
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from openai import AsyncOpenAI

from ai_provider.openai_provider import OpenAIProvider
from app.config import get_settings, resolve_agent_trace_dir, sync_mysql_env_from_settings
from app.mcp_sampling import build_openai_sampling_callback
from mcp_client.client import Client
from mcp import types as mcp_types  # pyright: ignore[reportMissingImports]
from app.orchestrator import ModularOrchestrator, AgentType
from app.session_store import SessionStore

_logger = logging.getLogger(__name__)

agent: ModularOrchestrator | None = None
session_store: SessionStore | None = None
orchestrator_lock = asyncio.Lock()

_AGENT_TYPES: frozenset[str] = frozenset({
    "maestro",
    "analise_os",
    "clusterizacao",
    "visualizador",
    "agregador",
    "projecoes",
})


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, session_store

    model = OpenAIProvider()
    settings = get_settings()
    trace_root = resolve_agent_trace_dir(settings)
    if trace_root is not None:
        trace_root.mkdir(parents=True, exist_ok=True)
        os.environ["AGENT_TRACE_DIR"] = str(trace_root)
    else:
        os.environ.pop("AGENT_TRACE_DIR", None)

    sync_mysql_env_from_settings(settings)
    oai = AsyncOpenAI(api_key=settings.openai_api_key or None)
    sampling_cb = build_openai_sampling_callback(
        oai,
        settings.openai_model or "gpt-4o-mini",
    )
    client = Client(
        "mcp_server/server.py",
        sampling_callback=sampling_cb,
        sampling_capabilities=mcp_types.SamplingCapability(),
    )
    await client.connect()

    # Criar orquestrador modular
    agent = ModularOrchestrator(model, client)
    await agent.load_tools()

    if settings.postgres_enabled:
        try:
            session_store = await SessionStore.create(settings)
            await session_store.run_migrations(settings)
        except Exception as e:
            session_store = None
            _logger.warning(
                "PostgreSQL indisponível — sessões persistidas desactivadas. "
                "Crie a base %r (ou corrija POSTGRES_*) se precisar de histórico. Erro: %s",
                settings.postgres_database,
                e,
                exc_info=True,
            )

    yield

    if session_store:
        await session_store.close()
        session_store = None
    if agent:
        await agent.client.close()


app = FastAPI(title="project_mcp_v1_modular", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    target_agent: AgentType | None = None  # Se None, usa Maestro (ou continua especialista)
    new_conversation: bool = False  # Se True, limpa histórico e recomeça pelo Maestro
    user_id: str | None = None
    session_id: UUID | None = None


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "agent": agent.current_agent if agent else "not_initialized"}


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Endpoint de chat com suporte a roteamento de agentes.

    Por omissão mantém a thread: após handoff para um especialista, novas mensagens
    com ``target_agent`` omitido continuam com o mesmo agente e o histórico.

    - ``new_conversation: true`` — limpa mensagens e recomeça pelo Maestro.
    - Com PostgreSQL activo: envia ``session_id`` nas mensagens seguintes; ``user_id`` é opcional.
      O transcript persistido inclui só a conversa com especialistas (não o roteamento do Maestro).

    Exemplos:
    - POST /chat {"message": "Análise semanal de OS"}
      → Maestro roteia para agente_analise_os

    - POST /chat {"message": "Agrupar concessionárias", "target_agent": "clusterizacao"}
      → Direto para agente_clusterizacao
    """
    if agent is None:
        raise RuntimeError("Agent not initialized")

    sid: UUID | None = None

    async with orchestrator_lock:
        if session_store:
            if request.user_id:
                await session_store.upsert_user(request.user_id)

            if request.new_conversation:
                nsid = uuid.uuid4()
                await session_store.create_session(nsid, request.user_id)
                await agent.reset_conversation()
                sid = nsid
            elif request.session_id is None:
                nsid = uuid.uuid4()
                await session_store.create_session(nsid, request.user_id)
                await agent.reset_conversation()
                sid = nsid
            else:
                row = await session_store.get_session(request.session_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="session_id não encontrado")
                sid = request.session_id
                msgs = await session_store.load_messages(sid)
                ca = row["current_agent"]
                if ca not in _AGENT_TYPES:
                    ca = "maestro"
                    msgs = []
                agent.hydrate_session_state(ca, msgs, session_id=sid)  # type: ignore[arg-type]
        else:
            if request.new_conversation:
                await agent.reset_conversation()

        out = await agent.run(
            request.message,
            target_agent=request.target_agent,
            session_id=sid,
        )
        assistant = out["assistant"]

        if session_store is not None and sid is not None:
            if out["agent"] != "maestro":
                await session_store.replace_conversation_messages(sid, agent.messages)
                await session_store.touch_session(sid, out["agent"])
            else:
                await session_store.touch_session(sid)

    payload: dict = {
        "reply": assistant["content"],
        "tools_used": out["tools_used"],
        "agent_used": out["agent"],
    }
    tid = out.get("trace_run_id")
    if tid:
        payload["trace_run_id"] = tid
    if session_store is not None and sid is not None:
        payload["session_id"] = str(sid)
    if request.user_id is not None:
        payload["user_id"] = request.user_id
    return payload


@app.post("/agent/set")
async def set_agent(agent_type: AgentType):
    """Muda agente ativo (para testes/debug)."""
    if agent is None:
        raise RuntimeError("Agent not initialized")

    await agent.set_agent(agent_type)
    return {
        "message": f"Agent set to {agent_type}",
        "current_agent": agent.current_agent,
        "metadata": {
            "model": agent.current_metadata.model,
            "context_budget": agent.current_metadata.context_budget,
            "role": agent.current_metadata.role,
        } if agent.current_metadata else None
    }


@app.get("/agents")
async def list_agents():
    """Lista agentes disponíveis e seus SKILLs."""
    if agent is None:
        raise RuntimeError("Agent not initialized")

    agents_info = {}
    agent_types = ["maestro", "analise_os", "clusterizacao", "visualizador", "agregador", "projecoes"]

    for agent_type in agent_types:
        try:
            skill, metadata = agent.skill_loader.load_skill(agent_type)
            agents_info[agent_type] = {
                "role": metadata.role,
                "model": metadata.model,
                "context_budget": metadata.context_budget,
                "max_tokens": metadata.max_tokens,
                "temperature": metadata.temperature,
                "skill_preview": skill[:200] + "..." if len(skill) > 200 else skill
            }
        except Exception as e:
            agents_info[agent_type] = {"error": str(e)}

    return agents_info
