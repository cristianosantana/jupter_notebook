"""Âncoras e cobertura de proveniência — contratos sem dependência de ``runtime``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


def merge_coverage_infos(*infos: "CoverageInfo", notes: str | None = None) -> "CoverageInfo":
    """Agrega várias :class:`CoverageInfo` (rótulos com prefixo ``layer_<i>_``)."""
    if not infos:
        return CoverageInfo(labels={}, notes=notes)
    merged: dict[str, Any] = {}
    note_parts: list[str] = []
    for i, c in enumerate(infos):
        for k, v in dict(c.labels).items():
            merged[f"layer_{i}_{k}"] = v
        if c.notes:
            note_parts.append(c.notes)
    final_notes = notes if notes is not None else (" | ".join(note_parts) if note_parts else None)
    return CoverageInfo(labels=merged, notes=final_notes)


def merge_provenance_anchors(
    *bundles: tuple["ProvenanceAnchor", ...],
) -> tuple["ProvenanceAnchor", ...]:
    """Concatena e deduplica por ``(artifact_id, source)``."""
    seen: set[tuple[str, str | None]] = set()
    out: list[ProvenanceAnchor] = []
    for b in bundles:
        for p in b:
            key = (p.artifact_id, p.source)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class ProvenanceAnchor:
    """Referência estável ao artefacto ou passo gerador."""

    artifact_id: str
    source: str | None = None
    lineage: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CoverageInfo:
    """Cobertura declarada pelo produtor (sem inferência nem scoring aqui)."""

    labels: Mapping[str, Any] = field(default_factory=dict)
    notes: str | None = None
