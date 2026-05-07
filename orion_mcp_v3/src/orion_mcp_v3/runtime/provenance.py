"""Âncoras e cobertura de proveniência (Fase 0.3 — só estruturas, sem lógica)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


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
