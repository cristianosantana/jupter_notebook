"""Reasoner determinístico entre evidência executada e narração."""

from __future__ import annotations

import re
from collections.abc import Mapping

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
            return AnalyticalReasoningResult(
                facts=(fact,),
                insights=(),
                risks=(),
                limitations=_material_limitations(direct_contract),
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


def _asks_executive(message: str) -> bool:
    return bool(re.search(r"\b(executiv[ao]|resum[ao]|objetiv[ao]|direto)\b", message or "", re.IGNORECASE))


def _material_limitations(contract: EvidenceContract) -> tuple[str, ...]:
    out: list[str] = []
    if contract.status == EvidenceStatus.PIPELINE_FAILURE:
        out.append("Há falha operacional material no pipeline.")
    if contract.truncated_payload_detected:
        out.append("Payload parcial detectado; não usar preview como dataset completo.")
    if not contract.safe_for_record_level_claims and contract.status == EvidenceStatus.PRESENT:
        out.append("Não é seguro fazer afirmações registro a registro.")
    return tuple(out)
