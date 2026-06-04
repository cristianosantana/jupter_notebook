"""Gate de período para perguntas analíticas com referência anafórica."""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.runtime.temporal_reference import has_temporal_anaphora


@dataclass(frozen=True, slots=True)
class PeriodAdequacyDecision:
    resolved: bool
    plan: CognitivePlan
    date_from: str | None = None
    date_to: str | None = None
    inherited_from: str | None = None
    blocked_reason: str | None = None

    @property
    def should_block(self) -> bool:
        return self.blocked_reason is not None

    def as_trace(self) -> dict[str, Any]:
        return {
            "resolved": self.resolved,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "inherited_from": self.inherited_from,
            "blocked_reason": self.blocked_reason,
        }


def resolve_period_adequacy(
    message: str,
    plan: CognitivePlan,
    *,
    last_evidence: EvidenceBlock | None = None,
) -> PeriodAdequacyDecision:
    """Resolve ou bloqueia perguntas como "nesse período" sem `time_scope` explícito."""
    if not _has_period_anaphora(message):
        return PeriodAdequacyDecision(resolved=True, plan=plan)
    if plan.time_scope:
        return PeriodAdequacyDecision(resolved=True, plan=plan)

    inherited = _period_from_evidence(last_evidence)
    if inherited is None:
        return PeriodAdequacyDecision(
            resolved=False,
            plan=plan,
            blocked_reason="missing_period_context",
        )

    date_from, date_to = inherited
    hints = dict(plan.hints or {})
    signals = dict(hints.get("signals") or {}) if isinstance(hints.get("signals"), Mapping) else {}
    signals["recall"] = True
    signals["inherits_period"] = True
    hints.update(
        {
            "date_from": date_from,
            "date_to": date_to,
            "period_grain": "month" if date_from[:7] == date_to[:7] else "day",
            "period_source": "inherited_last_analytical_evidence",
            "inherits_period": True,
            "signals": signals,
            "explicit_period": {"date_from": date_from, "date_to": date_to},
        }
    )
    updated = replace(
        plan,
        time_scope=f"{date_from}/{date_to}",
        needs_temporal_context=True,
        hints=hints,
    )
    return PeriodAdequacyDecision(
        resolved=True,
        plan=updated,
        date_from=date_from,
        date_to=date_to,
        inherited_from="last_analytical_evidence",
    )


def _has_period_anaphora(message: str) -> bool:
    return has_temporal_anaphora(message)


def _period_from_evidence(evidence: EvidenceBlock | None) -> tuple[str, str] | None:
    if evidence is None:
        return None
    for row in _direct_answer_rows(evidence):
        period = str(row.get("periodo") or "").strip()
        bounds = _period_bounds(period)
        if bounds is not None:
            return bounds
    return None


def _direct_answer_rows(evidence: EvidenceBlock) -> Sequence[Mapping[str, Any]]:
    direct = evidence.supporting_data.get("direct_answer") if evidence.supporting_data else None
    if not isinstance(direct, Mapping):
        return ()
    rows = direct.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return ()
    return tuple(row for row in rows if isinstance(row, Mapping))


def _period_bounds(period: str) -> tuple[str, str] | None:
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", period):
        return period, period
    if re.fullmatch(r"20\d{2}-\d{2}", period):
        year, month = (int(part) for part in period.split("-"))
        last_day = calendar.monthrange(year, month)[1]
        return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"
    return None

