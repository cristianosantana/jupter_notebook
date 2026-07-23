"""No-op de tracing — Senna não grava pipeline_trace do chat."""

from __future__ import annotations

from typing import Any


def log_public_chat_event(*, etapa: str, fase: str, dados: dict[str, Any] | None = None) -> None:
    return None


def preview_message(message: str) -> dict[str, Any]:
    text = (message or "").strip()
    return {"message_preview": text[:80], "message_chars": len(text)}


def snapshot_knowledge_hit(hit: Any) -> dict[str, Any]:
    return {
        "origin_id": getattr(hit, "origin_id", None),
        "context_key": getattr(hit, "context_key", None),
    }


def snapshot_vector_matches(matches: list[tuple[int, float | None]]) -> list[dict[str, Any]]:
    return [{"origin_id": oid, "score": score} for oid, score in matches]


def log_memory_accessed(**_kwargs: Any) -> None:
    return None
