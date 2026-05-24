"""
Fase 0 — Fundação semântica (`docs/roadmaps/ROADMAP_EXECUTÁVEL.md`).

Tarefas 0.2 ContextBlock, 0.3 proveniência, 0.4 RuntimeEvent, 0.5 SemanticQueryPlan.
Sem lógica de allocator/scheduler — apenas contratos imutáveis e enums.
"""

from __future__ import annotations

import pytest

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.runtime.events import RuntimeEvent, RuntimeEventType
from orion_mcp_v3.runtime.provenance import CoverageInfo, ProvenanceAnchor


def test_task_02_context_source_role_block() -> None:
    b = ContextBlock(
        "hello",
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="t1",
        metadata={"k": 1},
        relevance_score=0.5,
    )
    assert b.text == "hello"
    assert b.role == ContextRole.USER
    assert b.source == ContextSource.USER_INPUT
    assert b.block_id == "t1"
    assert b.metadata["k"] == 1
    assert b.relevance_score == 0.5


def test_task_02_context_block_is_frozen() -> None:
    b = ContextBlock("x", ContextRole.SYSTEM, ContextSource.SYSTEM)
    with pytest.raises(Exception):
        b.text = "y"  # type: ignore[misc]


def test_task_03_provenance_anchor_and_coverage() -> None:
    pa = ProvenanceAnchor(
        artifact_id="a1",
        source="mysql",
        lineage=("step1",),
        metadata={"t": "vendas"},
    )
    assert pa.artifact_id == "a1"
    cov = CoverageInfo(labels={"rows": 100}, notes="ok")
    assert cov.labels["rows"] == 100


def test_task_04_runtime_event_types_and_payload() -> None:
    for et in (
        RuntimeEventType.DIGEST_CREATED,
        RuntimeEventType.MEMORY_PROMOTED,
        RuntimeEventType.BUDGET_EXCEEDED,
        RuntimeEventType.CONFLICT_DETECTED,
    ):
        ev = RuntimeEvent(et, payload={"x": 1}, trace_id="tid")
        assert ev.event_type == et
        assert ev.payload["x"] == 1
        assert ev.trace_id == "tid"


def test_task_05_semantic_query_plan_and_strategy() -> None:
    p = SemanticQueryPlan(
        intent_slug="analytics.foo",
        strategy=RetrievalStrategy.BROKER_FANOUT,
        target_collections=("c1",),
        hints={"k": "v"},
        correlation_id="cid",
    )
    assert p.intent_slug == "analytics.foo"
    assert p.strategy == RetrievalStrategy.BROKER_FANOUT
    assert p.target_collections == ("c1",)
    assert p.hints["k"] == "v"
    assert p.correlation_id == "cid"


def test_digest_contract_compatible_with_phase0_exports() -> None:
    """AnalyticalDigest vive em contracts (camadas posteriores); smoke para pacote."""
    d = AnalyticalDigest(summary="s", volume=0)
    assert d.summary == "s"
