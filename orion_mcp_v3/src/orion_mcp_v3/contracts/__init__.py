"""Contratos semânticos: tipos formais partilhados (ex.: blocos de contexto)."""

from orion_mcp_v3.contracts.cognitive_plan import (
    AttentionProfile,
    CognitivePlan,
    IntentType,
)
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan

__all__ = [
    "AnalyticalDigest",
    "AttentionProfile",
    "CognitivePlan",
    "ContextBlock",
    "ContextRole",
    "ContextSource",
    "IntentType",
    "SemanticQueryPlan",
    "RetrievalStrategy",
]
