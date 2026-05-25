"""Seletor LLM de QueryTemplate baseado em cartões semânticos."""

from __future__ import annotations

import json
import logging
from typing import Any

from orion_mcp_v3.broker.query_capability_catalog import QueryCapabilityCatalog
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.query_selection import QuerySelectionContract
from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider, NullLLMProvider

_LOG = logging.getLogger(__name__)


class QueryTemplateSelector:
    """Escolhe uma visão analítica declarada; não gera nem aceita SQL."""

    def __init__(self, provider: LLMProvider, *, max_tokens: int = 900) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    async def select(
        self,
        message: str,
        *,
        cognitive_plan: CognitivePlan,
        capabilities: QueryCapabilityCatalog,
    ) -> QuerySelectionContract | None:
        if isinstance(self._provider, NullLLMProvider):
            return None
        prompt = _build_prompt(message, cognitive_plan=cognitive_plan, capabilities=capabilities)
        try:
            response = await self._provider.chat(
                [
                    ChatMessage(role="system", content=_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=self._max_tokens,
                temperature=0,
            )
        except Exception:
            _LOG.exception("query template selector provider failed")
            return None

        payload = _parse_json_object(response.text)
        if payload is None or "sql" in {str(k).lower() for k in payload}:
            return None
        try:
            contract = QuerySelectionContract.from_mapping(payload)
        except (TypeError, ValueError):
            return None
        return contract if contract.template_slug else None


_SYSTEM_PROMPT = """You are a query template selector.
Return exactly one JSON object and no prose.
Never generate SQL.
Never answer the user.
Choose template_slug only from the query_cards.
Prefer the template whose dimensions match the user's requested business entity.
"""


def _build_prompt(
    message: str,
    *,
    cognitive_plan: CognitivePlan,
    capabilities: QueryCapabilityCatalog,
) -> str:
    payload = {
        "user_message": message,
        "cognitive_plan": {
            "intent_type": cognitive_plan.intent_type.value,
            "needs_analytics": cognitive_plan.needs_analytics,
            "needs_comparison": cognitive_plan.needs_comparison,
            "metrics": list(cognitive_plan.metrics),
            "entities": list(cognitive_plan.entities),
            "time_scope": cognitive_plan.time_scope,
        },
        "query_cards": capabilities.query_cards_prompt(),
        "required_json_shape": {
            "template_slug": "string from query_cards",
            "measure": "string|null",
            "dimension": "string|null",
            "operation": "string|null",
            "confidence": "number 0..1",
            "reason": "short string",
        },
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None
