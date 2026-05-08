"""Bloco de evidência analítica — resultado da camada EvidenceBuilder (ORDEM_IMPLEMENTAÇÃO §6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from orion_mcp_v3.runtime.provenance import CoverageInfo, ProvenanceAnchor


@dataclass(frozen=True, slots=True)
class EvidenceBlock:
    """
    Evidência estruturada derivada de linhas SQL + raciocínio analítico leve.

    ``insights`` agrega tendências, linha de base, variação e anomalias sem substituir
    o digest textual (:class:`~AnalyticalDigest`).
    """

    summary: str
    insights: Mapping[str, Any]
    metrics: Mapping[str, Any]
    confidence: float
    coverage: CoverageInfo
    provenance: tuple[ProvenanceAnchor, ...] = field(default_factory=tuple)
    sample_refs: tuple[str, ...] = ()
    supporting_data: Mapping[str, Any] = field(default_factory=dict)
