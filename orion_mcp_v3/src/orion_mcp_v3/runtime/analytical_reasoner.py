"""Reasoner determinístico entre evidência executada e narração."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from orion_mcp_v3.contracts.analytics_outcome import AnalyticsOutcome, AnalyticsOutcomeStatus
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.evidence_contract import EvidenceContract, EvidencePriority, EvidenceStatus
from orion_mcp_v3.contracts.reasoning_result import AnalyticalReasoningResult, AnswerMode


class AnalyticalReasoner:
    """Produz decisão estruturada para o narrador sem chamar LLM."""

    def reason(
        self,
        message: str,
        *,
        cognitive_plan: CognitivePlan,
        analytics_outcome: AnalyticsOutcome,
        last_analytical_evidence: EvidenceBlock | None = None,
    ) -> AnalyticalReasoningResult:
        evidence = analytics_outcome.evidence
        contract = _contract_from(evidence) or analytics_outcome.evidence_contract

        if analytics_outcome.status in {
            AnalyticsOutcomeStatus.EXECUTION_FAILURE,
            AnalyticsOutcomeStatus.AGGREGATION_FAILURE,
        }:
            failure = analytics_outcome.failure or contract.failure
            risk = (
                f"Falha operacional em {failure.stage}: {failure.failure_type}."
                if failure is not None
                else "Falha operacional no pipeline analítico."
            )
            return AnalyticalReasoningResult(
                facts=(),
                insights=(),
                risks=(risk,),
                limitations=("A resposta quantitativa não deve ser inferida sem nova evidência.",),
                evidence_contract=contract,
                answer_mode=AnswerMode.OPERATIONAL_FAILURE,
                should_narrate=True,
            )

        if analytics_outcome.status == AnalyticsOutcomeStatus.EXECUTED_EMPTY:
            return AnalyticalReasoningResult(
                facts=("A consulta analítica executou, mas não retornou linhas para os filtros atuais.",),
                limitations=("Não há observações no resultado atual para sustentar uma métrica quantitativa.",),
                evidence_contract=contract,
                answer_mode=AnswerMode.ANALYTICAL,
                should_narrate=True,
            )

        if analytics_outcome.status == AnalyticsOutcomeStatus.NO_PLAN:
            return AnalyticalReasoningResult(
                limitations=("Nenhum plano analítico seguro foi produzido para esta pergunta.",),
                evidence_contract=contract,
                answer_mode=AnswerMode.CLARIFICATION_NEEDED,
                should_narrate=True,
                blocked_reason="no_analytical_plan",
            )

        closing_set = _managerial_closing_answer_set(evidence)
        if closing_set is not None:
            direct_contract = EvidenceContract.present(
                row_count=contract.row_count,
                full_dataset_available=contract.full_dataset_available,
                source_priority=EvidencePriority.DIRECT_ANSWER,
                operational_confidence=contract.operational_confidence,
                safe_for_record_level_claims=contract.safe_for_record_level_claims,
            )
            facts, insights, risks = _managerial_closing_reasoning(closing_set)
            return AnalyticalReasoningResult(
                facts=facts,
                insights=insights,
                risks=risks,
                limitations=_material_limitations(direct_contract, evidence=evidence),
                evidence_contract=direct_contract,
                answer_mode=AnswerMode.EXECUTIVE,
                should_narrate=True,
            )

        if _has_direct_answer(evidence):
            direct_contract = EvidenceContract.present(
                row_count=contract.row_count,
                full_dataset_available=contract.full_dataset_available,
                source_priority=EvidencePriority.DIRECT_ANSWER,
                operational_confidence=contract.operational_confidence,
                safe_for_record_level_claims=contract.safe_for_record_level_claims,
            )
            fact = (
                "Resposta direta composta disponível na evidência; preservar as seções."
                if _has_direct_answer_set(evidence)
                else "Resposta direta disponível na evidência; preservar a seção `Resposta direta:`."
            )
            structural_facts, structural_insights = _direct_answer_structural_reasoning(evidence, message=message)
            return AnalyticalReasoningResult(
                facts=(fact, *structural_facts),
                insights=structural_insights,
                risks=(),
                limitations=_material_limitations(direct_contract, evidence=evidence),
                evidence_contract=direct_contract,
                answer_mode=AnswerMode.LITERAL,
                should_narrate=True,
            )

        mode = AnswerMode.EXECUTIVE if _asks_executive(message) else AnswerMode.ANALYTICAL
        facts = (
            f"Evidência analítica disponível com {contract.row_count} registro(s).",
            "Agregados são autoritativos." if contract.aggregates_are_authoritative else "Agregados não estão marcados como autoritativos.",
        )
        insights = (
            ("A evidência é segura para análise quantitativa.",)
            if contract.safe_for_quantitative_analysis
            else ()
        )
        return AnalyticalReasoningResult(
            facts=facts,
            insights=insights,
            risks=(),
            limitations=_material_limitations(contract),
            evidence_contract=contract,
            answer_mode=mode,
            should_narrate=True,
        )


def _contract_from(evidence: EvidenceBlock | None) -> EvidenceContract | None:
    if evidence is None:
        return None
    raw = evidence.supporting_data.get("evidence_contract") if evidence.supporting_data else None
    if not isinstance(raw, Mapping):
        raw = evidence.metrics.get("evidence_contract") if evidence.metrics else None
    if not isinstance(raw, Mapping):
        return None
    return EvidenceContract.from_mapping(raw)


def _has_direct_answer(evidence: EvidenceBlock | None) -> bool:
    if evidence is None:
        return False
    if _has_direct_answer_set(evidence):
        return True
    if isinstance(evidence.supporting_data.get("direct_answer"), Mapping):
        return True
    return isinstance(evidence.insights.get("direct_answer"), Mapping)


def _has_direct_answer_set(evidence: EvidenceBlock | None) -> bool:
    if evidence is None:
        return False
    if isinstance(evidence.supporting_data.get("direct_answer_set"), Mapping):
        return True
    return isinstance(evidence.insights.get("direct_answer_set"), Mapping)


def _direct_answer(evidence: EvidenceBlock | None) -> Mapping[str, Any] | None:
    if evidence is None:
        return None
    raw = evidence.supporting_data.get("direct_answer")
    if isinstance(raw, Mapping):
        return raw
    raw = evidence.insights.get("direct_answer")
    return raw if isinstance(raw, Mapping) else None


def _direct_answer_set(evidence: EvidenceBlock | None) -> Mapping[str, Any] | None:
    if evidence is None:
        return None
    raw = evidence.supporting_data.get("direct_answer_set")
    if isinstance(raw, Mapping):
        return raw
    raw = evidence.insights.get("direct_answer_set")
    return raw if isinstance(raw, Mapping) else None


def _managerial_closing_answer_set(evidence: EvidenceBlock | None) -> Mapping[str, Any] | None:
    raw = _direct_answer_set(evidence)
    if not isinstance(raw, Mapping):
        return None
    if raw.get("collection_slug") != "fechamento_gerencial_por_mes":
        return None
    sections = raw.get("executive_sections")
    if not isinstance(sections, (list, tuple)) or not sections:
        return None
    return raw


def _managerial_closing_reasoning(answer_set: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    facts: list[str] = []
    insights: list[str] = []
    risks: list[str] = []
    headline = str(answer_set.get("headline") or "").strip()
    if headline:
        facts.append(headline)
    data_quality = answer_set.get("data_quality")
    if isinstance(data_quality, Mapping):
        templates = data_quality.get("templates_projected")
        rows = data_quality.get("rows_projected")
        if templates is not None and rows is not None:
            facts.append(f"Fechamento projetado com {templates} template(s) e {rows} registro(s).")
    sections = answer_set.get("executive_sections")
    if isinstance(sections, (list, tuple)):
        for section in sections:
            if not isinstance(section, Mapping):
                continue
            label = str(section.get("label") or section.get("template_slug") or "Seção").strip()
            top = str(section.get("top") or "").strip()
            top_value = str(section.get("top_value") or "").strip()
            share = str(section.get("share_percent") or "").strip()
            if top and top_value:
                suffix = f" ({share})" if share else ""
                insights.append(f"{label}: líder {top} com {top_value}{suffix}.")
            warnings = section.get("warnings")
            if isinstance(warnings, (list, tuple)):
                for warning in warnings:
                    text = str(warning or "").strip()
                    if text:
                        risks.append(f"{label}: {text}.")
    if not facts:
        facts.append("Fechamento gerencial estruturado disponível na evidência.")
    return tuple(facts), tuple(insights), tuple(risks)


def _direct_answer_structural_reasoning(
    evidence: EvidenceBlock | None,
    *,
    message: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    direct = _direct_answer(evidence)
    if direct is None:
        return (), ()

    rows = _direct_answer_rows(direct)
    plan = direct.get("plan")
    plan = plan if isinstance(plan, Mapping) else {}
    facts: list[str] = []
    insights: list[str] = []

    if rows:
        facts.append(f"Resposta direta materializada com {len(rows)} registro(s).")

    measure = _string_or_none(plan.get("measure"))
    dimension = _string_or_none(plan.get("dimension"))
    if rows and measure:
        scored: list[tuple[float, Mapping[str, Any]]] = []
        totals: list[Decimal] = []
        zero_count = 0
        for row in rows:
            value = _float_or_none(row.get(measure))
            if value is None:
                continue
            if value == 0.0:
                zero_count += 1
            scored.append((value, row))
            decimal_value = _decimal_or_none(row.get(measure))
            if decimal_value is not None:
                totals.append(decimal_value)

        if scored:
            if totals and _asks_totalization(message, plan):
                insights.append(f"Total {measure}: {_format_decimal(sum(totals, Decimal('0')))}.")
            top_value, top_row = max(scored, key=lambda item: item[0])
            label = _string_or_none(top_row.get(dimension)) if dimension else None
            subject = label or "maior valor"
            raw_value = top_row.get(measure)
            insights.append(f"Maior {measure}: {subject} ({raw_value if raw_value is not None else top_value}).")
        if zero_count:
            insights.append(f"{zero_count} registro(s) com {measure} igual a zero.")

    sort = plan.get("sort")
    if isinstance(sort, Mapping):
        field = _string_or_none(sort.get("field"))
        direction = _string_or_none(sort.get("direction"))
        if field:
            suffix = f" ({direction})" if direction else ""
            insights.append(f"Resposta ordenada por {field}{suffix}.")

    return tuple(facts), tuple(insights)


def _direct_answer_rows(direct: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    rows = direct.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return ()
    return tuple(row for row in rows if isinstance(row, Mapping))


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.01")) if value == value.quantize(Decimal("0.01")) else value.normalize()
    return format(normalized, "f")


def _asks_totalization(message: str, plan: Mapping[str, Any]) -> bool:
    operation = _string_or_none(plan.get("operation"))
    if operation and operation.lower() in {"sum", "total", "totalize", "totalizar"}:
        return True
    return bool(
        re.search(
            r"\b(total|totais|soma|somar|somado|somada|somatorio|somatório|acumulado|acumulada)\b",
            message or "",
            re.IGNORECASE,
        )
    )


def _asks_executive(message: str) -> bool:
    return bool(re.search(r"\b(executiv[ao]|resum[ao]|objetiv[ao]|direto)\b", message or "", re.IGNORECASE))


def _material_limitations(contract: EvidenceContract, *, evidence: EvidenceBlock | None = None) -> tuple[str, ...]:
    out: list[str] = []
    if contract.status == EvidenceStatus.PIPELINE_FAILURE:
        out.append("Há falha operacional material no pipeline.")
    if contract.truncated_payload_detected:
        out.append("Payload parcial detectado; não usar preview como dataset completo.")
    if not contract.safe_for_record_level_claims and contract.status == EvidenceStatus.PRESENT:
        out.append("Não é seguro fazer afirmações registro a registro.")
    if evidence is not None and evidence.confidence < 0.70:
        out.append(f"A confiança da evidência é {evidence.confidence:.2f}; sinalizar possível cobertura parcial.")
    return tuple(out)
