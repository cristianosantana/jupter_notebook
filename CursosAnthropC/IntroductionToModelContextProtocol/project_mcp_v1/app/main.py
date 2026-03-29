import os

from fastapi import FastAPI
from pydantic import BaseModel

from openai import AsyncOpenAI

from ai_provider.openai_provider import OpenAIProvider
from app.config import get_settings
from app.mcp_sampling import build_openai_sampling_callback
from mcp_client.client import Client
from mcp import types as mcp_types  # pyright: ignore[reportMissingImports]
from app.orchestrator import AgentOrchestrator


app = FastAPI(title="project_mcp_v1")


class ChatBody(BaseModel):
    message: str


agent: AgentOrchestrator | None = None


@app.on_event("startup")
async def startup():

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

    agent = AgentOrchestrator(model, client)
    await agent.load_tools()

@app.on_event("shutdown")
async def shutdown():
    if agent:
        await agent.client.close()

@app.post("/chat")
async def chat(body: ChatBody):
    if agent is None:
        raise RuntimeError("Agent not initialized")

    out = await agent.run(body.message)
    assistant = out["assistant"]

    return {
        "reply": assistant["content"],
        "tools_used": out["tools_used"],
    }