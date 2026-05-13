"""Contratos semânticos: tipos formais partilhados (ex.: blocos de contexto)."""

from orion_mcp_v3.contracts.cognitive_plan import (
    AttentionProfile,
    CognitivePlan,
    IntentType,
)
from orion_mcp_v3.contracts.cognitive_artifact import (
    CognitiveArtifact,
    artifact_provenance_anchor,
    heuristic_confidence_from_volume,
)
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.evidence_series_spec import EvidenceSeriesSpec
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy, RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.contracts.semantic_retrieval_plan import SemanticRetrievalPlan

__all__ = [
    "AnalyticalDigest",
    "EvidenceBlock",
    "EvidenceSeriesSpec",
    "AttentionProfile",
    "CognitivePlan",
    "CognitiveArtifact",
    "artifact_provenance_anchor",
    "heuristic_confidence_from_volume",
    "ContextBlock",
    "ContextRole",
    "ContextSource",
    "IntentType",
    "SemanticQueryPlan",
    "SemanticRetrievalPlan",
    "AnalyticsStrategy",
    "RetrievalStrategy",
]
