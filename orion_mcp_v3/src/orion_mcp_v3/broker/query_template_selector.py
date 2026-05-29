"""Seletor LLM de QueryTemplate baseado em cartões semânticos."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.broker.query_capability_catalog import QueryCapabilityCatalog
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.query_selection import QuerySelectionContract
from orion_mcp_v3.prompts import get_prompt_registry
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


@dataclass(frozen=True, slots=True)
class QuerySelectionValidationResult:
    accepted: bool
    contract: QuerySelectionContract | None = None
    rejected_reason: str | None = None


class QuerySelectionValidator:
    """Valida a escolha do seletor contra capabilities declaradas."""

    _DERIVED_OPERATIONS = frozenset({"below_average"})

    def __init__(self, catalog: QueryCapabilityCatalog, *, min_confidence: float = 0.55) -> None:
        self._catalog = catalog
        self._min_confidence = min_confidence

    def validate(self, contract: QuerySelectionContract) -> QuerySelectionValidationResult:
        if contract.confidence < self._min_confidence:
            return self._reject("confidence_too_low")
        entry = self._catalog.entry_for_template(contract.template_slug)
        if entry is None:
            return self._reject("unsupported_template")

        measure = _resolve_alias(contract.measure, entry.metrics)
        dimension = _resolve_alias(contract.dimension, entry.dimensions)
        operation = contract.operation.strip() if contract.operation else None
        entity_filters = _normalize_entity_filters(contract.entity_filters, entry.dimensions)

        if contract.measure is not None and measure is None:
            return self._reject("unsupported_measure")
        if contract.dimension is not None and dimension is None:
            return self._reject("unsupported_dimension")
        if operation is not None and operation not in entry.operations and operation not in self._DERIVED_OPERATIONS:
            return self._reject("unsupported_operation")
        return QuerySelectionValidationResult(
            accepted=True,
            contract=QuerySelectionContract(
                template_slug=entry.template_slug,
                measure=measure,
                dimension=dimension,
                operation=operation,
                entity_filters=entity_filters,
                confidence=contract.confidence,
                reason=contract.reason,
            ),
        )

    @staticmethod
    def _reject(reason: str) -> QuerySelectionValidationResult:
        return QuerySelectionValidationResult(accepted=False, rejected_reason=reason)


_SYSTEM_PROMPT = get_prompt_registry().get_text("query_template_selector.system")


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
            "entity_filters": [
                {
                    "dimension": "one dimension from the selected query_card",
                    "value": "specific entity value from the user message",
                    "match": "contains|exact",
                }
            ],
            "confidence": "number 0..1",
            "reason": "short string",
        },
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _resolve_alias(value: str | None, options: Mapping[str, tuple[str, ...]]) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    for key, synonyms in options.items():
        values = {key.lower(), *(str(s).lower() for s in synonyms)}
        if raw in values:
            return key
    return None


def _normalize_entity_filters(
    filters: tuple[dict[str, str], ...],
    dimensions: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, str], ...]:
    out: list[dict[str, str]] = []
    for item in filters:
        dimension = _resolve_alias(item.get("dimension"), dimensions)
        value = str(item.get("value") or "").strip()
        if dimension is None or not value:
            continue
        if dimension in _TEMPORAL_FILTER_DIMENSIONS:
            continue
        match = _normalize_filter_match(
            dimension=dimension,
            value=value,
            match=str(item.get("match") or "contains"),
        )
        out.append({"dimension": dimension, "value": value, "match": match})
    return tuple(out)


def _normalize_filter_match(*, dimension: str, value: str, match: str) -> str:
    normalized = match.strip().lower()
    if normalized not in {"contains", "exact"}:
        normalized = "contains"
    if normalized != "exact":
        return normalized
    if dimension in {"periodo", "data_pagamento"} and re.fullmatch(r"20\d{2}(?:-\d{2})?(?:-\d{2})?", value):
        return "exact"
    return "contains"


_TEMPORAL_FILTER_DIMENSIONS = frozenset({"periodo", "data_pagamento"})


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
