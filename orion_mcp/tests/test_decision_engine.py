import pytest

from orion_mcp.core.decision.actions import Action
from orion_mcp.core.decision.decision_engine import DecisionContext, decide
from orion_mcp.core.state.models import DataCacheEntry, State
from orion_mcp.core.strategy import Strategy


def test_decide_call_tool_when_cache_empty() -> None:
    s = State()
    assert decide(s, "hello", Strategy.fast) == Action.CALL_TOOL


def test_decide_format_when_intent_and_cache() -> None:
    s = State(intent="format_only", data_cache={"k": DataCacheEntry(summary="x")})
    assert decide(s, "tabela", Strategy.fast) == Action.FORMAT_RESPONSE


def test_decide_insights_when_why_and_cache_and_no_tool_yet() -> None:
    s = State(intent="why_question", data_cache={"k": DataCacheEntry(summary="x")})
    ctx = DecisionContext(tool_calls_used=0)
    assert decide(s, "por que?", Strategy.fast, ctx=ctx) == Action.GENERATE_INSIGHTS


def test_decide_response_when_why_but_tool_already_used() -> None:
    s = State(intent="why_question", data_cache={"k": DataCacheEntry(summary="x")})
    ctx = DecisionContext(tool_calls_used=1)
    assert decide(s, "por que?", Strategy.fast, ctx=ctx) == Action.GENERATE_RESPONSE


def test_deterministic_same_input() -> None:
    s = State(data_cache={"k": DataCacheEntry(summary="x")})
    a1 = decide(s, "ok", Strategy.fast)
    a2 = decide(s, "ok", Strategy.fast)
    assert a1 == a2 == Action.GENERATE_RESPONSE


def test_decide_domain_pending_key_missing_from_cache_calls_tool() -> None:
    s = State(
        data_cache={"other-key": DataCacheEntry(summary="old")},
        flags={"pending_domain_tool_cache_key": "need-this-key"},
    )
    ctx = DecisionContext(tool_calls_used=0)
    assert decide(s, "x", Strategy.fast, ctx=ctx) == Action.CALL_TOOL


def test_decide_domain_pending_key_in_cache_skips_tool() -> None:
    k = "same-key"
    s = State(
        data_cache={k: DataCacheEntry(summary="fresh")},
        flags={"pending_domain_tool_cache_key": k},
    )
    ctx = DecisionContext(tool_calls_used=0)
    assert decide(s, "x", Strategy.fast, ctx=ctx) == Action.GENERATE_RESPONSE


def test_decide_force_refresh_respects_tool_budget() -> None:
    s = State(flags={"force_refresh": True}, data_cache={})
    ctx = DecisionContext(tool_calls_used=1)
    assert decide(s, "atualizar", Strategy.fast, ctx=ctx) == Action.GENERATE_RESPONSE
