"""Schemas HTTP do Chat Público."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    message: str = Field(..., min_length=1)
    parent_question_id: UUID | None = None


class AskDeltaEvent(BaseModel):
    delta: str


class AskFinishEvent(BaseModel):
    finish_reason: str = "stop"
    question_id: str
    thread_id: str
    cached: bool
    topic: str
    semantic_hash: str
