from __future__ import annotations

from collections.abc import Sequence

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES
from orion_mcp_v3.broker.query_capability_catalog import build_query_capability_catalog
from orion_mcp_v3.protocols.llm import ChatMessage, LLMResponse, LLMResponseMeta
from orion_mcp_v3.runtime.analytical_intent_interpreter import (
    AnalyticalIntentInterpreter,
    AnalyticalMemoryContext,
)
from orion_mcp_v3.runtime.heuristic_signal_catalog import extract_heuristic_signals
from orion_mcp_v3.runtime.intent_resolver import IntentResolver


class FakeIntentProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def generate(self, prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        return LLMResponse(text=self.text, meta=LLMResponseMeta(model="fake"))

    async def chat(self, messages: Sequence[ChatMessage], **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return LLMResponse(text=self.text, meta=LLMResponseMeta(model="fake"))

    async def stream(self, messages: Sequence[ChatMessage], **kwargs):  # type: ignore[no-untyped-def]
        yield ""


async def test_interpreter_returns_contract_from_json() -> None:
    provider = FakeIntentProvider(
        """
        {
          "intent_type": "comparative",
          "operation": "delta",
          "needs_analytics": true,
          "needs_memory": true,
          "needs_comparison": true,
          "template_slug": "performance_vendedor",
          "metric": "sales",
          "dimension": "seller",
          "date_ranges": [
            {"label": "março", "date_from": "2026-03-01", "date_to": "2026-03-31"},
            {"label": "abril", "date_from": "2026-04-01", "date_to": "2026-04-30"}
          ],
          "source_periods": "explicit",
          "inherits_from_previous": [],
          "confidence": 0.92
        }
        """
    )
    message = "compare março e abril por vendedor"
    heuristic = IntentResolver().resolve(message)

    contract = await AnalyticalIntentInterpreter(provider).interpret(
        message,
        recent_context=AnalyticalMemoryContext(),
        capabilities=build_query_capability_catalog(ANALYTICS_TEMPLATES),
        regex_signals=extract_heuristic_signals(message),
        heuristic_plan=heuristic,
    )

    assert provider.calls == 1
    assert contract is not None
    assert contract.intent_type.value == "comparative"
    assert contract.needs_comparison is True
    assert contract.template_slug == "performance_vendedor"


async def test_interpreter_returns_none_for_non_json() -> None:
    provider = FakeIntentProvider("isso não é json")
    message = "olá"
    heuristic = IntentResolver().resolve(message)

    contract = await AnalyticalIntentInterpreter(provider).interpret(
        message,
        recent_context=AnalyticalMemoryContext(),
        capabilities=build_query_capability_catalog(ANALYTICS_TEMPLATES),
        regex_signals=extract_heuristic_signals(message),
        heuristic_plan=heuristic,
    )

    assert contract is None
