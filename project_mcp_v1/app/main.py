"""
Aplicação FastAPI com Orquestrador Modular.

Este arquivo substitui app/main.py para usar o novo ModularOrchestrator
com suporte a múltiplos agentes especializados.

Uso:
    uvicorn app.main_modular:app --reload
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from openai import AsyncOpenAI

from ai_provider.openai_provider import OpenAIProvider
from app.config import get_settings
from app.mcp_sampling import build_openai_sampling_callback
from mcp_client.client import Client
from mcp import types as mcp_types  # pyright: ignore[reportMissingImports]
from app.orchestrator import ModularOrchestrator, AgentType


agent: ModularOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent

    model = OpenAIProvider()
    settings = get_settings()
    os.environ.setdefault("MYSQL_HOST", settings.mysql_host)
    os.environ.setdefault("MYSQL_PORT", str(settings.mysql_port))
    os.environ.setdefault("MYSQL_USER", settings.mysql_user)
    os.environ.setdefault("MYSQL_PASSWORD", settings.mysql_password)
    os.environ.setdefault("MYSQL_DATABASE", settings.mysql_database)
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

    yield

    if agent:
        await agent.client.close()


app = FastAPI(title="project_mcp_v1_modular", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    target_agent: AgentType | None = None  # Se None, usa Maestro (ou continua especialista)
    new_conversation: bool = False  # Se True, limpa histórico e recomeça pelo Maestro


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

    Exemplos:
    - POST /chat {"message": "Análise semanal de OS"}
      → Maestro roteia para agente_analise_os

    - POST /chat {"message": "Agrupar concessionárias", "target_agent": "clusterizacao"}
      → Direto para agente_clusterizacao
    """
    if agent is None:
        raise RuntimeError("Agent not initialized")

    if request.new_conversation:
        await agent.reset_conversation()

    out = await agent.run(request.message, target_agent=request.target_agent)
    assistant = out["assistant"]

    return {
        "reply": assistant["content"],
        "tools_used": out["tools_used"],
        "agent_used": out["agent"],
    }


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
