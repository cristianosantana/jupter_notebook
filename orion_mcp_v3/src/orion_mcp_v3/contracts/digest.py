"""Digest analítico compacto para contexto LLM (Fase 3.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from orion_mcp_v3.runtime.provenance import CoverageInfo


@dataclass(frozen=True, slots=True)
class AnalyticalDigest:
    """
    Visão agregada de um conjunto analítico: texto curto + métricas + amostra + cobertura.

    Campos opcionais preenchidos após destilação map-reduce (Fase 4).
    """

    summary: str
    volume: int
    sample: tuple[Mapping[str, Any], ...] = ()
    coverage: CoverageInfo = field(default_factory=CoverageInfo)
    source_refs: tuple[str, ...] = ()
    aggregation_logic: str | None = None
