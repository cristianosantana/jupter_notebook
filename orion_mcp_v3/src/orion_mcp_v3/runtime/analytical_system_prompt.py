"""
Prompt de sistema analítico injetado pelo :class:`CognitiveOrchestrator`.

O objetivo é dar ao LLM uma instrução explícita antes do turno do utilizador:
identidade, tom, estrutura de resposta, uso de evidência, período, cobertura e
anti-alucinação. Este módulo não executa retrieval nem analytics; apenas transforma
o estado cognitivo já resolvido em um :class:`ContextBlock` SYSTEM.
"""

from __future__ import annotations

from typing import Any, Mapping

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.prompts import get_prompt_registry

_PROMPTS = get_prompt_registry()
_PROMPT_ID = "analytical_system.fragments"
_IDENTITY = _PROMPTS.get_fragment(_PROMPT_ID, "identity")
_TONE = _PROMPTS.get_fragment(_PROMPT_ID, "tone")
_STRUCTURE_ANALYTICAL = _PROMPTS.get_fragment(_PROMPT_ID, "structure_analytical")
_STRUCTURE_MANAGERIAL_CLOSING = _PROMPTS.get_fragment(_PROMPT_ID, "structure_managerial_closing")
_STRUCTURE_CONVERSATIONAL = _PROMPTS.get_fragment(_PROMPT_ID, "structure_conversational")
_EVIDENCE_RULES = _PROMPTS.get_fragment(_PROMPT_ID, "evidence_rules")
_PERIOD_TEMPLATE = _PROMPTS.get_fragment(_PROMPT_ID, "period_template")
_COVERAGE_TEMPLATE = _PROMPTS.get_fragment(_PROMPT_ID, "coverage_template")
_CONFIDENCE_LOW = _PROMPTS.get_fragment(_PROMPT_ID, "confidence_low")
_ANTI_HALLUCINATION = _PROMPTS.get_fragment(_PROMPT_ID, "anti_hallucination")

_ANALYTICAL_INTENTS = {
    IntentType.ANALYTICAL,
    IntentType.TEMPORAL,
    IntentType.COMPARATIVE,
    IntentType.MONITORING,
    IntentType.HYBRID,
}


def build_analytical_system_block(
    cognitive_plan: CognitivePlan,
    *,
    evidence: EvidenceBlock | None = None,
    period_label: str | None = None,
) -> ContextBlock:
    """Constrói o bloco SYSTEM que orienta a narração final."""
    sections: list[str] = [_IDENTITY, _TONE]
    intent = cognitive_plan.intent_type

    if intent in _ANALYTICAL_INTENTS or cognitive_plan.needs_analytics:
        sections.append(_STRUCTURE_ANALYTICAL)
    else:
        sections.append(_STRUCTURE_CONVERSATIONAL)

    collection_slug = _collection_slug_from_evidence(evidence)
    if collection_slug == "fechamento_gerencial_por_mes":
        sections.append(_STRUCTURE_MANAGERIAL_CLOSING)

    if cognitive_plan.needs_analytics:
        sections.append(_EVIDENCE_RULES)

    period = _resolve_period(period_label, cognitive_plan, evidence)
    if period:
        sections.append(_PERIOD_TEMPLATE.format(period=period))

    if evidence is not None:
        coverage_note = _build_coverage_note(evidence)
        if coverage_note:
            sections.append(_COVERAGE_TEMPLATE.format(coverage_note=coverage_note))
        if evidence.confidence < 0.70:
            sections.append(_CONFIDENCE_LOW.format(confidence=evidence.confidence))

    # Anti-alucinação fica sempre por último para ser a regra mais recente no prompt.
    sections.append(_ANTI_HALLUCINATION)

    return ContextBlock(
        text="\n\n".join(sections),
        role=ContextRole.SYSTEM,
        source=ContextSource.SYSTEM,
        block_id="system:analytical_prompt",
        metadata={
            "fusion_kind": "system_prompt",
            "intent_type": intent.value,
            "needs_analytics": cognitive_plan.needs_analytics,
            "period": period or "não especificado",
            "evidence_confidence": evidence.confidence if evidence is not None else None,
            "collection_slug": collection_slug,
        },
        relevance_score=1.0,
        confidence=1.0,
        source_priority=1.0,
        cognitive_weight=1.0,
        information_density=0.9,
        compressibility=0.05,
    )


def _resolve_period(
    period_label: str | None,
    plan: CognitivePlan,
    evidence: EvidenceBlock | None,
) -> str | None:
    """Resolve o período em ordem de confiança: caller → plano → evidência."""
    if period_label and period_label.strip():
        return period_label.strip()

    hints = dict(plan.hints or {})
    date_from = hints.get("date_from")
    date_to = hints.get("date_to")
    if isinstance(date_from, str) and isinstance(date_to, str) and date_from and date_to:
        return f"{date_from} a {date_to}"

    explicit = hints.get("explicit_period")
    if isinstance(explicit, Mapping):
        date_from = explicit.get("date_from")
        date_to = explicit.get("date_to")
        if isinstance(date_from, str) and isinstance(date_to, str) and date_from and date_to:
            return f"{date_from} a {date_to}"

    ts = plan.time_scope
    if ts:
        return ts.strip()

    if evidence is not None:
        period = _period_from_mapping(evidence.metrics) or _period_from_mapping(evidence.insights)
        if period:
            return period

        period_coverage = evidence.insights.get("period_coverage")
        if isinstance(period_coverage, Mapping):
            d_min = period_coverage.get("date_min")
            d_max = period_coverage.get("date_max")
            if d_min and d_max:
                return f"{d_min} a {d_max}"
            start = period_coverage.get("date_from")
            end = period_coverage.get("date_to")
            if start and end:
                return f"{start} a {end}"

    return None


def _collection_slug_from_evidence(evidence: EvidenceBlock | None) -> str | None:
    if evidence is None:
        return None
    raw = evidence.supporting_data.get("direct_answer_set")
    if not isinstance(raw, Mapping):
        raw = evidence.insights.get("direct_answer_set")
    if not isinstance(raw, Mapping):
        return None
    slug = raw.get("collection_slug")
    return slug.strip() if isinstance(slug, str) and slug.strip() else None


def _period_from_mapping(values: Mapping[str, Any]) -> str | None:
    period = values.get("period")
    if isinstance(period, str) and period.strip():
        return period.strip()
    start = values.get("date_from")
    end = values.get("date_to")
    if isinstance(start, str) and isinstance(end, str) and start and end:
        return f"{start} a {end}"
    return None


def _build_coverage_note(evidence: EvidenceBlock) -> str:
    """Gera uma nota de cobertura curta e legível para o prompt de sistema."""
    labels = dict(evidence.coverage.labels or {})
    parts: list[str] = []

    templates_ok = labels.get("templates_ok")
    templates_total = labels.get("templates_total")
    if templates_ok is not None and templates_total is not None:
        parts.append(f"{templates_ok}/{templates_total} templates executados com sucesso")

    row_count = labels.get("total_rows") or labels.get("row_count") or evidence.metrics.get("n")
    if row_count is not None:
        parts.append(f"{row_count} registros analisados")

    if evidence.coverage.notes:
        parts.append(evidence.coverage.notes.strip())

    return "; ".join(parts)
