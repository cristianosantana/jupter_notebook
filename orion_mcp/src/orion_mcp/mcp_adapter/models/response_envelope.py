from __future__ import annotations

from typing import Any


def tool_envelope(
    *,
    tool_name: str,
    value: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Envelope JSON estável para o cliente / LLM (V1).
    O núcleo consome preferencialmente `value` (shape da tool in-process).
    """
    return {
        "type": "tool_result",
        "name": tool_name,
        "value": value,
        "metadata": metadata or {},
    }


def envelope_value(envelope: dict[str, Any]) -> dict[str, Any]:
    """Extrai o dict de negócio do envelope; fallback se formato legado."""
    if isinstance(envelope.get("value"), dict):
        return envelope["value"]
    return envelope
