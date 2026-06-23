"""Resolução de facts para memórias via join plan + fallback."""

from __future__ import annotations

import time
from dataclasses import dataclass

from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import (
    FallbackPolicy,
    ResolvedMemoryHit,
    build_trace_for_resolution,
)
from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap
from orion_mcp_v3.public_chat.domain.fact_engine.join_plan import MemoryJoinPlan
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.trace import FactTrace
from orion_mcp_v3.public_chat.domain.join_plan_builder import build_join_plan
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.domain.memory_catalog import MemoryCatalog, get_memory_catalog
from orion_mcp_v3.public_chat.domain.period_utils import period_in_context_key
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event
from orion_mcp_v3.public_chat.infrastructure.remissive_reader import PublicRemissiveReader


@dataclass(frozen=True, slots=True)
class MemoryResolveResult:
    join_plan: MemoryJoinPlan | None
    resolved: dict[str, ResolvedMemoryHit]
    gaps: tuple[FactGap, ...]
    traces: tuple[FactTrace, ...]
    catalog_hits: tuple[KnowledgeHit, ...]


class MemoryResolver:
    def __init__(
        self,
        reader: PublicRemissiveReader,
        *,
        catalog: MemoryCatalog | None = None,
        fallback: FallbackPolicy | None = None,
    ) -> None:
        self._reader = reader
        self._catalog = catalog or get_memory_catalog()
        self._fallback = fallback or FallbackPolicy()

    async def resolve(
        self,
        requirements: tuple[FactRequirement, ...],
        knowledge: ConhecimentoRecuperado,
    ) -> MemoryResolveResult:
        t0 = time.monotonic()
        join_plan = build_join_plan(requirements, catalog=self._catalog)
        if join_plan is not None:
            log_public_chat_event(
                etapa="fact.join_plan",
                fase="post",
                dados=join_plan.as_mapping(),
            )

        catalog_hits = await self._load_catalog_hits(join_plan)
        vector_hits = list(knowledge.hits)

        resolved: dict[str, ResolvedMemoryHit] = {}
        gaps: list[FactGap] = []
        traces: list[FactTrace] = []

        for requirement in requirements:
            if requirement.semantics.aggregation_rule.value == "derived":
                continue
            period_filtered = _filter_by_period(catalog_hits, join_plan.period if join_plan else None)
            result = self._fallback.resolve_from_hits(
                requirement,
                catalog_hits=period_filtered,
                vector_hits=vector_hits,
                catalog=self._catalog,
            )
            if result.hit is not None:
                resolved[requirement.fact_key] = result.hit
                traces.append(
                    build_trace_for_resolution(
                        requirement,
                        result.hit,
                        semantics_version=self._catalog.version,
                    )
                )
            if result.gap is not None:
                gaps.append(result.gap)

        resolve_result = MemoryResolveResult(
            join_plan=join_plan,
            resolved=resolved,
            gaps=tuple(gaps),
            traces=tuple(traces),
            catalog_hits=tuple(catalog_hits),
        )
        log_public_chat_event(
            etapa="fact.resolve",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "resolved_count": len(resolve_result.resolved),
                "gap_count": len(resolve_result.gaps),
                "traces": [trace.as_mapping() for trace in resolve_result.traces],
                "gaps": [gap.as_mapping() for gap in resolve_result.gaps],
            },
        )
        return resolve_result

    async def _load_catalog_hits(self, join_plan: MemoryJoinPlan | None) -> list[KnowledgeHit]:
        if join_plan is None:
            return []
        patterns: list[str] = []
        for source in join_plan.required_sources:
            entry = self._catalog.theme_entry(source.theme_slug)
            if entry is not None:
                patterns.extend(entry.category_patterns)
        if not patterns:
            return []
        hits = await self._reader.load_hits_by_theme_patterns(patterns)
        return _filter_by_period(hits, join_plan.period)


def _filter_by_period(hits: list[KnowledgeHit], period: str | None) -> list[KnowledgeHit]:
    if not period:
        return hits
    return [hit for hit in hits if period_in_context_key(hit.context_key, period)]
