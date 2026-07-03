"""Seleção da evidência estruturada enviada por e-mail."""

from __future__ import annotations

from collections.abc import Mapping

from orion_mcp_v3.contracts.evidence_block import EvidenceBlock


def structured_email_evidence_from(evidence: EvidenceBlock | None) -> str | None:
    """Prefere texto completo (``full_section_detail`` / ``full_summary``) quando escopado para chat."""
    return analytical_direct_reply_from(evidence)


def analytical_direct_reply_from(evidence: EvidenceBlock | None) -> str | None:
    """Texto de resposta directa no caminho analítico (sem narrador LLM)."""
    if evidence is None:
        return None
    supporting = evidence.supporting_data or {}
    for key in ("direct_answer", "direct_answer_set"):
        payload = supporting.get(key)
        if isinstance(payload, Mapping):
            for field in ("full_section_detail", "full_summary"):
                full = payload.get(field)
                if isinstance(full, str) and full.strip():
                    return full.strip()
    summary = (evidence.summary or "").strip()
    return summary or None
