"""Runtime: eventos, proveniência e ciclo de vida do Orion v3 (Fase 0+)."""

from orion_mcp_v3.runtime.attention_policy import (
    AttentionPolicy,
    AttentionShares,
    ElasticFreeTierParams,
    elastic_free_tier_params,
    policy_shares,
)
from orion_mcp_v3.runtime.intent_resolver import (
    IntentResolver,
    map_attention_profile_to_policy,
)
from orion_mcp_v3.runtime.budget_allocator import allocate, estimate_tokens
from orion_mcp_v3.runtime.prompt_render import render_blocks_to_prompt
from orion_mcp_v3.runtime.context_builder import AnalyticalContextBuilder
from orion_mcp_v3.runtime.context_state import ContextState
from orion_mcp_v3.runtime.conflict_resolution import (
    ConflictResolutionResult,
    cap_system_blocks,
    resolve_duplicate_blocks,
)
from orion_mcp_v3.runtime.context_fusion import ContextFusion, ContextFusionResult
from orion_mcp_v3.runtime.decay import (
    apply_decay,
    apply_decay_to_sequence,
    apply_decay_with_clock,
    resolve_age_seconds,
)
from orion_mcp_v3.runtime.events import RuntimeEvent, RuntimeEventType
from orion_mcp_v3.runtime.drift_guard import DriftGuard, DriftReport, DriftSignal
from orion_mcp_v3.runtime.provenance import (
    CoverageInfo,
    ProvenanceAnchor,
    merge_coverage_infos,
    merge_provenance_anchors,
)

__all__ = [
    "allocate",
    "AnalyticalContextBuilder",
    "apply_decay",
    "apply_decay_to_sequence",
    "apply_decay_with_clock",
    "AttentionPolicy",
    "AttentionShares",
    "cap_system_blocks",
    "ConflictResolutionResult",
    "ContextFusion",
    "ContextFusionResult",
    "IntentResolver",
    "map_attention_profile_to_policy",
    "ContextState",
    "merge_coverage_infos",
    "merge_provenance_anchors",
    "CoverageInfo",
    "DriftGuard",
    "DriftReport",
    "DriftSignal",
    "ElasticFreeTierParams",
    "elastic_free_tier_params",
    "estimate_tokens",
    "render_blocks_to_prompt",
    "policy_shares",
    "resolve_age_seconds",
    "resolve_duplicate_blocks",
    "ProvenanceAnchor",
    "RuntimeEvent",
    "RuntimeEventType",
]
