"""Rotas HTTP do Chat Público."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import APIRouter, HTTPException

from orion_mcp_v3.public_chat.api.schemas import AskRequest, AskResponse
from orion_mcp_v3.public_chat.application.consulta_turn_runner import ConsultaTurnRunner
from orion_mcp_v3.public_chat.domain.errors import InvalidParentQuestionError


class RunnerResolver(Protocol):
    async def __call__(self) -> ConsultaTurnRunner | None: ...


def create_public_ask_router(
    runner_resolver: RunnerResolver | Callable[[], Awaitable[ConsultaTurnRunner | None]],
) -> APIRouter:
    router = APIRouter(prefix="/public", tags=["public-chat"])

    @router.post("/ask", response_model=AskResponse)
    async def public_ask(req: AskRequest) -> AskResponse:
        runner = await runner_resolver()
        if runner is None:
            raise HTTPException(status_code=503, detail="Public chat unavailable")

        try:
            result, presentation = await runner.run_turn_with_metadata(
                req.message,
                parent_question_id=req.parent_question_id,
            )
        except InvalidParentQuestionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return AskResponse(
            message=presentation,
            question_id=str(result.question_id),
            thread_id=str(result.thread_id),
            cached=result.cached,
            topic=result.topic,
            semantic_hash=result.semantic_hash,
        )

    return router
