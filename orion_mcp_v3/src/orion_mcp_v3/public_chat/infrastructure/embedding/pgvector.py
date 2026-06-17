"""Utilitários pgvector isolados do Chat Público."""

from __future__ import annotations

from typing import Sequence


def to_pgvector(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"
