"""Interpretador LLM para escopo e apresentação da resposta analítica."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.broker.query_capability_catalog import QueryCapabilityCatalog
from orion_mcp_v3.contracts.answer_presentation import AnswerPresentationContract
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.query_selection import QuerySelectionContract
from orion_mcp_v3.prompts import get_prompt_registry
from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider, NullLLMProvider

_LOG = logging.getLogger(__name__)


class AnswerPresentationInterpreter:
    def __init__(self, provider: LLMProvider, *, max_tokens: int = 700) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    async def interpret(
        self,
        message: str,
        *,
        cognitive_plan: CognitivePlan,
        query_selection: QuerySelectionContract,
        capabilities: QueryCapabilityCatalog,
    ) -> AnswerPresentationContract | None:
        if query_selection.selection_kind == "collection" or query_selection.collection_slug is not None:
            return AnswerPresentationContract(
                result_scope={"mode": "all", "limit": None},
                sort=None,
                confidence=max(0.9, query_selection.confidence),
                reason="collection_default_presentation",
            )
        if isinstance(self._provider, NullLLMProvider):
            return None
        prompt = _build_prompt(
            message,
            cognitive_plan=cognitive_plan,
            query_selection=query_selection,
            capabilities=capabilities,
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
            _LOG.exception("answer presentation interpreter provider failed")
            return None

        payload = _parse_json_object(response.text)
        if payload is None or "sql" in {str(k).lower() for k in payload}:
            return None
        try:
            return AnswerPresentationContract.from_mapping(payload)
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class AnswerPresentationValidationResult:
    accepted: bool
    contract: AnswerPresentationContract | None = None
    rejected_reason: str | None = None


class AnswerPresentationValidator:
    def __init__(self, catalog: QueryCapabilityCatalog, *, min_confidence: float = 0.55) -> None:
        self._catalog = catalog
        self._min_confidence = min_confidence

    def validate(
        self,
        contract: AnswerPresentationContract,
        *,
        query_selection: QuerySelectionContract,
    ) -> AnswerPresentationValidationResult:
        if contract.confidence < self._min_confidence:
            return self._reject("confidence_too_low")
        if query_selection.selection_kind == "collection" or query_selection.collection_slug is not None:
            collection = self._catalog.collection_card(query_selection.collection_slug)
            if collection is None:
                return self._reject("unsupported_collection")
            result_scope = _normalize_result_scope(contract.result_scope) or {"mode": "all", "limit": None}
            return AnswerPresentationValidationResult(
                accepted=True,
                contract=AnswerPresentationContract(
                    result_scope=result_scope,
                    sort=None,
                    confidence=contract.confidence,
                    reason=contract.reason or "collection_default_presentation",
                ),
            )
        entry = self._catalog.entry_for_template(query_selection.template_slug)
        if entry is None:
            return self._reject("unsupported_template")
        result_scope = _normalize_result_scope(contract.result_scope)
        sort = _normalize_sort(contract.sort, entry.metrics, entry.dimensions)
        return AnswerPresentationValidationResult(
            accepted=True,
            contract=AnswerPresentationContract(
                result_scope=result_scope,
                sort=sort,
                confidence=contract.confidence,
                reason=contract.reason,
            ),
        )

    @staticmethod
    def _reject(reason: str) -> AnswerPresentationValidationResult:
        return AnswerPresentationValidationResult(accepted=False, rejected_reason=reason)


_SYSTEM_PROMPT = get_prompt_registry().get_text("answer_presentation.system")


def _build_prompt(
    message: str,
    *,
    cognitive_plan: CognitivePlan,
    query_selection: QuerySelectionContract,
    capabilities: QueryCapabilityCatalog,
) -> str:
    entry = capabilities.entry_for_template(query_selection.template_slug)
    selected_card = entry.as_prompt_dict() if entry is not None else None
    payload = {
        "user_message": message,
        "cognitive_plan": {
            "intent_type": cognitive_plan.intent_type.value,
            "metrics": list(cognitive_plan.metrics),
            "entities": list(cognitive_plan.entities),
            "time_scope": cognitive_plan.time_scope,
        },
        "query_selection": query_selection.as_dict(),
        "selected_query_card": selected_card,
        "required_json_shape": {
            "result_scope": {"mode": "all|top_n|bottom_n|sample", "limit": "integer|null"},
            "sort": {"field": "measure or dimension from selected_query_card", "direction": "asc|desc"},
            "confidence": "number 0..1",
            "reason": "short string",
        },
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _normalize_result_scope(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    mode = str(raw.get("mode") or "").strip().lower()
    if mode not in {"all", "top_n", "bottom_n", "sample"}:
        return None
    limit_raw = raw.get("limit")
    limit: int | None = None
    if limit_raw not in (None, ""):
        try:
            limit = max(1, int(limit_raw))
        except (TypeError, ValueError):
            limit = None
    return {"mode": mode, "limit": limit}


def _normalize_sort(
    raw: Mapping[str, str] | None,
    metrics: Mapping[str, tuple[str, ...]],
    dimensions: Mapping[str, tuple[str, ...]],
) -> dict[str, str] | None:
    if not isinstance(raw, Mapping):
        return None
    field = _resolve_alias(raw.get("field"), metrics) or _resolve_alias(raw.get("field"), dimensions)
    direction = str(raw.get("direction") or "desc").strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "desc"
    if field is None:
        return {"field": "", "direction": direction}
    return {"field": field, "direction": direction}


def _resolve_alias(value: str | None, options: Mapping[str, tuple[str, ...]]) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    for key, synonyms in options.items():
        values = {key.lower(), *(str(s).lower() for s in synonyms)}
        if raw in values:
            return key
    return None


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
