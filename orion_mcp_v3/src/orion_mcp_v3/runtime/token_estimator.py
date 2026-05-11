"""Estimativa determinística de custo em tokens (heurística caracteres / razão)."""

from __future__ import annotations

_CHARS_PER_TOKEN_ESTIMATE: int = 4


def estimate_tokens(text: str) -> int:
    """Heurística alinhada a prompts LLM típicos (≈ caracteres / 4)."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)
