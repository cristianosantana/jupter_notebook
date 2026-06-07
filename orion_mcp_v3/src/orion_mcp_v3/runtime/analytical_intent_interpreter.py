"""Interpretador LLM para intenção analítica estruturada."""

from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence

from orion_mcp_v3.broker.query_capability_catalog import QueryCapabilityCatalog
from orion_mcp_v3.contracts.analytical_intent import (
    AnalyticalDateRange,
    AnalyticalIntentContract,
    AnalyticalIntentType,
    AnalyticalOperation,
    SourcePeriods,
)
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.memory.repositories.conversation_state import ConversationMessage
from orion_mcp_v3.prompts import get_prompt_registry
from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider
from orion_mcp_v3.runtime.heuristic_signal_catalog import HeuristicSignalCatalog

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AnalyticalMemoryTurn:
    role: str
    content: str

    def as_prompt_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content[:1200]}


@dataclass(frozen=True, slots=True)
class AnalyticalMemoryContext:
    turns: tuple[AnalyticalMemoryTurn, ...] = ()
    has_analytical_memory: bool = False

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "has_analytical_memory": self.has_analytical_memory,
            "turns": [turn.as_prompt_dict() for turn in self.turns],
        }


def memory_context_from_messages(
    messages: Sequence[ConversationMessage],
    *,
    current_message: str,
    limit: int = 8,
) -> AnalyticalMemoryContext:
    current = (current_message or "").strip()
    prior: list[ConversationMessage] = []
    for msg in messages:
        if msg.role == "user" and msg.content.strip() == current and msg is messages[-1]:
            continue
        prior.append(msg)
    selected = prior[-limit:]
    turns = tuple(
        AnalyticalMemoryTurn(role=msg.role, content=msg.content)
        for msg in selected
        if msg.content.strip()
    )
    analytical_markers = (
        "resposta direta",
        "answer_plan",
        "analytical_signature",
        "faturamento",
        "vendas",
        "ticket",
        "concession",
        "vendedor",
    )
    has_analytical = any(
        any(marker in turn.content.lower() for marker in analytical_markers)
        for turn in turns
    )
    return AnalyticalMemoryContext(turns=turns, has_analytical_memory=has_analytical)


class AnalyticalIntentInterpreter:
    def __init__(self, provider: LLMProvider, *, max_tokens: int = 1200) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    async def interpret(
        self,
        message: str,
        *,
        recent_context: AnalyticalMemoryContext,
        capabilities: QueryCapabilityCatalog,
        regex_signals: HeuristicSignalCatalog,
        heuristic_plan: CognitivePlan,
    ) -> AnalyticalIntentContract | None:
        collection_contract = _collection_contract_from_message(
            message,
            capabilities=capabilities,
            heuristic_plan=heuristic_plan,
        )
        if collection_contract is not None:
            return collection_contract

        prompt = _build_prompt(
            message,
            recent_context=recent_context,
            capabilities=capabilities,
            regex_signals=regex_signals,
            heuristic_plan=heuristic_plan,
        )
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
            _LOG.exception("analytical intent interpreter provider failed")
            return None

        payload = _parse_json_object(response.text)
        if payload is None:
            return None
        try:
            return AnalyticalIntentContract.from_mapping(payload)
        except (TypeError, ValueError):
            _LOG.info("analytical intent interpreter rejected invalid contract json")
            return None


_SYSTEM_PROMPT = get_prompt_registry().get_text("analytical_intent.system")


def _build_prompt(
    message: str,
    *,
    recent_context: AnalyticalMemoryContext,
    capabilities: QueryCapabilityCatalog,
    regex_signals: HeuristicSignalCatalog,
    heuristic_plan: CognitivePlan,
) -> str:
    payload = {
        "user_message": message,
        "recent_context": recent_context.as_prompt_dict(),
        "declared_capabilities": capabilities.as_prompt_dict(),
        "collection_cards": capabilities.collection_cards_prompt(),
        "heuristic_signals": regex_signals.as_prompt_dict(),
        "heuristic_plan": {
            "intent_type": heuristic_plan.intent_type.value,
            "needs_analytics": heuristic_plan.needs_analytics,
            "needs_memory": heuristic_plan.needs_memory,
            "needs_comparison": heuristic_plan.needs_comparison,
            "metrics": list(heuristic_plan.metrics),
            "entities": list(heuristic_plan.entities),
            "time_scope": heuristic_plan.time_scope,
            "confidence": heuristic_plan.confidence,
        },
        "allowed_output": {
            "intent_type": [
                "analytical",
                "comparative",
                "temporal",
                "recall",
                "monitoring",
                "execution",
                "hybrid",
                "conversational",
            ],
            "operation": [
                "list",
                "ranking_desc",
                "ranking_asc",
                "top_and_bottom",
                "comparison",
                "delta",
                "summary",
                "collection",
            ],
            "source_periods": [
                "explicit",
                "last_analytical_turn",
                "last_two_analytical_turns",
                "none",
            ],
        },
        "required_json_shape": {
            "intent_type": "string",
            "operation": "string",
            "needs_analytics": "boolean",
            "needs_memory": "boolean",
            "needs_comparison": "boolean",
            "template_slug": "string|null",
            "collection_slug": "string|null",
            "metric": "string|null",
            "dimension": "string|null",
            "date_ranges": [
                {"label": "string", "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"}
            ],
            "source_periods": "string",
            "inherits_from_previous": ["metric|dimension|operation|period"],
            "entity_filters": [
                {"dimension": "capability dimension", "value": "specific entity value", "match": "contains|exact"}
            ],
            "confidence": "number 0..1",
        },
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _collection_contract_from_message(
    message: str,
    *,
    capabilities: QueryCapabilityCatalog,
    heuristic_plan: CognitivePlan,
) -> AnalyticalIntentContract | None:
    text = _norm(message)
    for card in capabilities.collections:
        if not any(_norm(description) in text for description in card.descriptions):
            continue
        date_ranges = _date_ranges_from_time_scope(heuristic_plan.time_scope)
        return AnalyticalIntentContract(
            intent_type=AnalyticalIntentType.ANALYTICAL,
            operation=AnalyticalOperation.COLLECTION,
            needs_analytics=True,
            needs_memory=heuristic_plan.needs_memory,
            needs_comparison=False,
            collection_slug=card.collection_slug,
            date_ranges=date_ranges,
            source_periods=SourcePeriods.EXPLICIT if date_ranges else SourcePeriods.NONE,
            confidence=max(0.9, heuristic_plan.confidence),
        )
    return None


def _date_ranges_from_time_scope(time_scope: str | None) -> tuple[AnalyticalDateRange, ...]:
    if not time_scope or "/" not in time_scope:
        return ()
    date_from, date_to = (part.strip() for part in time_scope.split("/", 1))
    if not date_from or not date_to:
        return ()
    return (AnalyticalDateRange(label="requested_period", date_from=date_from, date_to=date_to),)


def _norm(text: str) -> str:
    raw = "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )
    return " ".join(raw.split())


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
