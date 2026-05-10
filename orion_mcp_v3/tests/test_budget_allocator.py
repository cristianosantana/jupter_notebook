"""Fase 1.4 — validação MVP do ``budget_allocator``."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime import allocate, estimate_tokens, AttentionPolicy


def _blob(prefix: str, token_target: int) -> str:
    """Texto suficientemente longo para ~token_target tokens (heurística /4)."""
    unit = "x" * 4  # ≈ 1 token
    return prefix + unit * token_target


def test_estimate_tokens_min_one_for_non_empty() -> None:
    assert estimate_tokens("abcd") >= 1
    assert estimate_tokens("") == 0


def test_reserve_system_then_essence_then_relevance_order() -> None:
    s = ContextBlock("SYS", ContextRole.SYSTEM, ContextSource.SYSTEM)
    e = ContextBlock("ESS", ContextRole.USER, ContextSource.ESSENCE)
    hi = ContextBlock("HI", ContextRole.USER, ContextSource.USER_INPUT, relevance_score=0.95)
    lo = ContextBlock("LO", ContextRole.USER, ContextSource.USER_INPUT, relevance_score=0.05)
    out = allocate([lo, hi, e, s], max_tokens=4096)
    assert [x.text for x in out] == ["SYS", "ESS", "HI", "LO"]


def test_truncates_excess() -> None:
    b = ContextBlock("y" * 400, ContextRole.USER, ContextSource.USER_INPUT, relevance_score=1.0)
    out = allocate([b], max_tokens=10)
    assert len(out) == 1
    assert out[0].metadata.get("truncated") is True
    assert estimate_tokens(out[0].text) <= 10


def test_higher_relevance_wins_tight_budget() -> None:
    low = ContextBlock(_blob("a", 15), ContextRole.USER, ContextSource.BROKER, relevance_score=0.1)
    high = ContextBlock(_blob("b", 15), ContextRole.USER, ContextSource.BROKER, relevance_score=0.99)
    out = allocate([low, high], max_tokens=20)
    assert out[0] is high
    total = sum(estimate_tokens(x.text) for x in out)
    assert total <= 20


def test_allocate_empty() -> None:
    assert allocate([], max_tokens=100) == []


def test_elastic_path_orders_data_before_memory_zones() -> None:
    """Com DATA+MEMORY presentes, a fracção livre usa trilha elástica; ordem: DATA depois MEMORY."""
    data = ContextBlock(
        "D" + "x" * 200,
        ContextRole.DATA,
        ContextSource.BROKER,
        block_id="bloco-data",
        relevance_score=0.4,
    )
    mem = ContextBlock(
        "M" + "y" * 200,
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="bloco-mem",
        relevance_score=0.99,
    )
    out = allocate([data, mem], max_tokens=500, policy=AttentionPolicy.ANALYTICAL)
    assert len(out) == 2
    assert out[0].block_id == "bloco-data"
    assert out[1].block_id == "bloco-mem"
    assert sum(estimate_tokens(b.text) for b in out) <= 500
