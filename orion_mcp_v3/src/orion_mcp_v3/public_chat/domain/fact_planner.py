"""Fact Planner híbrido — determinístico + LLM fallback."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_requirements import (
    fact_keys_for_contract,
    is_composite_question,
)
from orion_mcp_v3.public_chat.domain.fact_semantics_catalog import FactSemanticsCatalog, get_fact_semantics_catalog
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event
from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry

_LLM_FALLBACK_CONFIDENCE = 0.7


@dataclass(frozen=True, slots=True)
class FactPlanResult:
    requirements: tuple[FactRequirement, ...]
    composite: bool
    used_llm_fallback: bool
    confidence: float


class FactPlanner:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        catalog: FactSemanticsCatalog | None = None,
        max_tokens: int = 512,
    ) -> None:
        self._provider = provider
        self._catalog = catalog or get_fact_semantics_catalog()
        self._max_tokens = max_tokens

    async def plan(self, message: str, *, contract: IntentContract) -> FactPlanResult:
        t0 = time.monotonic()
        composite = is_composite_question(contract, message)
        deterministic_keys = fact_keys_for_contract(contract, message)
        used_llm = False
        confidence = contract.confidence

        if not deterministic_keys or confidence < _LLM_FALLBACK_CONFIDENCE or composite:
            llm_keys = await self._llm_fact_keys(message, contract)
            if llm_keys:
                deterministic_keys = tuple(dict.fromkeys((*deterministic_keys, *llm_keys)))
                used_llm = True

        requirements: list[FactRequirement] = []
        for fact_key in deterministic_keys:
            semantics = self._catalog.get(fact_key)
            if semantics is None:
                continue
            requirements.append(
                FactRequirement(
                    fact_key=fact_key,
                    metric=contract.metric,
                    dimension=contract.dimension,
                    entity=_entity_from_contract(contract),
                    period=contract.period,
                    operation=contract.operation,
                    semantics=semantics,
                )
            )

        result = FactPlanResult(
            requirements=tuple(requirements),
            composite=composite or len(requirements) >= 2,
            used_llm_fallback=used_llm,
            confidence=confidence,
        )
        log_public_chat_event(
            etapa="fact.plan",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "composite": result.composite,
                "used_llm_fallback": result.used_llm_fallback,
                "confidence": result.confidence,
                "requirements": [req.as_mapping() for req in result.requirements],
                "fact_keys": [req.fact_key for req in result.requirements],
            },
        )
        return result

    async def _llm_fact_keys(self, message: str, contract: IntentContract) -> tuple[str, ...]:
        if self._provider is None:
            return ()
        try:
            system = get_public_chat_prompt_registry().get_text("public_chat_fact_planner.system")
        except KeyError:
            return ()
        prompt = json.dumps(
            {
                "message": message,
                "intent_contract": contract.as_mapping(),
                "available_fact_keys": list(self._catalog.fact_keys),
            },
            ensure_ascii=False,
        )
        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=prompt),
        ]
        try:
            response = await self._provider.complete(messages, max_tokens=self._max_tokens, temperature=0)
        except Exception:
            return ()
        return _parse_llm_fact_keys(response.content)


def _entity_from_contract(contract: IntentContract) -> str | None:
    for filt in contract.entity_filters:
        if filt.value:
            return filt.value
    if contract.dimension == "forma_pagamento":
        return None
    return None


def _parse_llm_fact_keys(content: str) -> tuple[str, ...]:
    text = (content or "").strip()
    if not text:
        return ()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return ()
    raw = parsed.get("fact_keys") if isinstance(parsed, dict) else None
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw if item)
