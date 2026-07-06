"""Política única de fallback para resolução de facts."""

from __future__ import annotations

from dataclasses import dataclass

from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap, GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionRule, ResolutionTrace, build_resolution_trace
from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit
from orion_mcp_v3.public_chat.domain.memory_catalog import MemoryCatalog
from orion_mcp_v3.public_chat.domain.period_utils import period_in_context_key


@dataclass(frozen=True, slots=True)
class ResolvedMemoryHit:
    hit: KnowledgeHit
    rule: ResolutionRule
    resolution_trace: ResolutionTrace


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

        picked, rule, attempted_rules = _pick_hit_for_themes(
            requirement=requirement,
            vector_hits=vector_hits,
            catalog_hits=catalog_hits,
            themes=themes,
            catalog=catalog,
        )
        if picked is not None and rule is not None:
            trace = build_resolution_trace(
                fact_key=fact_key,
                hit_origin_id=picked.origin_id,
                hit_context_key=picked.context_key,
                rule=rule,
                semantics_version=catalog.version,
            )
            return ResolveResult(
                hit=ResolvedMemoryHit(hit=picked, rule=rule, resolution_trace=trace),
            )

        attempted = tuple(hit.origin_id for hit in catalog_hits + vector_hits)
        rule_labels = tuple(rule.value for rule in attempted_rules)
        if attempted:
            return ResolveResult(
                hit=None,
                gap=FactGap(
                    fact_key=fact_key,
                    reason=GapReason.MEMORY_EXISTS_BUT_NO_MATCH,
                    detail=f"themes={themes}",
                    origin_ids_attempted=attempted,
                    attempted_rules=rule_labels,
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
    requirement: FactRequirement,
    vector_hits: list[KnowledgeHit],
    catalog_hits: list[KnowledgeHit],
    themes: tuple[str, ...],
    catalog: MemoryCatalog,
) -> tuple[KnowledgeHit | None, ResolutionRule | None, tuple[ResolutionRule, ...]]:
    """
    Escolhe o hit mais adequado intersectando elegibilidade (catálogo) com
    relevância semântica (ordem do vector search).

    1. Percorre vector_hits na ordem do retriever; retorna o primeiro cujo
       origin_id está no conjunto elegível do catálogo.
    2. Sem catálogo: primeiro vector hit que casa com o tema.
    3. Fallback: primeiro hit elegível do catálogo (ordem SQL).
    """
    attempted: list[ResolutionRule] = []
    eligible_catalog = _filter_hits_for_required_keys(
        _filter_hits_for_themes(catalog_hits, themes, catalog),
        requirement,
    )
    if eligible_catalog:
        attempted.append(ResolutionRule.CATALOG)

    eligible_ids = {hit.origin_id for hit in eligible_catalog}

    if eligible_ids:
        attempted.append(ResolutionRule.VECTOR_RETRIEVAL)
        for hit in vector_hits:
            if hit.origin_id in eligible_ids and _hit_matches_required_keys(hit, requirement):
                return hit, ResolutionRule.VECTOR_RETRIEVAL, tuple(attempted)

    if not eligible_catalog:
        attempted.append(ResolutionRule.VECTOR_RETRIEVAL)
        for hit in vector_hits:
            if _hit_matches_themes(hit, themes, catalog) and _hit_matches_required_keys(hit, requirement):
                return hit, ResolutionRule.VECTOR_RETRIEVAL, tuple(attempted)

    if eligible_catalog:
        picked = eligible_catalog[0]
        if _hit_matches_required_keys(picked, requirement):
            return picked, ResolutionRule.CATALOG, tuple(attempted)

    return None, None, tuple(attempted)


def _filter_hits_for_required_keys(
    hits: list[KnowledgeHit],
    requirement: FactRequirement,
) -> list[KnowledgeHit]:
    return [hit for hit in hits if _hit_matches_required_keys(hit, requirement)]


def _hit_matches_required_keys(hit: KnowledgeHit, requirement: FactRequirement) -> bool:
    if not _hit_matches_period(hit, requirement):
        return False
    required = _required_key_metrics_keys(requirement)
    if not required:
        return True
    return any(key in hit.key_metrics for key in required)


def _hit_matches_period(hit: KnowledgeHit, requirement: FactRequirement) -> bool:
    if not requirement.period:
        return True
    return period_in_context_key(hit.context_key, requirement.period)


def _required_key_metrics_keys(requirement: FactRequirement) -> tuple[str, ...]:
    keys: list[str] = []
    if requirement.matched_key:
        keys.append(requirement.matched_key)
    keys.extend(requirement.semantics.key_metrics_keys)
    return tuple(dict.fromkeys(key for key in keys if key))
