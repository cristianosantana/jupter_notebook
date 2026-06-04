"""Política de isolamento para contexto analítico histórico."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import unicodedata

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextSource
from orion_mcp_v3.runtime.analytical_signature import (
    AnalyticalSignature,
    signature_from_metadata,
    signatures_compatible,
)


@dataclass(frozen=True, slots=True)
class AnalyticalContextDecision:
    allow_historical_analytics: bool
    allow_vector_memory: bool
    max_memory_blocks: int
    reason: str


@dataclass(frozen=True, slots=True)
class AnalyticalContextFilterResult:
    kept_blocks: tuple[ContextBlock, ...]
    before_count: int
    after_count: int
    dropped_vector: int = 0
    dropped_analytical_memory: int = 0
    dropped_over_limit: int = 0
    reason: str = ""

    def as_trace(self, decision: AnalyticalContextDecision) -> dict[str, object]:
        return {
            "allow_vector_memory": decision.allow_vector_memory,
            "allow_historical_analytics": decision.allow_historical_analytics,
            "before_count": self.before_count,
            "after_count": self.after_count,
            "dropped_vector": self.dropped_vector,
            "dropped_analytical_memory": self.dropped_analytical_memory,
            "dropped_over_limit": self.dropped_over_limit,
            "reason": self.reason or decision.reason,
        }


_CONTINUITY_INTENTS = {
    IntentType.COMPARATIVE,
    IntentType.RECALL,
    IntentType.MONITORING,
    IntentType.HYBRID,
}

_ANALYTICAL_MARKERS = (
    "resposta direta:",
    "[template.",
    "resumo estatístico complementar",
    "ranking por",
    "métrica `",
    "metric `",
    "answer_plan",
    "direct_answer",
    "direct_answer_set",
)

_MEASURE_TERMS: dict[str, tuple[str, ...]] = {
    "valor_total": ("valor_total", "faturamento", "receita", "valor total"),
    "faturamento": ("faturamento", "receita"),
    "total_vendas": ("total_vendas", "vendas", "volume de vendas", "volume"),
    "total_os": ("total_os", "volume de os", "volume", "vendas"),
    "ticket_medio": ("ticket_medio", "ticket médio", "ticket medio", "ticket"),
}

_DIMENSION_TERMS: dict[str, tuple[str, ...]] = {
    "vendedor": ("vendedor", "vendedores"),
    "concessionaria": ("concessionaria", "concessionária", "concessionárias"),
    "concessionária": ("concessionaria", "concessionária", "concessionárias"),
    "forma_pagamento": ("forma_pagamento", "forma de pagamento", "pagamento"),
}


def _has_recall_hint(plan: CognitivePlan) -> bool:
    hints = plan.hints or {}
    if not isinstance(hints, Mapping):
        return False
    if hints.get("inherits_period") or hints.get("period_source") == "inherited_last_analytical_evidence":
        return True
    signals = hints.get("signals")
    if isinstance(signals, Mapping):
        return bool(
            signals.get("recall")
            or signals.get("comparative")
            or signals.get("inherits_period")
        )
    return False


def _is_continuity_turn(plan: CognitivePlan) -> bool:
    return (
        plan.intent_type in _CONTINUITY_INTENTS
        or plan.needs_comparison
        or plan.needs_baseline
        or plan.needs_trend_analysis
        or _has_recall_hint(plan)
    )


def _is_vector_block(block: ContextBlock) -> bool:
    return str(block.metadata.get("retrieval") or "").lower() == "vector"


def _is_analytical_memory_block(block: ContextBlock) -> bool:
    if block.source == ContextSource.BROKER:
        return True
    md = block.metadata or {}
    if signature_from_metadata(md) is not None:
        return True
    text = (block.text or "").lower()
    return any(marker in text for marker in _ANALYTICAL_MARKERS)


def _norm(text: str) -> str:
    raw = "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )
    return " ".join(raw.split())


def _terms_for(value: str | None, aliases: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(_norm(t) for t in aliases.get(value, (value,)) if t)


def _same_analytical_shape_ignoring_dates(
    current: AnalyticalSignature,
    historical: AnalyticalSignature,
) -> bool:
    if not historical.has_analytical_shape:
        return False
    if current.measure and historical.measure and current.measure != historical.measure:
        return False
    if current.dimension and historical.dimension and current.dimension != historical.dimension:
        return False
    if current.template_slug and historical.template_slug and current.template_slug != historical.template_slug:
        return False
    return True


def _text_matches_signature(text: str, current: AnalyticalSignature) -> bool:
    """Fallback para memória antiga que ainda não persistia `analytical_signature`."""

    blob = _norm(text)
    measure_terms = _terms_for(current.measure, _MEASURE_TERMS)
    dimension_terms = _terms_for(current.dimension, _DIMENSION_TERMS)
    measure_ok = not measure_terms or any(term in blob for term in measure_terms)
    dimension_ok = not dimension_terms or any(term in blob for term in dimension_terms)
    return bool(measure_ok and dimension_ok)


class AnalyticalContextIsolationPolicy:
    """Decide e aplica isolamento entre memória conversacional e evidência SQL antiga."""

    def decide(self, plan: CognitivePlan) -> AnalyticalContextDecision:
        if plan.needs_analytics and not _is_continuity_turn(plan):
            return AnalyticalContextDecision(
                allow_historical_analytics=False,
                allow_vector_memory=False,
                max_memory_blocks=2,
                reason="analytical_fresh_turn",
            )
        if plan.needs_analytics or _is_continuity_turn(plan):
            return AnalyticalContextDecision(
                allow_historical_analytics=True,
                allow_vector_memory=True,
                max_memory_blocks=4,
                reason="analytical_continuity",
            )
        return AnalyticalContextDecision(
            allow_historical_analytics=True,
            allow_vector_memory=True,
            max_memory_blocks=8,
            reason="non_analytical_turn",
        )

    def filter_with_trace(
        self,
        blocks: Sequence[ContextBlock],
        plan: CognitivePlan,
        *,
        signature: AnalyticalSignature | None = None,
    ) -> AnalyticalContextFilterResult:
        decision = self.decide(plan)
        kept: list[ContextBlock] = []
        dropped_vector = 0
        dropped_analytical = 0

        for block in blocks:
            is_vector = _is_vector_block(block)
            if is_vector and not decision.allow_vector_memory:
                dropped_vector += 1
                continue

            is_analytical = _is_analytical_memory_block(block)
            if is_analytical:
                historical_sig = signature_from_metadata(block.metadata or {})
                if signature is not None and historical_sig is not None and plan.needs_comparison:
                    compatible = _same_analytical_shape_ignoring_dates(signature, historical_sig)
                elif signature is not None and historical_sig is not None:
                    compatible = signatures_compatible(signature, historical_sig)
                elif signature is not None and plan.needs_comparison:
                    compatible = _text_matches_signature(block.text or "", signature)
                else:
                    compatible = False
                if not decision.allow_historical_analytics or not compatible:
                    dropped_analytical += 1
                    continue

            kept.append(block)

        kept.sort(key=lambda b: b.compute_attention_score(), reverse=True)
        limited = tuple(kept[: decision.max_memory_blocks])
        dropped_over_limit = max(0, len(kept) - len(limited))
        return AnalyticalContextFilterResult(
            kept_blocks=limited,
            before_count=len(blocks),
            after_count=len(limited),
            dropped_vector=dropped_vector,
            dropped_analytical_memory=dropped_analytical,
            dropped_over_limit=dropped_over_limit,
            reason=decision.reason,
        )

    def filter_blocks(
        self,
        blocks: Sequence[ContextBlock],
        plan: CognitivePlan,
        *,
        signature: AnalyticalSignature | None = None,
    ) -> tuple[ContextBlock, ...]:
        return self.filter_with_trace(blocks, plan, signature=signature).kept_blocks
