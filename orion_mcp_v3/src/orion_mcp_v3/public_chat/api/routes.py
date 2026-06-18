"""Rotas HTTP do Chat Público."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import APIRouter, HTTPException

from orion_mcp_v3.public_chat.api.schemas import AskRequest, AskResponse
from orion_mcp_v3.public_chat.application.consulta_turn_runner import ConsultaTurnRunner
from orion_mcp_v3.public_chat.domain.errors import InvalidParentQuestionError
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import (
    begin_turn_trace,
    log_public_chat_event,
    preview_message,
)
from orion_mcp_v3.public_chat.infrastructure.pipeline_snapshots import preview_answer


class RunnerResolver(Protocol):
    async def __call__(self) -> ConsultaTurnRunner | None: ...


def create_public_ask_router(
    runner_resolver: RunnerResolver | Callable[[], Awaitable[ConsultaTurnRunner | None]],
) -> APIRouter:
    router = APIRouter(prefix="/public", tags=["public-chat"])

    @router.post("/ask", response_model=AskResponse)
    async def public_ask(req: AskRequest) -> AskResponse:
        trace_id = begin_turn_trace()
        t0 = time.monotonic()
        log_public_chat_event(
            etapa="api.ask",
            fase="pre",
            trace_id=trace_id,
            dados={
                **preview_message(req.message),
                "parent_question_id": str(req.parent_question_id) if req.parent_question_id else None,
            },
        )

        runner = await runner_resolver()
        if runner is None:
            log_public_chat_event(
                etapa="api.ask",
                fase="error",
                trace_id=trace_id,
                dados={"reason": "runner_unavailable", "status": 503},
            )
            raise HTTPException(status_code=503, detail="Public chat unavailable")

        try:
            result, presentation = await runner.run_turn_with_metadata(
                req.message,
                parent_question_id=req.parent_question_id,
            )
        except InvalidParentQuestionError as exc:
            log_public_chat_event(
                etapa="api.ask",
                fase="error",
                trace_id=trace_id,
                dados={"reason": "invalid_parent_question", "detail": str(exc), "status": 400},
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log_public_chat_event(
                etapa="api.ask",
                fase="error",
                trace_id=trace_id,
                dados={"reason": type(exc).__name__, "detail": str(exc)},
            )
            raise

        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
        log_public_chat_event(
            etapa="api.ask",
            fase="post",
            trace_id=trace_id,
            dados={
                "latency_ms": elapsed_ms,
                "question_id": str(result.question_id),
                "thread_id": str(result.thread_id),
                "cached": result.cached,
                "topic": result.topic,
                "semantic_hash": result.semantic_hash,
                **preview_answer(presentation),
            },
        )

        return AskResponse(
            message=presentation,
            question_id=str(result.question_id),
            thread_id=str(result.thread_id),
            cached=result.cached,
            topic=result.topic,
            semantic_hash=result.semantic_hash,
        )

    return router
