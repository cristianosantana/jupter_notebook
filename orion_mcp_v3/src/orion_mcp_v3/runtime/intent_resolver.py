"""
Resolve intenção cognitiva por heurística (sem LLM).

Usa :mod:`intent_patterns` e devolve :class:`~orion_mcp_v3.contracts.cognitive_plan.CognitivePlan`.
"""

from __future__ import annotations

from orion_mcp_v3.contracts.cognitive_plan import (
    AttentionProfile,
    CognitivePlan,
    IntentType,
)
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy
from orion_mcp_v3.runtime import intent_patterns as P
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy


def map_attention_profile_to_policy(profile: AttentionProfile) -> AttentionPolicy:
    """Liga :class:`~AttentionProfile` (contrato) a :class:`~AttentionPolicy` (allocator)."""
    return _ATTENTION_TO_POLICY[profile]


_ATTENTION_TO_POLICY: dict[AttentionProfile, AttentionPolicy] = {
    AttentionProfile.ANALYTICAL: AttentionPolicy.ANALYTICAL,
    AttentionProfile.CONVERSATIONAL: AttentionPolicy.CONVERSATIONAL,
    AttentionProfile.PLANNING: AttentionPolicy.PLANNING,
    AttentionProfile.HYBRID: AttentionPolicy.HYBRID,
    AttentionProfile.MONITORING: AttentionPolicy.MONITORING,
    AttentionProfile.EXECUTION: AttentionPolicy.EXECUTION,
}


def attention_profile_to_policy_key(profile: AttentionProfile) -> str:
    """Valor estável para logging (mesmo slug que :class:`~AttentionPolicy`)."""
    return profile.value


class IntentResolver:
    """Análise lexical mínima; evoluir para IntentResolver com modelo quando existir política."""

    def resolve(self, user_input: str, recent_context: str | None = None) -> CognitivePlan:
        text = (user_input or "").strip()
        blob = f"{text}\n{(recent_context or '').strip()}".strip()

        cmp_ = P._any_match(P.COMPARATIVE_PATTERNS, blob)
        tmp = P._any_match(P.TEMPORAL_PATTERNS, blob)
        ana = P._any_match(P.ANALYTICAL_PATTERNS, blob)
        rec = P._any_match(P.RECALL_PATTERNS, blob)
        mon = P._any_match(P.MONITORING_PATTERNS, blob)
        exe = P._any_match(P.EXECUTION_PATTERNS, blob)

        needs_comparison = cmp_
        needs_temporal_context = tmp
        needs_analytics = ana
        needs_memory = rec
        needs_baseline = cmp_ and ana
        needs_trend_analysis = ana and tmp
        needs_entity_resolution = ana and ("cliente" in blob.lower() or "customer" in blob.lower())

        intent_type = self._infer_intent_type(
            ana=ana,
            rec=rec,
            cmp_=cmp_,
            tmp=tmp,
            mon=mon,
            exe=exe,
        )
        attention_profile = self._infer_attention_profile(intent_type, mon=mon, exe=exe)
        retrieval_strategy = self._infer_retrieval(ana, rec)
        confidence = self._confidence(
            ana=ana,
            rec=rec,
            cmp_=cmp_,
            tmp=tmp,
            mon=mon,
            exe=exe,
        )

        metrics = self._extract_metric_hints(blob)

        return CognitivePlan(
            intent_type=intent_type,
            needs_memory=needs_memory,
            needs_analytics=needs_analytics,
            needs_comparison=needs_comparison,
            needs_temporal_context=needs_temporal_context,
            needs_baseline=needs_baseline,
            needs_trend_analysis=needs_trend_analysis,
            needs_entity_resolution=needs_entity_resolution,
            confidence=confidence,
            entities=(),
            metrics=metrics,
            time_scope=self._time_scope_hint(blob) if tmp else None,
            retrieval_strategy=retrieval_strategy,
            attention_profile=attention_profile,
            hints={
                "resolver": "heuristic_v1",
                "signals": {
                    "comparative": cmp_,
                    "temporal": tmp,
                    "analytical": ana,
                    "recall": rec,
                    "monitoring": mon,
                    "execution": exe,
                },
            },
        )

    def _infer_intent_type(
        self,
        *,
        ana: bool,
        rec: bool,
        cmp_: bool,
        tmp: bool,
        mon: bool,
        exe: bool,
    ) -> IntentType:
        if mon:
            return IntentType.MONITORING
        if exe:
            return IntentType.EXECUTION
        if rec and not ana:
            return IntentType.RECALL
        if cmp_ and (ana or tmp):
            return IntentType.COMPARATIVE
        if tmp and not ana and not rec:
            return IntentType.TEMPORAL
        if ana and rec:
            return IntentType.HYBRID
        if ana:
            return IntentType.ANALYTICAL
        if rec:
            return IntentType.CONVERSATIONAL
        return IntentType.CONVERSATIONAL

    def _infer_attention_profile(
        self,
        intent: IntentType,
        *,
        mon: bool,
        exe: bool,
    ) -> AttentionProfile:
        if mon or intent == IntentType.MONITORING:
            return AttentionProfile.MONITORING
        if exe or intent == IntentType.EXECUTION:
            return AttentionProfile.EXECUTION
        if intent == IntentType.ANALYTICAL:
            return AttentionProfile.ANALYTICAL
        if intent in (IntentType.HYBRID, IntentType.COMPARATIVE):
            return AttentionProfile.HYBRID
        return AttentionProfile.CONVERSATIONAL

    def _infer_retrieval(self, ana: bool, rec: bool) -> RetrievalStrategy:
        if ana and rec:
            return RetrievalStrategy.HYBRID
        if ana:
            return RetrievalStrategy.BROKER_FANOUT
        if rec:
            return RetrievalStrategy.KEYWORD
        return RetrievalStrategy.KEYWORD

    def _confidence(
        self,
        *,
        ana: bool,
        rec: bool,
        cmp_: bool,
        tmp: bool,
        mon: bool,
        exe: bool,
    ) -> float:
        score = 0.35
        for flag in (ana, rec, cmp_, tmp, mon, exe):
            if flag:
                score += 0.11
        return min(0.95, round(score, 3))

    def _time_scope_hint(self, blob: str) -> str | None:
        lower = blob.lower()
        if "últimos" in lower or "last" in lower or "past" in lower:
            return "relative_window"
        if "hoje" in lower or "today" in lower:
            return "today"
        if "ontem" in lower or "yesterday" in lower:
            return "yesterday"
        return None

    def _extract_metric_hints(self, blob: str) -> tuple[str, ...]:
        out: list[str] = []
        lower = blob.lower()
        for label, needle in (
            ("revenue", "faturamento"),
            ("revenue", "revenue"),
            ("ticket", "ticket"),
            ("sales", "os"),
        ):
            if needle in lower and label not in out:
                out.append(label)
        return tuple(out)
