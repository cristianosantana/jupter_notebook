from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from orion_mcp_v2.core.decision.engine import BusinessIntent

if TYPE_CHECKING:
    from orion_mcp_v2.llm_provider.openai_provider import OpenAIChatService
    from orion_mcp_v2.skill.loader import SkillRegistry

_logger = logging.getLogger(__name__)

_JSON_OBJ = re.compile(r"\{[\s\S]*\}")


async def categorize_conversation_text(
    conversation_text: str,
    skills: "SkillRegistry",
    llm: "OpenAIChatService",
) -> BusinessIntent:
    spec = skills.get("session_intent_analyzer")
    sys_p = spec.render_system(conversation_text=conversation_text[:12000])
    raw = await llm.complete(
        system_prompt=sys_p,
        user_text='Responda apenas com JSON no formato especificado.',
        model=spec.model,
        max_tokens=spec.max_tokens,
    )
    m = _JSON_OBJ.search(raw or "")
    blob = m.group(0) if m else raw
    try:
        data = json.loads(blob or "{}")
        pri = str(data.get("primary_intent") or "").strip().upper()
        for bi in BusinessIntent:
            if bi.value == pri:
                return bi
    except json.JSONDecodeError:
        _logger.warning("intent_json_parse_failed", extra={"raw": raw[:200]})
    # fallback heurístico
    from orion_mcp_v2.core.decision.engine import _detect_intent

    return _detect_intent(conversation_text)
