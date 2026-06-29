"""Carregamento do catálogo de semântica de facts."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

import yaml

from orion_mcp_v3.public_chat.domain.fact_engine.semantics import (
    AggregationRule,
    Comparator,
    FactSemantics,
    SourcePriority,
)


class FactSemanticsCatalog:
    def __init__(self, facts: Mapping[str, FactSemantics], *, version: str = "v1") -> None:
        self._facts = dict(facts)
        self.version = version

    def get(self, fact_key: str) -> FactSemantics | None:
        return self._facts.get(fact_key)

    def require(self, fact_key: str) -> FactSemantics:
        item = self.get(fact_key)
        if item is None:
            raise KeyError(f"fact_key {fact_key!r} not in catalog")
        return item

    @property
    def fact_keys(self) -> tuple[str, ...]:
        return tuple(self._facts.keys())


def _parse_source_priority(raw: Any) -> tuple[SourcePriority, ...]:
    if not isinstance(raw, list):
        return ()
    result: list[SourcePriority] = []
    for item in raw:
        try:
            result.append(SourcePriority(str(item)))
        except ValueError:
            continue
    return tuple(result)


def _parse_semantics(fact_key: str, raw: Mapping[str, Any]) -> FactSemantics:
    agg = AggregationRule(str(raw.get("aggregation_rule") or "lookup"))
    comp = Comparator(str(raw.get("comparator") or "none"))
    derived_from = tuple(str(item) for item in (raw.get("derived_from") or []))
    memory_themes = tuple(str(item) for item in (raw.get("memory_themes") or []))
    key_metrics_keys = tuple(str(item) for item in (raw.get("key_metrics_keys") or []))
    return FactSemantics(
        fact_key=fact_key,
        aggregation_rule=agg,
        comparator=comp,
        source_priority=_parse_source_priority(raw.get("source_priority")),
        value_kind=str(raw.get("value_kind") or "label"),
        allows_multiple_values=bool(raw.get("allows_multiple_values", False)),
        derived_from=derived_from,
        memory_themes=memory_themes,
        key_metrics_keys=key_metrics_keys,
        key_metrics_entity_field=str(raw.get("key_metrics_entity_field") or "tipo"),
        key_metrics_value_field=str(raw.get("key_metrics_value_field") or "valor"),
    )


def load_fact_semantics_catalog(path: Path | None = None) -> FactSemanticsCatalog:
    if path is not None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        config_file = resources.files("orion_mcp_v3.public_chat.config").joinpath("fact_semantics.yaml")
        raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("fact_semantics.yaml must be a mapping")
    version = str(raw.get("version") or "v1")
    facts_raw = raw.get("facts") or {}
    if not isinstance(facts_raw, dict):
        raise ValueError("fact_semantics.yaml facts must be a mapping")
    facts = {
        str(key): _parse_semantics(str(key), item if isinstance(item, dict) else {})
        for key, item in facts_raw.items()
    }
    return FactSemanticsCatalog(facts, version=version)


@lru_cache(maxsize=1)
def get_fact_semantics_catalog() -> FactSemanticsCatalog:
    return load_fact_semantics_catalog()
