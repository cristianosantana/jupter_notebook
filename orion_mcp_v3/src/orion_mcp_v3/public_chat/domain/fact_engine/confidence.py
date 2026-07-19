"""Propagação de confiança por camada de extracção."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.fact_engine.trace import ExtractionPath

EXTRACTION_CONFIDENCE: dict[ExtractionPath, float] = {
    ExtractionPath.KEY_METRICS: 0.95,
    ExtractionPath.STRUCTURED_PARSER: 0.75,
    ExtractionPath.RANKING_DERIVED: 0.85,
    ExtractionPath.DERIVED_COMPUTE: 0.90,
    ExtractionPath.LLM_EXTRACT: 0.70,
}

MIN_FACT_CONFIDENCE = 0.65
MIN_DERIVE_CONFIDENCE = 0.80
# Persistência de cache: exige fatos + confiança útil; gaps sozinhos não bloqueiam.
MIN_CACHE_STORE_CONFIDENCE = 0.80


def confidence_for_path(path: ExtractionPath) -> float:
    return EXTRACTION_CONFIDENCE.get(path, 0.60)
