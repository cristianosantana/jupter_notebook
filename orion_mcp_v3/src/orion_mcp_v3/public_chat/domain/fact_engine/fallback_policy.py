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
    """Catálogo filtra elegibilidade; vector search define a ordem de preferência."""

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

        picked, rule = _pick_hit_for_themes(
            vector_hits=vector_hits,
            catalog_hits=catalog_hits,
            themes=themes,
            catalog=catalog,
        )
        if picked is not None and rule is not None:
            return ResolveResult(hit=ResolvedMemoryHit(hit=picked, rule=rule))

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


def _hit_matches_themes(
    hit: KnowledgeHit,
    themes: tuple[str, ...],
    catalog: MemoryCatalog,
) -> bool:
    if not themes:
        return True
    return any(catalog.context_key_matches_theme(hit.context_key, theme) for theme in themes)


def _filter_hits_for_themes(
    hits: list[KnowledgeHit],
    themes: tuple[str, ...],
    catalog: MemoryCatalog,
) -> list[KnowledgeHit]:
    if not themes:
        return list(hits)
    return [hit for hit in hits if _hit_matches_themes(hit, themes, catalog)]


def _pick_hit_for_themes(
    *,
    vector_hits: list[KnowledgeHit],
    catalog_hits: list[KnowledgeHit],
    themes: tuple[str, ...],
    catalog: MemoryCatalog,
) -> tuple[KnowledgeHit | None, ResolutionRule | None]:
    """
    Escolhe o hit mais adequado intersectando elegibilidade (catálogo) com
    relevância semântica (ordem do vector search).

    1. Percorre vector_hits na ordem do retriever; retorna o primeiro cujo
       origin_id está no conjunto elegível do catálogo.
    2. Sem catálogo: primeiro vector hit que casa com o tema.
    3. Fallback: primeiro hit elegível do catálogo (ordem SQL).
    """
    eligible_catalog = _filter_hits_for_themes(catalog_hits, themes, catalog)
    eligible_ids = {hit.origin_id for hit in eligible_catalog}

    if eligible_ids:
        for hit in vector_hits:
            if hit.origin_id in eligible_ids:
                return hit, ResolutionRule.VECTOR_RETRIEVAL

    if not eligible_catalog:
        for hit in vector_hits:
            if _hit_matches_themes(hit, themes, catalog):
                return hit, ResolutionRule.VECTOR_RETRIEVAL

    if eligible_catalog:
        return eligible_catalog[0], ResolutionRule.CATALOG

    return None, None


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
