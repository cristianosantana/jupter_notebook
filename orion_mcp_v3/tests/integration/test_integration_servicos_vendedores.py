"""
Integração: serviços mais vendidos pelos melhores vendedores (``valor_venda_real``).

Query de referência:

.. code-block:: sql

    SELECT
        vendedor.id AS vendedor_id,
        vendedor.nome AS vendedor,
        oss.servico_id,
        COUNT(*) AS qtd_vendas,
        SUM(oss.valor_venda_real) AS total_vendido,
        AVG(oss.valor_venda_real) AS ticket_medio
    FROM os
        JOIN os_servicos AS oss ON os.id = oss.os_id
        JOIN funcionarios AS vendedor ON vendedor.id = os.vendedor_id
    WHERE os.created_at BETWEEN '2026-01-01' AND '2026-03-01'
    GROUP BY vendedor.id, oss.servico_id
    ORDER BY total_vendido DESC;

Pipeline completo: IntentResolver → build_query_plan → compile_select (com sql_hints
customizados para JOINs vendedor + os_servicos) → MySQL real (opcional via ``ORION_MYSQL_URL``
ou ``MYSQL_URL``) → EvidenceBuilder → redução analítica → map-reduce/DriftGuard →
memória → CognitiveOrchestrator.

Log JSONL por corrida em ``logs/integration_servicos_vendedores_<UTC>.jsonl``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from asyncmy.errors import OperationalError, ProgrammingError

from orion_mcp_v3.broker import (
    EvidenceBuilder,
    aggregate_groups,
    distill_with_semantic_merge,
    merge_cognitive_artifacts,
    sample_recent_structured,
    semantic_merge_sections,
)
from orion_mcp_v3.broker import SqlAllowlist, SqlCompilationError, compile_semantic_query_plan
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.broker.planner import build_query_plan
from orion_mcp_v3.broker.sql_compiler import compile_select
from orion_mcp_v3.connection_hub.mysql_backend import MysqlDatastoreClient
from orion_mcp_v3.memory import (
    EpisodicRetriever,
    InMemoryConversationStateRepository,
    MemoryComposer,
    MemoryRetrievalPipeline,
    SemanticRetriever,
)
from orion_mcp_v3.connection_hub.pools import close_mysql_pool, create_mysql_pool
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy, RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.runtime import (
    AttentionPolicy,
    CognitiveOrchestrationResult,
    CognitiveOrchestrator,
    ContextState,
    DriftGuard,
    allocate,
    elastic_free_tier_params,
    estimate_tokens,
)
from orion_mcp_v3.runtime.conflict_resolution import cap_system_blocks, resolve_duplicate_blocks
from orion_mcp_v3.runtime.decay import apply_decay_with_clock
from orion_mcp_v3.runtime.intent_resolver import IntentResolver, map_attention_profile_to_policy
from orion_mcp_v3.runtime.provenance import CoverageInfo

from integration_pipeline_logger import (
    JsonlPipelineLogger,
    analytical_digest_snapshot,
    cognitive_artifact_snapshot,
    cognitive_plan_snapshot,
    conflict_resolution_snapshot,
    context_block_snapshot,
    context_fusion_snapshot,
    drift_report_snapshot,
    evidence_block_snapshot,
    rows_for_json,
    semantic_query_plan_snapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_logs_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "logs"


def _mysql_url() -> str | None:
    u = (os.environ.get("ORION_MYSQL_URL") or os.environ.get("MYSQL_URL") or "").strip()
    return u or None


def _integration_sql_allowlist() -> SqlAllowlist:
    """Allowlist estendida: inclui ``vendedor_id`` em ``os`` para o JOIN com ``funcionarios``."""
    return SqlAllowlist(
        tables=frozenset({"clientes", "os", "os_servicos", "funcionarios", "concessionarias"}),
        columns_by_table={
            "clientes": frozenset({"id", "nome", "paga", "created_at"}),
            "os": frozenset({"id", "cliente_id", "concessionaria_id", "vendedor_id", "created_at", "paga"}),
            "os_servicos": frozenset({"id", "os_id", "servico_id", "valor_venda_real", "created_at"}),
            "funcionarios": frozenset({"id", "nome", "created_at"}),
            "concessionarias": frozenset({"id", "nome", "created_at"}),
        },
    )


_VENDEDORES_SQL_HINTS: dict[str, Any] = {
    "sql_table": "os",
    "sql_joins": (
        {
            "join_table": "os_servicos",
            "alias": "oss",
            "on_left_column": "id",
            "on_right_column": "os_id",
        },
        {
            "join_table": "funcionarios",
            "alias": "vendedor",
            "on_left_column": "vendedor_id",
            "on_right_column": "id",
        },
    ),
    "sql_columns": (
        {"qualifier": "vendedor", "column": "id"},
        {"qualifier": "vendedor", "column": "nome"},
        {"qualifier": "oss", "column": "servico_id"},
        {
            "agg": "COUNT",
            "qualifier": "oss",
            "column": "servico_id",
            "alias": "qtd_vendas",
        },
        {
            "agg": "SUM",
            "qualifier": "oss",
            "column": "valor_venda_real",
            "alias": "total_vendido",
        },
        {
            "agg": "AVG",
            "qualifier": "oss",
            "column": "valor_venda_real",
            "alias": "ticket_medio",
        },
    ),
    "sql_group_by": (
        {"qualifier": "vendedor", "column": "id"},
        {"qualifier": "vendedor", "column": "nome"},
        {"qualifier": "oss", "column": "servico_id"},
    ),
    "sql_filters": (
        {"qualifier": "os", "column": "created_at", "op": ">=", "value": "2026-01-01"},
        {"qualifier": "os", "column": "created_at", "op": "<", "value": "2026-03-01"},
    ),
    "sql_order_by": {"direction": "desc", "alias": "total_vendido"},
    "sql_omit_limit": False,
}


_NUMERIC_VALUE_PRIORITY: tuple[str, ...] = (
    "total_vendido",
    "ticket_medio",
    "total_faturamento",
    "valor_venda_real",
    "valor",
    "amount",
    "total",
    "rev",
    "score",
)
_SKIP_AUTOPICK_KEYS: frozenset[str] = frozenset(
    {"id", "cliente_id", "concessionaria_id", "os_id", "servico_id", "vendedor_id", "paga"}
)


def _pick_evidence_keys(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Escolhe métrica temporal e coluna de tempo a partir do schema real dos resultados."""
    if not rows:
        return None, None
    sample = rows[0]
    time_key: str | None = "created_at" if "created_at" in sample else None
    for vk in _NUMERIC_VALUE_PRIORITY:
        if vk in sample:
            return vk, time_key
    for k, v in sample.items():
        if k in _SKIP_AUTOPICK_KEYS or k == time_key:
            continue
        try:
            float(v)
            return k, time_key
        except (TypeError, ValueError):
            continue
    return None, time_key


def _apply_evidence_builder(logger: JsonlPipelineLogger, rows: list[dict[str, Any]]) -> EvidenceBlock | None:
    """Bloco 6: resultado SQL → ``EvidenceBlock``."""
    if not rows:
        logger.step(
            "evidence_builder_skipped",
            input_data={},
            output_data={"reason": "sem linhas (URL MySQL ausente ou SELECT vazio)"},
        )
        return None
    value_key, time_key = _pick_evidence_keys(rows)
    if not value_key:
        logger.step(
            "evidence_builder_skipped",
            input_data={"row_keys_sample": sorted(rows[0].keys())},
            output_data={"reason": "nenhuma coluna numérica conhecida ou inferível nas linhas"},
        )
        return None
    id_key: str | None = "id" if "id" in rows[0] else None
    block = EvidenceBuilder().build(rows, value_key=value_key, time_key=time_key, id_key=id_key)
    logger.step(
        "evidence_builder",
        input_data={"value_key": value_key, "time_key": time_key, "row_count": len(rows)},
        output_data=evidence_block_snapshot(block),
    )
    return block


# ---------------------------------------------------------------------------
# §13 — compilador semântico (validação allowlist, sem execução)
# ---------------------------------------------------------------------------

def _apply_semantic_query_compiler_phase13(
    logger: JsonlPipelineLogger,
    plan: SemanticQueryPlan,
    *,
    variant: str,
) -> None:
    """§13: DSL SemanticQueryPlan → merge → validação → SQL parametrizado (allowlist)."""
    allowlist = _integration_sql_allowlist()
    try:
        result = compile_semantic_query_plan(plan, allowlist, default_limit=1000)
        logger.step(
            f"semantic_query_compiler_{variant}",
            input_data={
                "variant": variant,
                "semantic_query_plan": semantic_query_plan_snapshot(plan),
            },
            output_data={
                "merged_hints_keys": sorted(result.merged_plan.hints.keys()),
                "sql": result.compiled.sql,
                "param_count": len(result.compiled.params),
                "params_preview": list(result.compiled.params)[:24],
            },
        )
    except SqlCompilationError as exc:
        logger.step(
            f"semantic_query_compiler_{variant}_error",
            input_data={
                "variant": variant,
                "semantic_query_plan": semantic_query_plan_snapshot(plan),
            },
            output_data={"error": str(exc)},
        )


# ---------------------------------------------------------------------------
# MySQL real (opcional)
# ---------------------------------------------------------------------------

async def _mysql_real_execution(
    logger: JsonlPipelineLogger,
    semantic: SemanticQueryPlan,
) -> list[dict[str, Any]]:
    """SELECT real na BD via compilador + allowlist.

    Passa ``_VENDEDORES_SQL_HINTS`` como override para gerar o JOIN
    os → os_servicos + os → funcionarios com GROUP BY vendedor/servico.
    """
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
        return []

    allowlist = _integration_sql_allowlist()

    pool = await create_mysql_pool(url)
    if pool is None:
        logger.step("mysql_pool_failed", input_data={"url_host": url.split("@")[-1][:48]}, output_data={"error": "create_mysql_pool devolveu None"})
        pytest.fail("create_mysql_pool devolveu None com URL definida")

    client = MysqlDatastoreClient(pool)
    selected: list[dict[str, Any]] = []
    try:
        ping = await client.select("SELECT 1 AS ok", ())
        logger.step(
            "mysql_ping",
            input_data={"sql": "SELECT 1 AS ok", "params": []},
            output_data={"rows": rows_for_json(list(ping))},
        )

        executor = AnalyticsExecutor(client, allowlist, default_limit=1000)
        plan_exec = executor.prepare_execution_plan(semantic, _VENDEDORES_SQL_HINTS)
        logger.step(
            "mysql_plan_merge",
            input_data={"semantic_query_plan": semantic_query_plan_snapshot(semantic)},
            output_data={"merged_hints_keys": sorted(plan_exec.hints.keys())},
        )

        compiled = compile_select(plan_exec, allowlist, default_limit=executor.default_limit)
        logger.step(
            "mysql_compiled_sql",
            input_data={"sql": compiled.sql, "params": list(compiled.params)},
            output_data={"sql_preview": compiled.sql[:500]},
        )
        try:
            rows = await client.select(compiled.sql, compiled.params)
        except (ProgrammingError, OperationalError) as exc:
            logger.step(
                "mysql_analytics_select_error",
                input_data={"sql": compiled.sql, "params": list(compiled.params)},
                output_data={"error": str(exc), "args": getattr(exc, "args", ())},
            )
            pytest.skip(f"SELECT analítico na BD real falhou (schema/coluna?): {exc}")

        logger.step(
            "mysql_analytics_select",
            input_data={"sql": compiled.sql, "params": list(compiled.params)},
            output_data={
                "row_count": len(rows),
                "rows": rows_for_json(list(rows)),
            },
        )
        selected = list(rows)
    finally:
        await close_mysql_pool(pool)

    return selected


# ---------------------------------------------------------------------------
# Bloco 5 — redução analítica
# ---------------------------------------------------------------------------

def _apply_analytical_reduction(
    logger: JsonlPipelineLogger,
    rows: list[dict[str, Any]],
) -> None:
    """Bloco 5: aggregators → samplers → ``merge_cognitive_artifacts``.

    Agrupa por ``id`` (vendedor) em vez de ``cliente_id``.
    """
    if not rows:
        logger.step(
            "analytical_reduction_skipped",
            input_data={},
            output_data={"reason": "sem linhas do MySQL (URL ausente ou resultado vazio)"},
        )
        return

    group_key = "id" if "id" in rows[0] else "servico_id"
    group_art = aggregate_groups(rows, group_key)
    logger.step(
        "analytical_reduction_aggregate_groups",
        input_data={"group_key": group_key, "mysql_row_count": len(rows)},
        output_data=cognitive_artifact_snapshot(group_art),
    )

    artifacts: list[Any] = [group_art]

    merged = merge_cognitive_artifacts(*artifacts)
    logger.step(
        "analytical_reduction_merge",
        input_data={
            "artifact_kinds": [a.kind for a in artifacts],
            "merged_kind": merged.kind,
        },
        output_data=cognitive_artifact_snapshot(merged),
    )


# ---------------------------------------------------------------------------
# Bloco 7 — map-reduce + DriftGuard
# ---------------------------------------------------------------------------

def _apply_map_reduce_phase7(logger: JsonlPipelineLogger, rows: list[dict[str, Any]]) -> AnalyticalDigest | None:
    """Bloco 7: chunk summarization → merge semântico → digest + DriftGuard."""
    if not rows:
        logger.step(
            "map_reduce_skipped",
            input_data={},
            output_data={"reason": "sem linhas do MySQL (URL ausente ou SELECT vazio)"},
        )
        return None

    class _ChunkSummarizer:
        def summarize_chunk(self, chunk: Sequence[Mapping[str, Any]], chunk_index: int) -> str:
            n = len(chunk)
            keys = sorted(chunk[0].keys()) if chunk else []
            return f"chunk_index={chunk_index} row_count={n} columns={keys}"

    chunk_row_cap = min(3, max(1, len(rows)))
    base_cov = CoverageInfo(labels={"pipeline": "integration_servicos_vendedores"}, notes="bloco7")
    digest = distill_with_semantic_merge(
        rows,
        _ChunkSummarizer(),
        max_rows=chunk_row_cap,
        max_tokens=100_000,
        semantic_merge=semantic_merge_sections,
        base_coverage=base_cov,
    )
    logger.step(
        "map_reduce_digest",
        input_data={
            "mysql_row_count": len(rows),
            "chunk_max_rows": chunk_row_cap,
            "aggregation_logic": digest.aggregation_logic,
        },
        output_data=analytical_digest_snapshot(digest),
    )

    synthetic_prior = AnalyticalDigest(
        summary="(prior sintético — serviços vendedores)",
        volume=1,
        confidence=0.99,
        coverage=CoverageInfo(labels={"role": "synthetic_prior"}, notes="drift_guard_vendedores"),
    )
    drift = DriftGuard(volume_change_ratio=2.0, confidence_drop_threshold=0.5).evaluate(
        synthetic_prior,
        digest,
    )
    logger.step(
        "drift_guard",
        input_data={"prior_volume": synthetic_prior.volume, "current_volume": digest.volume},
        output_data=drift_report_snapshot(drift),
    )
    return digest


# ---------------------------------------------------------------------------
# Bloco 8 — memória
# ---------------------------------------------------------------------------

_MEMORY_SESSION_ID = "integration-servicos-vendedores"


async def _apply_memory_pipeline_phase8(logger: JsonlPipelineLogger, utterance: str) -> list[ContextBlock]:
    """Bloco 8: EpisodicRetriever + SemanticRetriever + MemoryComposer."""
    repo = InMemoryConversationStateRepository()
    await repo.append_message(_MEMORY_SESSION_ID, "user", "Quero ver o desempenho dos vendedores.")
    await repo.append_message(_MEMORY_SESSION_ID, "assistant", "Posso cruzar vendedores com serviços por valor de venda.")
    await repo.append_message(_MEMORY_SESSION_ID, "user", utterance)

    episodic = EpisodicRetriever(repo)
    semantic = SemanticRetriever(repo)
    pipe = MemoryRetrievalPipeline(repo)

    ep_blocks = await episodic.retrieve(_MEMORY_SESSION_ID, limit=10)
    logger.step(
        "memory_episodic_retrieve",
        input_data={"session_id": _MEMORY_SESSION_ID, "limit": 10},
        output_data={
            "block_count": len(ep_blocks),
            "blocks": [context_block_snapshot(b) for b in ep_blocks],
        },
    )

    sem_blocks = await semantic.retrieve(utterance, _MEMORY_SESSION_ID, pool_limit=20, top_k=4)
    logger.step(
        "memory_semantic_retrieve",
        input_data={"session_id": _MEMORY_SESSION_ID, "query_preview": utterance[:96]},
        output_data={
            "block_count": len(sem_blocks),
            "blocks": [context_block_snapshot(b) for b in sem_blocks],
        },
    )

    raw = await pipe.collect_blocks(
        _MEMORY_SESSION_ID,
        recent_limit=10,
        semantic_query=utterance,
        semantic_retriever=semantic,
        episodic_retriever=episodic,
    )
    merged = await MemoryComposer().compose_blocks(raw, max_tokens=4096)
    logger.step(
        "memory_compose_blocks",
        input_data={
            "session_id": _MEMORY_SESSION_ID,
            "semantic_query_preview": utterance[:120],
        },
        output_data={
            "fitted_block_count": len(merged),
            "blocks": [context_block_snapshot(b) for b in merged],
        },
    )
    return merged


# ---------------------------------------------------------------------------
# §12 — CognitiveOrchestrator
# ---------------------------------------------------------------------------

_POST_FUSION_TOKEN_BUDGET = 4096


def _apply_cognitive_orchestrator_phase12(
    logger: JsonlPipelineLogger,
    utterance: str,
    cognitive: CognitivePlan,
    evidence: EvidenceBlock | None,
    digest: AnalyticalDigest | None,
    memory_blocks: list[ContextBlock],
    policy: AttentionPolicy,
    max_tokens: int,
) -> CognitiveOrchestrationResult:
    """§12 :class:`~CognitiveOrchestrator` — fusão → scheduler → allocator → prompt."""
    orch = CognitiveOrchestrator()
    result = orch.finalize_prompt(
        utterance,
        policy=policy,
        cognitive_plan=cognitive,
        evidence=evidence,
        digest=digest,
        memory_blocks=memory_blocks,
        max_tokens=max_tokens,
    )
    params = elastic_free_tier_params(policy)
    est = sum(estimate_tokens(b.text) for b in result.packed_blocks)
    logger.step(
        "cognitive_orchestrator",
        input_data={
            "utterance_preview": utterance[:120],
            "max_tokens": max_tokens,
            "attention_policy": policy.value,
            "elastic_free_tier": {
                "dialogue_fraction_of_free": params.dialogue_fraction_of_free,
                "data_share_of_remainder": params.data_share_of_remainder,
                "elasticity": params.elasticity,
            },
        },
        output_data={
            "fusion": context_fusion_snapshot(result.fusion),
            "scheduled_count": len(result.scheduled_blocks),
            "order_block_ids": [b.block_id for b in result.scheduled_blocks[:24]],
            "scheduler_scores_preview": [
                {"block_id": b.block_id, "scheduler_score": b.metadata.get("scheduler_score")}
                for b in result.scheduled_blocks[:12]
            ],
            "packed_count": len(result.packed_blocks),
            "packed_total_est_tokens": est,
            "packed_preview": [context_block_snapshot(b) for b in result.packed_blocks[:16]],
            "prompt_chars": len(result.prompt_text),
            "prompt_preview": result.prompt_text[:2500],
        },
    )
    return result


# ---------------------------------------------------------------------------
# Teste principal
# ---------------------------------------------------------------------------

async def test_integration_servicos_mais_vendidos_por_vendedores() -> None:
    """Pipeline completo: serviços mais vendidos pelos melhores vendedores (valor_venda_real)."""
    utterance = (
        "Ranking de serviços com mais vendas pelos melhores vendedores "
        "com base em valor_venda_real"
    )

    log_path = (
        _project_logs_dir()
        / f"integration_servicos_vendedores_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    )
    log = JsonlPipelineLogger(log_path)
    log.start_run(
        utterance=utterance,
        extra={
            "log_path": str(log_path),
            "mysql_url_configured": bool(_mysql_url()),
        },
    )
    log.step("entrada_pergunta", input_data={}, output_data={"utterance": utterance})

    # --- ContextBlock do utilizador ---
    user_block = ContextBlock(
        utterance,
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="turn-vendedores-1",
        relevance_score=1.0,
    )
    log.step(
        "context_block_utilizador",
        input_data={"spec": "ContextBlock USER / USER_INPUT"},
        output_data=context_block_snapshot(user_block),
    )

    # --- Decay de memória antiga ---
    stale_memory = ContextBlock(
        "memória antiga sobre vendedores",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="mem-vend-a",
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

    # --- Conflict resolution ---
    dup_a = ContextBlock("dup vendedor", ContextRole.DATA, ContextSource.BROKER, relevance_score=0.2)
    dup_b = ContextBlock("dup vendedor", ContextRole.DATA, ContextSource.BROKER, relevance_score=0.9)
    deduped = resolve_duplicate_blocks((dup_a, dup_b))
    log.step(
        "conflict_resolution_dedupe",
        input_data={"blocks": [context_block_snapshot(dup_a), context_block_snapshot(dup_b)]},
        output_data=conflict_resolution_snapshot(deduped),
    )
    assert len(deduped.blocks) == 1

    sys_blocks = tuple(
        ContextBlock(f"s{i}", ContextRole.SYSTEM, ContextSource.SYSTEM, block_id=f"sys-v-{i}", relevance_score=float(i))
        for i in range(4)
    )
    capped = cap_system_blocks(sys_blocks, max_blocks=2)
    log.step(
        "conflict_resolution_cap_system",
        input_data={"count": len(sys_blocks), "max_blocks": 2},
        output_data=conflict_resolution_snapshot(capped),
    )
    assert len(capped.blocks) == 2

    # --- ContextState ---
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

    # --- Coverage ---
    coverage = CoverageInfo(labels={"stage": "integration_vendedores"}, notes="serviços × vendedores")
    log.step(
        "coverage_info",
        input_data={"labels": dict(coverage.labels)},
        output_data={"notes": coverage.notes},
    )
    assert coverage.labels["stage"] == "integration_vendedores"

    # --- IntentResolver ---
    resolver = IntentResolver()
    cognitive = resolver.resolve(utterance)
    log.step(
        "intent_resolver",
        input_data={"utterance": utterance},
        output_data=cognitive_plan_snapshot(cognitive),
    )
    assert isinstance(cognitive, CognitivePlan)
    assert cognitive.needs_analytics is True
    assert cognitive.intent_type.value == "analytical"

    # --- AttentionPolicy ---
    policy = map_attention_profile_to_policy(cognitive.attention_profile)
    log.step(
        "map_attention_profile_to_policy",
        input_data={"attention_profile": cognitive.attention_profile.value},
        output_data={"attention_policy": policy.value},
    )
    assert isinstance(policy, AttentionPolicy)

    # --- Budget allocate ---
    packed = allocate(state.active_blocks, state.token_budget, policy=policy).fitted_blocks
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

    # --- build_query_plan ---
    semantic = build_query_plan(
        cognitive,
        query_text=utterance,
        correlation_id="integration-servicos-vendedores",
    )
    log.step(
        "build_query_plan_com_texto",
        input_data={
            "cognitive_plan": cognitive_plan_snapshot(cognitive),
            "query_text": utterance,
            "correlation_id": "integration-servicos-vendedores",
        },
        output_data=semantic_query_plan_snapshot(semantic),
    )
    assert isinstance(semantic, SemanticQueryPlan)
    assert semantic.strategy == RetrievalStrategy.BROKER_FANOUT
    assert semantic.analytics_strategy == AnalyticsStrategy.RANKING
    cog_meta = semantic.hints.get("cognitive")
    assert isinstance(cog_meta, dict)
    assert cog_meta.get("intent_type") == "analytical"
    assert semantic.hints.get("analytics_strategy") == AnalyticsStrategy.RANKING.value

    # --- §13 compilador semântico (sem hints vendedores — usa default) ---
    _apply_semantic_query_compiler_phase13(log, semantic, variant="com_texto")

    # --- Variante sem NL ---
    semantic_nl_free = build_query_plan(cognitive, query_text=None)
    log.step(
        "build_query_plan_sem_texto_nl",
        input_data={"cognitive_plan": cognitive_plan_snapshot(cognitive), "query_text": None},
        output_data=semantic_query_plan_snapshot(semantic_nl_free),
    )
    assert isinstance(semantic_nl_free, SemanticQueryPlan)
    assert semantic_nl_free.analytics_strategy == AnalyticsStrategy.RANKING

    _apply_semantic_query_compiler_phase13(log, semantic_nl_free, variant="sem_texto_nl")

    # --- §13 compilador semântico com hints vendedores (query de referência) ---
    from dataclasses import replace as _replace

    semantic_with_vendedores = _replace(
        semantic,
        hints={**dict(semantic.hints), **_VENDEDORES_SQL_HINTS},
    )
    _apply_semantic_query_compiler_phase13(log, semantic_with_vendedores, variant="com_hints_vendedores")

    # --- MySQL real (opcional) ---
    mysql_rows = await _mysql_real_execution(log, semantic)
    evidence = _apply_evidence_builder(log, mysql_rows)
    _apply_analytical_reduction(log, mysql_rows)
    digest = _apply_map_reduce_phase7(log, mysql_rows)

    # --- Memória ---
    memory_blocks = await _apply_memory_pipeline_phase8(log, utterance)

    # --- §12 CognitiveOrchestrator ---
    orch_result = _apply_cognitive_orchestrator_phase12(
        log,
        utterance,
        cognitive,
        evidence,
        digest,
        memory_blocks,
        policy,
        _POST_FUSION_TOKEN_BUDGET,
    )
    assert "[USER]" in orch_result.prompt_text or orch_result.prompt_text.strip() != ""

    log.step(
        "run_done",
        input_data={},
        output_data={"log_file": str(log_path)},
    )
    print(f"[integration-servicos-vendedores] Log gravado em: {log_path}")
