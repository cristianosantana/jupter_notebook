"""
Artefacto cognitivo — saída de aggregators / samplers / reducers (bloco 5 ORDEM_IMPLEMENTAÇÃO).

Não substitui linhas SQL brutas no consumidor final: ``summary`` deve ser estrutura agregada / referências mínimas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from orion_mcp_v3.contracts.provenance import CoverageInfo, ProvenanceAnchor


def heuristic_confidence_from_volume(row_count: int, *, baseline: float = 12.0) -> float:
    """Confiança heurística em [0.35, 0.95] a partir do volume processado."""
    n = max(0, int(row_count))
    return min(0.95, 0.35 + 0.60 * (1.0 - math.exp(-n / max(baseline, 1e-6))))


def artifact_provenance_anchor(*, kind: str, step: str, source: str) -> ProvenanceAnchor:
    return ProvenanceAnchor(artifact_id=f"{kind}:{step}", source=source, lineage=(kind, step))


@dataclass(frozen=True, slots=True)
class CognitiveArtifact:
    """
    Resultado analítico compacto com epistemologia explícita.

    ``confidence`` ∈ [0, 1]: heurística do produtor (ex.: volume, completude), não calibragem bayesiana.
    """

    kind: str
    summary: Mapping[str, Any]
    confidence: float
    coverage: CoverageInfo
    provenance: tuple[ProvenanceAnchor, ...] = field(default_factory=tuple)
