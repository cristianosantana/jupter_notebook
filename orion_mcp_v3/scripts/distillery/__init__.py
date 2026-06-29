"""
Módulo de destilação supervisionada — Memória Remissiva V2.

Estrutura:
  distillery/
    __init__.py       ← API pública do módulo
    field_parsers.py  ← funções de extração e coerção de campos do payload LLM
    catalog.py        ← catálogos de dimension/metric_kind e resolvedores
    payload_parser.py ← parse_distillation_payload + enrich_knowledge_from_windows
    prompt_builder.py ← _build_prompt

Uso externo:
    from distillery import (
        parse_distillation_payload,
        enrich_knowledge_from_windows,
        build_distillation_prompt,
        DistillationResult,
    )
"""

from distillery.payload_parser import (
    enrich_knowledge_from_windows,
    parse_distillation_payload,
)
from distillery.prompt_builder import build_distillation_prompt
from distillery.result import DistillationResult

__all__ = [
    "parse_distillation_payload",
    "enrich_knowledge_from_windows",
    "build_distillation_prompt",
    "DistillationResult",
]
