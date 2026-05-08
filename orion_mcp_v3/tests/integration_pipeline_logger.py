"""Logger JSONL e serialização para testes de integração (sem mocks)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from orion_mcp_v3.contracts.cognitive_artifact import CognitiveArtifact
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.context_block import ContextBlock
from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan
from orion_mcp_v3.runtime.conflict_resolution import ConflictResolutionResult


def _json_fallback(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    return str(obj)


def context_block_snapshot(b: ContextBlock) -> dict[str, Any]:
    return {
        "text": b.text,
        "role": b.role.value,
        "source": b.source.value,
        "block_id": b.block_id,
        "metadata": dict(b.metadata),
        "relevance_score": b.relevance_score,
    }


def cognitive_plan_snapshot(cp: CognitivePlan) -> dict[str, Any]:
    return {
        "intent_type": cp.intent_type.value,
        "needs_memory": cp.needs_memory,
        "needs_analytics": cp.needs_analytics,
        "needs_comparison": cp.needs_comparison,
        "needs_temporal_context": cp.needs_temporal_context,
        "needs_baseline": cp.needs_baseline,
        "needs_trend_analysis": cp.needs_trend_analysis,
        "needs_entity_resolution": cp.needs_entity_resolution,
        "confidence": cp.confidence,
        "entities": list(cp.entities),
        "metrics": list(cp.metrics),
        "time_scope": cp.time_scope,
        "retrieval_strategy": cp.retrieval_strategy.value,
        "attention_profile": cp.attention_profile.value,
        "hints": dict(cp.hints),
    }


def cognitive_artifact_snapshot(a: CognitiveArtifact) -> dict[str, Any]:
    return {
        "kind": a.kind,
        "summary": dict(a.summary),
        "confidence": a.confidence,
        "coverage": {"labels": dict(a.coverage.labels), "notes": a.coverage.notes},
        "provenance": [
            {
                "artifact_id": p.artifact_id,
                "source": p.source,
                "lineage": list(p.lineage),
                "metadata": dict(p.metadata),
            }
            for p in a.provenance
        ],
    }


def semantic_query_plan_snapshot(p: SemanticQueryPlan) -> dict[str, Any]:
    return {
        "intent_slug": p.intent_slug,
        "strategy": p.strategy.value,
        "target_collections": list(p.target_collections),
        "hints": dict(p.hints),
        "correlation_id": p.correlation_id,
        "analytics_strategy": p.analytics_strategy.value if p.analytics_strategy else None,
    }


def conflict_resolution_snapshot(r: ConflictResolutionResult) -> dict[str, Any]:
    return {
        "blocks": [context_block_snapshot(b) for b in r.blocks],
        "dropped_ids": list(r.dropped_ids),
        "notes": r.notes,
    }


class JsonlPipelineLogger:
    """Uma linha JSON por passo — fácil de inspecionar com ``jq`` ou editor."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def start_run(self, *, utterance: str, extra: dict[str, Any] | None = None) -> None:
        header = {
            "step": "run_start",
            "input": {},
            "output": {
                "utterance": utterance,
                "utc_iso": datetime.now(timezone.utc).isoformat(),
                **(extra or {}),
            },
        }
        self._append(header)

    def step(self, step: str, *, input_data: Any = None, output_data: Any = None) -> None:
        self._append({"step": step, "input": input_data, "output": output_data})

    def _append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=_json_fallback)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def rows_for_json(rows: list[dict[str, Any]], *, limit: int = 50) -> list[dict[str, Any]]:
    """Normaliza valores não-JSON-native (ex.: ``Decimal``, ``datetime``) para logging."""
    raw = json.dumps(rows[:limit], default=str)
    return json.loads(raw)
