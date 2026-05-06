from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion_mcp_v2.config.settings import Settings

from orion_mcp_v2.core.context.builder_aggregate_section import format_skill_aggregate_section
from orion_mcp_v2.core.context.context_caps import effective_llm_prompt_token_cap


def build_user_prompt(
    *,
    settings: "Settings",
    question: str,
    pipeline_out: dict[str, Any],
    redis_memory: dict[str, Any] | None,
    recent_user_messages: list[str],
) -> str:
    eff_chars = max(2048, effective_llm_prompt_token_cap(settings) * 4)
    redis_max = min(6000, eff_chars // 4)
    summary_max = min(8000, eff_chars // 3)
    insights_max = min(4000, eff_chars // 6)
    sample_max = min(6000, eff_chars // 4)
    total_cap = min(24000, eff_chars * 3)

    parts: list[str] = []
    parts.append("### Pergunta atual\n" + (question or "").strip())

    if redis_memory:
        parts.append(
            "### Memória curta (Redis)\n"
            + json.dumps(redis_memory, ensure_ascii=False)[:redis_max]
        )

    parts.append(
        "### Dados resumidos (determinístico)\n"
        + json.dumps(pipeline_out.get("summary"), ensure_ascii=False)[:summary_max]
    )
    parts.append("### Insights\n" + "\n".join(pipeline_out.get("insights") or [])[:insights_max])
    parts.append(
        "### Amostra\n"
        + json.dumps(pipeline_out.get("sample"), ensure_ascii=False)[:sample_max]
    )

    agg_block = format_skill_aggregate_section(pipeline_out, settings=settings)
    if agg_block:
        parts.append(agg_block)

    if recent_user_messages:
        tail = recent_user_messages[-5:]
        parts.append("### Perguntas recentes na sessão\n" + "\n".join(f"- {x}" for x in tail))

    text = "\n\n".join(parts)
    if len(text) > total_cap:
        text = text[:total_cap] + "\n… [truncado]"
    return text
