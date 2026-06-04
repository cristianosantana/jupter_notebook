"""Extrai sinais genéricos dos regex heurísticos existentes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.runtime import intent_patterns as P
from orion_mcp_v3.runtime.intent_resolver import _explicit_period_hint
from orion_mcp_v3.runtime.temporal_reference import temporal_anaphora_match


@dataclass(frozen=True, slots=True)
class HeuristicSignal:
    kind: str
    label: str
    confidence: float
    matched_text: str | None = None
    source: str = "regex"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "confidence": self.confidence,
            "matched_text": self.matched_text,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class HeuristicSignalCatalog:
    signals: tuple[HeuristicSignal, ...]

    def as_prompt_dict(self) -> list[dict[str, Any]]:
        return [signal.as_dict() for signal in self.signals]

    def labels(self, kind: str) -> tuple[str, ...]:
        return tuple(signal.label for signal in self.signals if signal.kind == kind)


def extract_heuristic_signals(message: str, recent_context: str | None = None) -> HeuristicSignalCatalog:
    """Converte regex atuais em evidências estruturadas, sem decidir a intenção final."""
    text = (message or "").strip()
    blob = f"{text}\n{(recent_context or '').strip()}".strip()
    signals: list[HeuristicSignal] = []

    for group, kind, label, confidence in (
        (P.COMPARATIVE_PATTERNS, "intent_signal", "comparative", 0.8),
        (P.TEMPORAL_PATTERNS, "intent_signal", "temporal", 0.7),
        (P.ANALYTICAL_PATTERNS, "intent_signal", "analytical", 0.75),
        (P.RECALL_PATTERNS, "intent_signal", "recall", 0.65),
        (P.MONITORING_PATTERNS, "intent_signal", "monitoring", 0.75),
        (P.EXECUTION_PATTERNS, "intent_signal", "execution", 0.75),
    ):
        signals.extend(_signals_from_group(group, blob, kind=kind, label=label, confidence=confidence))

    period = _explicit_period_hint(blob)
    if period is not None:
        signals.append(
            HeuristicSignal(
                kind="time_signal",
                label=str(period.get("period_source") or "explicit_period"),
                confidence=0.9,
                matched_text=f"{period['date_from']}/{period['date_to']}",
            )
        )

    signals.extend(_semantic_signals(blob))
    return HeuristicSignalCatalog(signals=tuple(_dedupe_signals(signals)))


def _signals_from_group(
    patterns: tuple[Any, ...],
    text: str,
    *,
    kind: str,
    label: str,
    confidence: float,
) -> list[HeuristicSignal]:
    out: list[HeuristicSignal] = []
    for pattern in patterns:
        match = pattern.search(text)
        if match is None:
            continue
        out.append(
            HeuristicSignal(
                kind=kind,
                label=label,
                confidence=confidence,
                matched_text=_clean_match(match.group(0)),
            )
        )
    return out


def _semantic_signals(text: str) -> list[HeuristicSignal]:
    lower = text.lower()
    out: list[HeuristicSignal] = []
    for label, needles in {
        "revenue": ("faturamento", "faturou", "receita", "recebimento", "recebido"),
        "ticket": ("ticket", "ticket médio"),
        "sales": ("venda", "vendas", "volume de vendas"),
    }.items():
        matched = next((needle for needle in needles if needle in lower), None)
        if matched:
            out.append(HeuristicSignal("metric_signal", label, 0.75, matched))

    for label, needles in {
        "seller": ("vendedor", "vendedores"),
        "dealership": ("concessionária", "concessionaria"),
        "payment_method": ("pagamento", "forma de pagamento", "meio de pagamento"),
    }.items():
        matched = next((needle for needle in needles if needle in lower), None)
        if matched:
            out.append(HeuristicSignal("dimension_signal", label, 0.75, matched))

    for label, needles in {
        "ranking_desc": ("maior", "top", "ranking"),
        "ranking_asc": ("menor",),
        "comparison": ("compar", "cruz", "versus", "vs"),
        "delta": ("queda", "subiu", "aumento", "aumentou", "caiu", "reduziu", "diminuiu"),
        "list": ("por ", "cada "),
    }.items():
        matched = next((needle for needle in needles if needle in lower), None)
        if matched:
            out.append(HeuristicSignal("operation_signal", label, 0.7, matched.strip()))

    period_match = temporal_anaphora_match(text)
    if period_match:
        out.append(HeuristicSignal("followup_signal", "inherits_period", 0.7, period_match))

    for label, needles in {
        "same_operation": ("faz o mesmo", "mesmo por", "cruze com"),
    }.items():
        matched = next((needle for needle in needles if needle in lower), None)
        if matched:
            out.append(HeuristicSignal("followup_signal", label, 0.7, matched))
    return out


def _clean_match(value: str) -> str:
    return " ".join(value.split())[:80]


def _dedupe_signals(signals: list[HeuristicSignal]) -> list[HeuristicSignal]:
    out: list[HeuristicSignal] = []
    seen: set[tuple[str, str, str | None]] = set()
    for signal in signals:
        key = (signal.kind, signal.label, signal.matched_text)
        if key in seen:
            continue
        seen.add(key)
        out.append(signal)
    return out
