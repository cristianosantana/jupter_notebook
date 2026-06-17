"""Fingerprint do conhecimento remissivo usado numa resolução."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado


def build_knowledge_fingerprint_from_knowledge(knowledge: ConhecimentoRecuperado) -> str:
    return build_knowledge_fingerprint(
        validated_answers=[hit.validated_answer for hit in knowledge.hits],
        key_metrics=[dict(hit.key_metrics) for hit in knowledge.hits],
        essence_themes=[item.theme for item in knowledge.essence],
    )


def build_knowledge_fingerprint(
    *,
    validated_answers: Sequence[str] = (),
    key_metrics: Sequence[Mapping[str, Any]] = (),
    essence_themes: Sequence[str] = (),
) -> str:
    """Hash determinístico do conteúdo efetivo em ``memory_*``."""
    canonical = {
        "essence_themes": sorted(str(theme) for theme in essence_themes),
        "key_metrics": [_sorted_mapping(item) for item in key_metrics],
        "validated_answers": list(validated_answers),
    }
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sorted_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): data[key] for key in sorted(data.keys(), key=str)}
