from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion_mcp_v2.llm_provider.openai_provider import OpenAIChatService
    from orion_mcp_v2.skill.loader import SkillRegistry

_logger = logging.getLogger(__name__)


async def summarize_sessions_block(
    sessions_json: str,
    skills: "SkillRegistry",
    llm: "OpenAIChatService",
) -> dict[str, Any]:
    spec = skills.get("memory_consolidator")
    sys_p = spec.render_system(sessions_json=sessions_json[:14000])
    raw = await llm.complete(
        system_prompt=sys_p,
        user_text="Produza o JSON pedido.",
        model=spec.model,
        max_tokens=spec.max_tokens,
    )
    try:
        data = json.loads(raw or "{}")
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        _logger.warning("consolidator_json_failed")
    return {"summary": raw[:2000], "key_metrics": {}, "recent_questions": []}
