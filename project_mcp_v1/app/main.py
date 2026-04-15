"""
Aplicação FastAPI com Orquestrador Modular.

Este arquivo substitui app/main.py para usar o novo ModularOrchestrator
com suporte a múltiplos agentes especializados.

Uso:
    uvicorn app.main_modular:app --reload
"""

import asyncio
import contextlib
import copy
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openai import AsyncOpenAI

from ai_provider.openai_provider import OpenAIProvider
from app.config import get_settings, resolve_agent_trace_dir, sync_mysql_env_from_settings
from app.content_blocks import split_reply_and_blocks
from app.post_turn_tasks import merge_post_turn_metadata_from_db_row, run_all_post_turn_work
from app.mcp_sampling import build_openai_sampling_callback
from mcp_client.client import Client
from mcp import types as mcp_types  # pyright: ignore[reportMissingImports]
from app.orchestrator import ModularOrchestrator, AgentType
from app.session_store import SessionStore

_logger = logging.getLogger(__name__)


def ensure_transcript_includes_user_message(
    messages: list[dict[str, Any]],
    user_text: str,
) -> bool:
    """
    Garante pelo menos uma mensagem ``role=user`` no transcript persistido.
    Usado quando o orquestrador não deixou nenhuma linha user (regressão / podagem).
    """
    text = (user_text or "").strip()
    if not text:
        return False
    if any((str(m.get("role") or "")).strip().lower() == "user" for m in messages):
        return False
    messages.insert(0, {"role": "user", "content": text})
    return True

agent: ModularOrchestrator | None = None
session_store: SessionStore | None = None
orchestrator_lock = asyncio.Lock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, session_store

    model = OpenAIProvider()
    settings = get_settings()
    trace_root = resolve_agent_trace_dir(settings)
    if trace_root is not None:
        trace_root.mkdir(parents=True, exist_ok=True)
        os.environ["AGENT_TRACE_DIR"] = str(trace_root)
        os.environ["AGENT_TRACE_MAX_FIELD_CHARS"] = str(
            int(settings.agent_trace_max_field_chars)
        )
    else:
        os.environ.pop("AGENT_TRACE_DIR", None)
        os.environ.pop("AGENT_TRACE_MAX_FIELD_CHARS", None)

    sync_mysql_env_from_settings(settings)
    oai = AsyncOpenAI(
        api_key=settings.openai_api_key or None,
        timeout=float(settings.openai_http_timeout_seconds),
    )
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

_st = get_settings()
_cors = [o.strip() for o in (_st.cors_origins or "").split(",") if o.strip()]
if not _cors:
    _cors = ["http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    target_agent: AgentType | None = None  # Se None, usa Maestro (ou continua especialista)
    new_conversation: bool = False  # Se True, limpa histórico e recomeça pelo Maestro
    user_id: str | None = None
    session_id: UUID | None = None


class McpToolCallRequest(BaseModel):
    """Corpo para executar uma tool do servidor MCP ligado ao orquestrador."""

    name: str
    arguments: dict[str, object] | None = None


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "agent": agent.current_agent if agent else "not_initialized"}


async def process_chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """
    Lógica partilhada por ``POST /chat`` e ``POST /api/chat``.

    Por omissão mantém a thread: após handoff para um especialista, novas mensagens
    com ``target_agent`` omitido continuam com o mesmo agente e o histórico.

    - ``new_conversation: true`` — limpa mensagens e recomeça pelo Maestro.
    - Com PostgreSQL activo: envia ``session_id`` nas mensagens seguintes; ``user_id`` é opcional.
      O transcript persistido inclui **todas** as mensagens da sessão (Maestro e especialistas).
    """
    if agent is None:
        raise RuntimeError("Agent not initialized")

    settings = get_settings()
    sid: UUID | None = None

    session_metadata: dict = {}

    async with orchestrator_lock:
        if session_store:
            if request.user_id:
                await session_store.upsert_user(request.user_id)

            if request.new_conversation:
                nsid = uuid.uuid4()
                await session_store.create_session(nsid, request.user_id)
                await agent.reset_conversation()
                sid = nsid
                session_metadata = {}
            elif request.session_id is None:
                nsid = uuid.uuid4()
                await session_store.create_session(nsid, request.user_id)
                await agent.reset_conversation()
                sid = nsid
                session_metadata = {}
            else:
                row = await session_store.get_session(request.session_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="session_id não encontrado")
                sid = request.session_id
                raw_meta = row.get("metadata")
                session_metadata = dict(raw_meta) if isinstance(raw_meta, dict) else {}
                msgs = await session_store.load_messages(sid)
                ca = row["current_agent"]
                if ca not in settings.orchestrator_agent_types_frozenset:
                    ca = "maestro"
                    msgs = []
                agent.hydrate_session_state(ca, msgs, session_id=sid)  # type: ignore[arg-type]
        else:
            if request.new_conversation:
                await agent.reset_conversation()
            session_metadata = {}

        meta_for_run = session_metadata if session_store is not None and sid is not None else None
        try:
            out = await agent.run(
                request.message,
                target_agent=request.target_agent,
                session_id=sid,
                session_metadata=meta_for_run,
            )
        except asyncio.CancelledError:
            _logger.info(
                "Pedido de chat cancelado durante agent.run (cliente desligou ou abort)"
            )
            raise
        assistant = out["assistant"]

        transcript_excerpt = "\n".join(
            str(m.get("content") or "")[:500] for m in agent.messages[-8:]
        )

        if session_store is not None and sid is not None:
            fresh_row = await session_store.get_session(sid)
            merge_post_turn_metadata_from_db_row(session_metadata, fresh_row)
            await session_store.update_session_metadata(sid, session_metadata)
            excerpt = (request.message or "").strip()
            if excerpt:
                await session_store.merge_session_metadata(
                    sid,
                    {
                        "last_user_message": excerpt[:8000],
                        "last_user_message_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            if excerpt:
                ensure_transcript_includes_user_message(agent.messages, excerpt)
            await session_store.replace_conversation_messages(sid, agent.messages)
            await session_store.touch_session(sid, out["agent"])
            tr = out.get("trace_run_id")
            if tr:
                await session_store.merge_session_metadata(
                    sid,
                    {"last_trace_run_id": str(tr)},
                )
            if background_tasks is not None:
                meta_snap = copy.deepcopy(session_metadata)
                background_tasks.add_task(
                    run_all_post_turn_work,
                    store=session_store,
                    mcp_client=agent.client,
                    session_id=sid,
                    model=agent.model,
                    metadata_snapshot=meta_snap,
                    user_input=request.message,
                    tools_used=list(out.get("tools_used") or []),
                    agent_final=str(out.get("agent") or ""),
                    transcript_excerpt=transcript_excerpt,
                    settings=settings,
                )

    display_reply, content_blocks = split_reply_and_blocks(assistant["content"])
    payload: dict = {
        "reply": display_reply,
        "content_blocks": content_blocks,
        "tools_used": out["tools_used"],
        "agent_used": out["agent"],
    }
    tid = out.get("trace_run_id")
    if tid is not None and str(tid).strip():
        payload["trace_run_id"] = str(tid).strip()
    else:
        payload["trace_run_id"] = None
    if session_store is not None and sid is not None:
        payload["session_id"] = str(sid)
    if request.user_id is not None:
        payload["user_id"] = request.user_id
    dbg_sem = out.get("semantic_context_debug")
    if dbg_sem is not None:
        payload["semantic_context_debug"] = dbg_sem
    ofm = out.get("orchestrator_flow_mode")
    if ofm is not None:
        payload["orchestrator_flow_mode"] = str(ofm)
    payload["orchestrator_llm_cap_exceeded"] = bool(out.get("orchestrator_llm_cap_exceeded"))
    return payload


async def _cancel_task_on_disconnect(http_request: Request, task: "asyncio.Task[dict]") -> None:
    """Quando o cliente fecha a ligação, cancela ``process_chat`` para libertar o lock."""
    try:
        while not task.done():
            if await http_request.is_disconnected():
                task.cancel()
                return
            await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        raise


async def run_chat_with_disconnect(
    http_request: Request,
    body: ChatRequest,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    task = asyncio.create_task(process_chat(body, background_tasks))
    disconnect_watch = asyncio.create_task(
        _cancel_task_on_disconnect(http_request, task)
    )
    try:
        return await task
    finally:
        disconnect_watch.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await disconnect_watch


@app.post("/chat")
async def chat(
    http_request: Request,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
):
    """Alias legado; preferir ``POST /api/chat`` no SmartChat."""
    return await run_chat_with_disconnect(http_request, body, background_tasks)


api_router = APIRouter(prefix="/api")


@api_router.post("/chat")
async def api_chat(
    http_request: Request,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
):
    return await run_chat_with_disconnect(http_request, body, background_tasks)


@api_router.get("/mcp/tools")
async def api_mcp_list_tools():
    """
    Lista as ferramentas expostas pelo servidor MCP (mesma sessão que o orquestrador).
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="orquestrador / MCP não inicializado")
    async with orchestrator_lock:
        tools = await agent.client.list_tools()
    serialized = [t.model_dump(mode="json") for t in tools]
    return {"tools": serialized, "count": len(serialized)}


@api_router.post("/mcp/tools/call")
async def api_mcp_call_tool(body: McpToolCallRequest):
    """
    Executa uma tool MCP por nome. Útil para debug ou integrações directas.
    Usa o mesmo cliente que o agente; pedidos são serializados com ``orchestrator_lock``.
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="orquestrador / MCP não inicializado")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name é obrigatório")
    async with orchestrator_lock:
        result = await agent.client.call_tool(name, body.arguments)
    return {
        "name": name,
        "is_error": result.isError,
        "result": result.model_dump(mode="json"),
    }


@api_router.get("/sessions")
async def api_list_sessions(user_id: str | None = None, limit: int = 50):
    if session_store is None:
        return {"sessions": [], "persistence_enabled": False}
    sessions = await session_store.list_sessions(user_id=user_id, limit=limit)
    return {"sessions": sessions, "persistence_enabled": True}


def _session_metadata_as_dict(raw: object) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


@api_router.get("/sessions/{session_id}")
async def api_get_session(session_id: UUID):
    if session_store is None:
        raise HTTPException(status_code=503, detail="persistência de sessões inactiva")
    row = await session_store.get_session(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session_id não encontrado")
    msgs = await session_store.load_messages(session_id)
    meta = _session_metadata_as_dict(row["metadata"])
    trace_run_id = meta.get("last_trace_run_id")
    if trace_run_id is not None:
        trace_run_id = str(trace_run_id)
    session_payload = {
        "session_id": str(row["session_id"]),
        "user_id": row["user_id"],
        "current_agent": row["current_agent"],
        "status": row["status"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "last_active_at": row["last_active_at"].isoformat() if row["last_active_at"] else None,
        "metadata": meta,
    }
    return {
        "session": session_payload,
        "messages": msgs,
        "trace_run_id": trace_run_id,
        "persistence_enabled": True,
    }


app.include_router(api_router)


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
    agent_types = [
        "maestro",
        "analise_os",
        "clusterizacao",
        "visualizador",
        "agregador",
        "projecoes",
        "verificador",
        "compositor_layout",
        "avaliador_critico",
        "formatador_ui",
    ]

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
