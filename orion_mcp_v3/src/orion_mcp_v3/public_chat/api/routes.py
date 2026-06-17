"""Rotas HTTP do Chat Público."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from orion_mcp_v3.public_chat.api.schemas import AskRequest
from orion_mcp_v3.public_chat.application.consulta_turn_runner import (
    ConsultaTurnRunner,
    TurnStreamChunk,
)
from orion_mcp_v3.public_chat.domain.errors import InvalidParentQuestionError


class RunnerResolver(Protocol):
    async def __call__(self) -> ConsultaTurnRunner | None: ...


def _chunk_to_sse(chunk: TurnStreamChunk) -> list[str]:
    events: list[str] = []
    if chunk.delta:
        payload = json.dumps({"delta": chunk.delta}, ensure_ascii=False)
        events.append(f"data: {payload}\n\n")
    if chunk.result is not None:
        done = json.dumps(
            {
                "finish_reason": "stop",
                "question_id": str(chunk.result.question_id),
                "thread_id": str(chunk.result.thread_id),
                "cached": chunk.result.cached,
                "topic": chunk.result.topic,
                "semantic_hash": chunk.result.semantic_hash,
            },
            ensure_ascii=False,
        )
        events.append(f"data: {done}\n\n")
    return events


def create_public_ask_router(
    runner_resolver: RunnerResolver | Callable[[], Awaitable[ConsultaTurnRunner | None]],
) -> APIRouter:
    router = APIRouter(prefix="/public", tags=["public-chat"])

    @router.post("/ask")
    async def public_ask(req: AskRequest) -> StreamingResponse:
        runner = await runner_resolver()
        if runner is None:
            raise HTTPException(status_code=503, detail="Public chat unavailable")

        stream = runner.run_turn(req.message, parent_question_id=req.parent_question_id)
        try:
            first_chunk = await stream.__anext__()
        except StopAsyncIteration:
            first_chunk = None
        except InvalidParentQuestionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        async def event_generator() -> AsyncIterator[str]:
            if first_chunk is not None:
                for line in _chunk_to_sse(first_chunk):
                    yield line
            try:
                async for chunk in stream:
                    for line in _chunk_to_sse(chunk):
                        yield line
            except InvalidParentQuestionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
