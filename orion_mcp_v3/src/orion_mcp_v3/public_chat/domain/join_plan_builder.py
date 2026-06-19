"""Construção de MemoryJoinPlan a partir de requirements."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.fact_engine.join_plan import MemoryJoinPlan, MemorySourceRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_semantics_catalog import FactSemanticsCatalog
from orion_mcp_v3.public_chat.domain.memory_catalog import MemoryCatalog, get_memory_catalog
from orion_mcp_v3.public_chat.domain.period_utils import normalize_period_key


def build_join_plan(
    requirements: tuple[FactRequirement, ...],
    *,
    catalog: MemoryCatalog | None = None,
) -> MemoryJoinPlan | None:
    mem_catalog = catalog or get_memory_catalog()
    period = normalize_period_key(_first_period(requirements))
    if not period:
        return None

    theme_facts: dict[str, list[str]] = {}
    for req in requirements:
        if req.semantics.aggregation_rule.value == "derived":
            continue
        themes = req.semantics.memory_themes or mem_catalog.themes_for_fact(req.fact_key)
        for theme in themes:
            theme_facts.setdefault(theme, []).append(req.fact_key)

    if not theme_facts:
        return None

    sources = tuple(
        MemorySourceRequirement(
            theme_slug=theme,
            fact_keys=tuple(dict.fromkeys(facts)),
            required=True,
        )
        for theme, facts in theme_facts.items()
    )
    return MemoryJoinPlan(
        period=period,
        required_sources=sources,
        join_keys=mem_catalog.join_keys,
    )


def _first_period(requirements: tuple[FactRequirement, ...]) -> str | None:
    for req in requirements:
        if req.period:
            return req.period
    return None
