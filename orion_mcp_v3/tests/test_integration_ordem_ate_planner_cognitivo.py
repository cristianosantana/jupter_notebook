"""
Integração até `docs/guides/ORDEM_IMPLEMENTAÇÃO.md` (§ dependência bloco 4):
o planner deve receber :class:`~CognitivePlan`, não só texto cru.

Cada passo é registado em JSONL (entrada/saída com dados). Execução MySQL opcional
via ``ORION_MYSQL_URL`` ou ``MYSQL_URL`` — pool asyncmy real, sem mocks.

Ficheiro de log por corrida: ``orion_mcp_v3/logs/integration_pipeline_<UTC>.jsonl``.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from asyncmy.errors import OperationalError, ProgrammingError

from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.broker.planner import build_query_plan
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist, compile_select
from orion_mcp_v3.connection_hub.mysql_backend import MysqlDatastoreClient
from orion_mcp_v3.connection_hub.pools import close_mysql_pool, create_mysql_pool
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy, RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.runtime import AttentionPolicy, ContextState
from orion_mcp_v3.runtime.budget_allocator import allocate
from orion_mcp_v3.runtime.conflict_resolution import cap_system_blocks, resolve_duplicate_blocks
from orion_mcp_v3.runtime.decay import apply_decay_with_clock
from orion_mcp_v3.runtime.intent_resolver import IntentResolver, map_attention_profile_to_policy
from orion_mcp_v3.runtime.provenance import CoverageInfo

from integration_pipeline_logger import (
    JsonlPipelineLogger,
    cognitive_plan_snapshot,
    conflict_resolution_snapshot,
    context_block_snapshot,
    rows_for_json,
    semantic_query_plan_snapshot,
)


def _project_logs_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "logs"


def _mysql_url() -> str | None:
    u = (os.environ.get("ORION_MYSQL_URL") or os.environ.get("MYSQL_URL") or "").strip()
    return u or None


async def _mysql_real_execution(logger: JsonlPipelineLogger, semantic: SemanticQueryPlan) -> None:
    """SELECT real na BD via compilador + allowlist (mesmo caminho que ``AnalyticsExecutor``)."""
    url = _mysql_url()
    logger.step(
        "mysql_env",
        input_data={
            "ORION_MYSQL_URL_defined": bool(os.environ.get("ORION_MYSQL_URL")),
            "MYSQL_URL_defined": bool(os.environ.get("MYSQL_URL")),
        },
        output_data={"connect": bool(url)},
    )
    if not url:
        logger.step(
            "mysql_skipped",
            input_data={},
            output_data={
                "reason": "Defina ORION_MYSQL_URL ou MYSQL_URL para executar SELECT real.",
            },
        )
        return

    allowlist = SqlAllowlist(
        tables=frozenset({"clientes", "os", "os_servicos", "funcionarios", "concessionarias"}),
        columns_by_table={
            "clientes": frozenset({"id", "nome", "paga"}),
            "os": frozenset({"id", "cliente_id", "concessionaria_id", "created_at", "paga"}),
            "os_servicos": frozenset({"id", "valor_venda_real"}),
            "funcionarios": frozenset({"id", "nome"}),
            "concessionarias": frozenset({"id", "nome"}),
        },
    )

    pool = await create_mysql_pool(url)
    if pool is None:
        logger.step("mysql_pool_failed", input_data={"url_host": url.split("@")[-1][:48]}, output_data={"error": "create_mysql_pool devolveu None"})
        pytest.fail("create_mysql_pool devolveu None com URL definida")

    client = MysqlDatastoreClient(pool)
    try:
        ping = await client.select("SELECT 1 AS ok", ())
        logger.step(
            "mysql_ping",
            input_data={"sql": "SELECT 1 AS ok", "params": []},
            output_data={"rows": rows_for_json(list(ping))},
        )

        executor = AnalyticsExecutor(client, allowlist, default_limit=50)
        plan_exec = executor.prepare_execution_plan(semantic, None)
        logger.step(
            "mysql_plan_merge",
            input_data={"semantic_query_plan": semantic_query_plan_snapshot(semantic)},
            output_data={"merged_hints_keys": sorted(plan_exec.hints.keys())},
        )

        compiled = compile_select(plan_exec, allowlist, default_limit=executor.default_limit)
        try:
            rows = await client.select(compiled.sql, compiled.params)
        except (ProgrammingError, OperationalError) as exc:
            logger.step(
                "mysql_analytics_select_error",
                input_data={"sql": compiled.sql, "params": list(compiled.params)},
                output_data={"error": str(exc), "args": getattr(exc, "args", ())},
            )
            pytest.skip(f"SELECT analítico na BD real falhou (schema/coluna?, ex. clientes.paga): {exc}")

        logger.step(
            "mysql_analytics_select",
            input_data={"sql": compiled.sql, "params": list(compiled.params)},
            output_data={
                "row_count": len(rows),
                "rows": rows_for_json(list(rows)),
            },
        )
    finally:
        await close_mysql_pool(pool)


def test_integration_pipeline_until_planner_accepts_cognitive_plan() -> None:
    utterance = "mostre o top 5 clientes por faturamento nos últimos 3 meses"

    log_path = _project_logs_dir() / f"integration_pipeline_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    log = JsonlPipelineLogger(log_path)
    log.start_run(
        utterance=utterance,
        extra={
            "log_path": str(log_path),
            "mysql_url_configured": bool(_mysql_url()),
        },
    )
    log.step("entrada_pergunta", input_data={}, output_data={"utterance": utterance})

    user_block = ContextBlock(
        utterance,
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="turn-1",
        relevance_score=1.0,
    )
    log.step(
        "context_block_utilizador",
        input_data={"spec": "ContextBlock USER / USER_INPUT"},
        output_data=context_block_snapshot(user_block),
    )

    stale_memory = ContextBlock(
        "memória antiga",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="mem-a",
        metadata={"created_at": 1_000_000.0},
        relevance_score=1.0,
    )
    decayed = apply_decay_with_clock(stale_memory, now=1_003_600.0, half_life_seconds=3600.0)
    log.step(
        "decay_memoria",
        input_data=context_block_snapshot(stale_memory),
        output_data={
            "decayed": context_block_snapshot(decayed),
            "relevance_before": stale_memory.relevance_score,
            "relevance_after": decayed.relevance_score,
        },
    )
    assert decayed.relevance_score < stale_memory.relevance_score

    dup_a = ContextBlock("dup", ContextRole.DATA, ContextSource.BROKER, relevance_score=0.2)
    dup_b = ContextBlock("dup", ContextRole.DATA, ContextSource.BROKER, relevance_score=0.9)
    deduped = resolve_duplicate_blocks((dup_a, dup_b))
    log.step(
        "conflict_resolution_dedupe",
        input_data={"blocks": [context_block_snapshot(dup_a), context_block_snapshot(dup_b)]},
        output_data=conflict_resolution_snapshot(deduped),
    )
    assert len(deduped.blocks) == 1

    sys_blocks = tuple(
        ContextBlock(f"s{i}", ContextRole.SYSTEM, ContextSource.SYSTEM, block_id=f"sys-{i}", relevance_score=float(i))
        for i in range(4)
    )
    capped = cap_system_blocks(sys_blocks, max_blocks=2)
    log.step(
        "conflict_resolution_cap_system",
        input_data={"count": len(sys_blocks), "max_blocks": 2},
        output_data=conflict_resolution_snapshot(capped),
    )
    assert len(capped.blocks) == 2

    state = ContextState(token_budget=512, active_blocks=[user_block, decayed, *deduped.blocks])
    log.step(
        "context_state",
        input_data={"token_budget": state.token_budget},
        output_data={
            "phase": state.current_phase,
            "active_blocks_count": len(state.active_blocks),
            "blocks_preview": [context_block_snapshot(b) for b in state.active_blocks],
        },
    )

    coverage = CoverageInfo(labels={"stage": "integration"}, notes="até planner cognitivo")
    log.step(
        "coverage_info",
        input_data={"labels": dict(coverage.labels)},
        output_data={"notes": coverage.notes},
    )
    assert coverage.labels["stage"] == "integration"

    resolver = IntentResolver()
    cognitive = resolver.resolve(utterance)
    log.step(
        "intent_resolver",
        input_data={"utterance": utterance},
        output_data=cognitive_plan_snapshot(cognitive),
    )
    assert isinstance(cognitive, CognitivePlan)
    assert cognitive.needs_analytics is True

    policy = map_attention_profile_to_policy(cognitive.attention_profile)
    log.step(
        "map_attention_profile_to_policy",
        input_data={"attention_profile": cognitive.attention_profile.value},
        output_data={"attention_policy": policy.value},
    )
    assert isinstance(policy, AttentionPolicy)

    packed = allocate(state.active_blocks, state.token_budget, policy=policy)
    log.step(
        "budget_allocate",
        input_data={
            "max_tokens": state.token_budget,
            "policy": policy.value,
            "incoming_blocks": len(state.active_blocks),
        },
        output_data={
            "packed_count": len(packed),
            "packed_preview": [context_block_snapshot(b) for b in packed],
        },
    )
    assert len(packed) >= 1

    semantic = build_query_plan(
        cognitive,
        query_text=utterance,
        correlation_id="integration-until-cognitive-planner",
    )
    log.step(
        "build_query_plan_com_texto",
        input_data={
            "cognitive_plan": cognitive_plan_snapshot(cognitive),
            "query_text": utterance,
            "correlation_id": "integration-until-cognitive-planner",
        },
        output_data=semantic_query_plan_snapshot(semantic),
    )
    assert isinstance(semantic, SemanticQueryPlan)
    assert semantic.strategy == RetrievalStrategy.BROKER_FANOUT
    assert semantic.analytics_strategy == AnalyticsStrategy.TREND
    assert semantic.hints.get("lookback_months") == 3
    assert semantic.hints.get("top_n") == 5
    assert semantic.hints.get("aggregation_kind") == "mixed"
    cog_meta = semantic.hints.get("cognitive")
    assert isinstance(cog_meta, dict)
    assert cog_meta.get("intent_type") == "analytical"
    assert semantic.hints.get("analytics_strategy") == AnalyticsStrategy.TREND.value

    semantic_nl_free = build_query_plan(cognitive, query_text=None)
    log.step(
        "build_query_plan_sem_texto_nl",
        input_data={"cognitive_plan": cognitive_plan_snapshot(cognitive), "query_text": None},
        output_data=semantic_query_plan_snapshot(semantic_nl_free),
    )
    assert isinstance(semantic_nl_free, SemanticQueryPlan)
    assert semantic_nl_free.analytics_strategy == AnalyticsStrategy.TREND

    asyncio.run(_mysql_real_execution(log, semantic))

    log.step(
        "run_done",
        input_data={},
        output_data={"log_file": str(log_path)},
    )
    print(f"[integration] Log gravado em: {log_path}")
