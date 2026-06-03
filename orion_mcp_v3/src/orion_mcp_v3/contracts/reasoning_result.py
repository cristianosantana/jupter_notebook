"""Resultado estruturado do raciocínio analítico pré-narração."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from orion_mcp_v3.contracts.evidence_contract import EvidenceContract


class AnswerMode(str, Enum):
    LITERAL = "literal"
    EXECUTIVE = "executive"
    ANALYTICAL = "analytical"
    OPERATIONAL_FAILURE = "operational_failure"
    CLARIFICATION_NEEDED = "clarification_needed"


@dataclass(frozen=True, slots=True)
class AnalyticalReasoningResult:
    facts: tuple[str, ...] = ()
    insights: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    confidence: dict[str, float] | None = None
    evidence_contract: EvidenceContract = EvidenceContract()
    answer_mode: AnswerMode = AnswerMode.ANALYTICAL
    should_narrate: bool = True
    blocked_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "facts": list(self.facts),
            "insights": list(self.insights),
            "risks": list(self.risks),
            "limitations": list(self.limitations),
            "confidence": dict(self.confidence or self.evidence_contract.operational_confidence.as_dict()),
            "evidence_contract": self.evidence_contract.as_dict(),
            "answer_mode": self.answer_mode.value,
            "should_narrate": self.should_narrate,
            "blocked_reason": self.blocked_reason,
        }
