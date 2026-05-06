from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orion_mcp_v2.memory.models import MemoryCurta


def build_memory_curta(
    *,
    user_id: str,
    category: str,
    consolidated_body: dict[str, Any],
    last_query_hint: dict[str, Any] | None = None,
) -> MemoryCurta:
    summary = str(consolidated_body.get("summary") or consolidated_body.get("text") or "").strip()
    km = consolidated_body.get("key_metrics") if isinstance(consolidated_body.get("key_metrics"), dict) else {}
    rq = consolidated_body.get("recent_questions")
    recent: list[str] = []
    if isinstance(rq, list):
        recent = [str(x) for x in rq[:12]]
    return MemoryCurta(
        user_id=user_id,
        category=category,
        consolidated_at=datetime.now(timezone.utc),
        summary=summary or "(sem resumo)",
        key_metrics=km,
        recent_questions=recent,
        last_results=last_query_hint,
    )
