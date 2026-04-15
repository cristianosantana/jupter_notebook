"""Padrão ILIKE seguro (parâmetro ligado; metacaracteres escapados)."""

from __future__ import annotations


def question_to_ilike_pattern(question: str) -> str:
    q = " ".join((question or "").split())
    if not q:
        return "%"
    parts = q.split()
    escaped: list[str] = []
    for p in parts:
        e = p.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        escaped.append(e)
    core = "%".join(escaped)
    return f"%{core}%"
