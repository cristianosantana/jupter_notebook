"""Catálogo seguro das capacidades analíticas expostas ao interpretador."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from orion_mcp_v3.broker.query_templates import QueryTemplateRegistry


@dataclass(frozen=True, slots=True)
class QueryCapabilityEntry:
    template_slug: str
    metrics: Mapping[str, tuple[str, ...]]
    dimensions: Mapping[str, tuple[str, ...]]
    operations: tuple[str, ...]
    default_metric: str | None = None
    default_dimension: str | None = None

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "template_slug": self.template_slug,
            "metrics": {
                key: {"synonyms": list(values)}
                for key, values in sorted(self.metrics.items())
            },
            "dimensions": {
                key: {"synonyms": list(values)}
                for key, values in sorted(self.dimensions.items())
            },
            "operations": list(self.operations),
            "default_metric": self.default_metric,
            "default_dimension": self.default_dimension,
        }


@dataclass(frozen=True, slots=True)
class QueryCapabilityCatalog:
    entries: tuple[QueryCapabilityEntry, ...]

    def as_prompt_dict(self) -> list[dict[str, Any]]:
        return [entry.as_prompt_dict() for entry in self.entries]

    @property
    def metric_keys(self) -> set[str]:
        return {key for entry in self.entries for key in entry.metrics}

    @property
    def dimension_keys(self) -> set[str]:
        return {key for entry in self.entries for key in entry.dimensions}

    @property
    def operation_keys(self) -> set[str]:
        return {op for entry in self.entries for op in entry.operations}

    def supports(
        self,
        *,
        metric: str | None = None,
        dimension: str | None = None,
        operation: str | None = None,
    ) -> bool:
        for entry in self.entries:
            if metric is not None and metric not in entry.metrics:
                continue
            if dimension is not None and dimension not in entry.dimensions:
                continue
            if operation is not None and operation not in entry.operations:
                continue
            return True
        return False


def build_query_capability_catalog(registry: QueryTemplateRegistry) -> QueryCapabilityCatalog:
    entries: list[QueryCapabilityEntry] = []
    for slug in registry.slugs:
        template = registry.get(slug)
        capability = template.capability if template is not None else None
        if capability is None:
            continue
        metrics = {
            key: _dedupe((measure.label, measure.column, *measure.synonyms, key))
            for key, measure in capability.measures.items()
        }
        dimensions = {
            key: _dedupe((dimension.label, dimension.column, *dimension.synonyms, key))
            for key, dimension in capability.dimensions.items()
        }
        entries.append(
            QueryCapabilityEntry(
                template_slug=slug,
                metrics=metrics,
                dimensions=dimensions,
                operations=tuple(capability.supported_operations),
                default_metric=capability.default_measure,
                default_dimension=capability.default_dimension,
            )
        )
    return QueryCapabilityCatalog(entries=tuple(entries))


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        out.append(normalized)
    return tuple(out)
