"""Política única de fallback para resolução de facts."""

from __future__ import annotations

from dataclasses import dataclass

from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap, GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.trace import FactTrace, ResolutionRule
from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit
from orion_mcp_v3.public_chat.domain.memory_catalog import MemoryCatalog


@dataclass(frozen=True, slots=True)
class ResolvedMemoryHit:
    hit: KnowledgeHit
    rule: ResolutionRule


@dataclass(frozen=True, slots=True)
class ResolveResult:
    hit: ResolvedMemoryHit | None
    gap: FactGap | None = None


class FallbackPolicy:
    """Ordem fixa: catálogo/SQL → vector merge → gap explícito."""

    def resolve_from_hits(
        self,
        requirement: FactRequirement,
        *,
        catalog_hits: list[KnowledgeHit],
        vector_hits: list[KnowledgeHit],
        catalog: MemoryCatalog,
    ) -> ResolveResult:
        fact_key = requirement.fact_key
        themes = catalog.themes_for_fact(fact_key)
        if not themes and requirement.semantics.memory_themes:
            themes = requirement.semantics.memory_themes

        catalog_match = _pick_hit_for_themes(catalog_hits, themes, catalog)
        if catalog_match is not None:
            return ResolveResult(
                hit=ResolvedMemoryHit(hit=catalog_match, rule=ResolutionRule.CATALOG),
            )

        vector_match = _pick_hit_for_themes(vector_hits, themes, catalog)
        if vector_match is not None:
            return ResolveResult(
                hit=ResolvedMemoryHit(hit=vector_match, rule=ResolutionRule.VECTOR_RETRIEVAL),
            )

        attempted = tuple(hit.origin_id for hit in catalog_hits + vector_hits)
        if attempted:
            return ResolveResult(
                hit=None,
                gap=FactGap(
                    fact_key=fact_key,
                    reason=GapReason.MEMORY_EXISTS_BUT_NO_MATCH,
                    detail=f"themes={themes}",
                    origin_ids_attempted=attempted,
                ),
            )
        return ResolveResult(
            hit=None,
            gap=FactGap(
                fact_key=fact_key,
                reason=GapReason.NO_MEMORY_FOUND,
                detail=f"period={requirement.period}",
            ),
        )


def _pick_hit_for_themes(
    hits: list[KnowledgeHit],
    themes: tuple[str, ...],
    catalog: MemoryCatalog,
) -> KnowledgeHit | None:
    if not hits or not themes:
        return hits[0] if hits and not themes else None
    for hit in hits:
        for theme in themes:
            if catalog.category_matches_theme(hit.category, theme):
                return hit
    return None


def build_trace_for_resolution(
    requirement: FactRequirement,
    resolved: ResolvedMemoryHit,
    *,
    semantics_version: str = "v1",
) -> FactTrace:
    hit = resolved.hit
    return FactTrace(
        fact_key=requirement.fact_key,
        resolved_from=(hit.origin_id,),
        context_keys=(hit.context_key,),
        rule_applied=resolved.rule,
        extraction_path=_default_extraction_path(requirement),
        semantics_version=semantics_version,
    )


def _default_extraction_path(requirement: FactRequirement):
    from orion_mcp_v3.public_chat.domain.fact_engine.semantics import SourcePriority
    from orion_mcp_v3.public_chat.domain.fact_engine.trace import ExtractionPath

    priority = requirement.semantics.source_priority
    if SourcePriority.KEY_METRICS in priority:
        return ExtractionPath.KEY_METRICS
    if SourcePriority.STRUCTURED in priority:
        return ExtractionPath.STRUCTURED_PARSER
    return ExtractionPath.STRUCTURED_PARSER
