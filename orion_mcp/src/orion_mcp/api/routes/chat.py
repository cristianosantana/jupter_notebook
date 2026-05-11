from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from orion_mcp.api.schemas import ChatRequest, ChatResponse
from orion_mcp.core.orchestrator.orchestrator import Orchestrator
from orion_mcp.core.state.turn_hints import ChatTurnHints
from orion_mcp.core.strategy import Strategy
from orion_mcp.infra.observability.metrics import CHAT_LATENCY, CHAT_REQUESTS

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _hints_from_chat_request(body: ChatRequest) -> ChatTurnHints:
    return ChatTurnHints(
        query_id=body.query_id,
        date_from=body.date_from,
        date_to=body.date_to,
        limit=body.limit,
        offset=body.offset,
        summarize=body.summarize,
    )


def get_orch(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    summary="Chat com streaming SSE",
    description=(
        "Fluxo principal de chat com **Server-Sent Events** (`text/event-stream`). "
        "Cada evento é uma linha `data: <json>\\n\\n`. Tipos: `token` (delta de texto do LLM) e `done` "
        "(payload final + métricas + `session_id`). O `payload` pode incluir `perf` (mapa booleano de degradação; ver `docs/api.md`). "
        "Para resposta JSON num único corpo, use `POST /api/v1/chat`."
    ),
)
async def chat_stream_v1(
    body: ChatRequest, request: Request, orch: Orchestrator = Depends(get_orch)
) -> StreamingResponse:
    import time

    t0 = time.perf_counter()

    async def event_source() -> AsyncIterator[str]:
        try:
            strat = Strategy.fast if body.strategy == "fast" else Strategy.deep
            sid = body.resolved_session_id()
            hints = _hints_from_chat_request(body)
            async for line in orch.handle_chat_stream(
                session_id=sid,
                user_input=body.message,
                strategy=strat,
                hints=hints,
            ):
                yield line
            CHAT_REQUESTS.labels(outcome="ok").inc()
        except Exception:
            CHAT_REQUESTS.labels(outcome="error").inc()
            raise
        finally:
            CHAT_LATENCY.observe(max(time.perf_counter() - t0, 0.0))

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat JSON",
    description="Resposta única em JSON. O campo `payload` pode incluir `perf` (degradação do turno; ver `docs/api.md`).",
)
async def chat_v1(body: ChatRequest, request: Request, orch: Orchestrator = Depends(get_orch)) -> ChatResponse:
    import time

    t0 = time.perf_counter()
    try:
        strat = Strategy.fast if body.strategy == "fast" else Strategy.deep
        sid = body.resolved_session_id()
        hints = _hints_from_chat_request(body)
        result = await orch.handle_chat(
            session_id=sid,
            user_input=body.message,
            strategy=strat,
            hints=hints,
        )
        CHAT_REQUESTS.labels(outcome="ok").inc()
        return ChatResponse(session_id=sid, payload=result.payload, metrics=result.metrics)
    except Exception:
        CHAT_REQUESTS.labels(outcome="error").inc()
        raise
    finally:
        CHAT_LATENCY.observe(max(time.perf_counter() - t0, 0.0))
