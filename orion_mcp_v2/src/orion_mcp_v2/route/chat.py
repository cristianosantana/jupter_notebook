from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Request

from orion_mcp_v2.observability.metrics import CHAT_REQUESTS, ORCHESTRATOR_TURN_SECONDS, RATE_LIMIT_HITS
from orion_mcp_v2.route.chat_context import resolve_chat_identity
from orion_mcp_v2.route.schemas import ChatRequestV2, ChatResponseV2

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


async def _check_rate_limit(request: Request, user_id: str) -> None:
    rlim = getattr(request.app.state, "redis_limiter", None)
    cfg = request.app.state.settings
    if rlim is None:
        return
    window = int(time.time()) // 60
    key = f"rl:v2:{user_id}:{window}"
    try:
        n = await rlim.incr(key)
        if n == 1:
            await rlim.expire(key, 120)
        if n > cfg.rate_limit_per_minute:
            RATE_LIMIT_HITS.inc()
            raise HTTPException(status_code=429, detail="rate_limit_exceeded")
    except HTTPException:
        raise
    except Exception:
        _logger.warning("rate_limit_check_failed", exc_info=True)


@router.post("/chat", response_model=ChatResponseV2)
async def chat_v2(body: ChatRequestV2, request: Request) -> ChatResponseV2:
    orch = request.app.state.orchestrator
    repo = orch.state_repository
    sid, uid = await resolve_chat_identity(
        repo, session_id=body.session_id, user_id=body.user_id
    )
    await _check_rate_limit(request, uid)
    t0 = time.perf_counter()
    try:
        result = await orch.run_turn(
            session_id=sid,
            user_id=uid,
            message=body.message,
            date_from=body.date_from,
            date_to=body.date_to,
        )
        CHAT_REQUESTS.labels(outcome="ok").inc()
        ORCHESTRATOR_TURN_SECONDS.observe(time.perf_counter() - t0)
        return ChatResponseV2(
            reply=result.reply,
            session_id=result.session_id,
            user_id=result.user_id,
            metadata=result.metadata,
        )
    except Exception:
        CHAT_REQUESTS.labels(outcome="error").inc()
        raise
