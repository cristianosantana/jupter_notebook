from __future__ import annotations

import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from orion_mcp_v2.observability.metrics import CHAT_LATENCY, CHAT_REQUESTS, ORCHESTRATOR_TURN_SECONDS
from orion_mcp_v2.route.chat import _check_rate_limit
from orion_mcp_v2.route.chat_context import resolve_chat_identity
from orion_mcp_v2.route.schemas import ChatRequestV2

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post(
    "/chat/stream",
    response_model=None,
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE (`text/event-stream`): eventos `token` e `done`.",
            "content": {"text/event-stream": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
    summary="Chat com streaming SSE",
)
async def chat_stream_v2(body: ChatRequestV2, request: Request):
    orch = request.app.state.orchestrator
    repo = orch.state_repository
    sid, uid = await resolve_chat_identity(
        repo, session_id=body.session_id, user_id=body.user_id
    )
    await _check_rate_limit(request, uid)
    t0 = time.perf_counter()

    async def event_source() -> AsyncIterator[str]:
        try:
            async for line in orch.handle_chat_stream(
                session_id=sid,
                user_id=uid,
                message=body.message,
                date_from=body.date_from,
                date_to=body.date_to,
            ):
                yield line
            CHAT_REQUESTS.labels(outcome="ok").inc()
        except Exception:
            CHAT_REQUESTS.labels(outcome="error").inc()
            raise
        finally:
            elapsed = max(time.perf_counter() - t0, 0.0)
            CHAT_LATENCY.observe(elapsed)
            ORCHESTRATOR_TURN_SECONDS.observe(elapsed)

    return StreamingResponse(event_source(), media_type="text/event-stream")
