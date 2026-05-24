"""Runtime: eventos, proveniência e ciclo de vida do Orion v3 (Fase 0+)."""

from orion_mcp_v3.runtime.attention_policy import (
    AttentionPolicy,
    AttentionPolicyDefinition,
    AttentionShares,
    ElasticFreeTierParams,
    elastic_free_tier_params,
    policy_definition,
    policy_shares,
)
from orion_mcp_v3.runtime.intent_resolver import (
    IntentResolver,
    map_attention_profile_to_policy,
)
from orion_mcp_v3.runtime.analytical_system_prompt import build_analytical_system_block
from orion_mcp_v3.runtime.analytical_context_policy import (
    AnalyticalContextDecision,
    AnalyticalContextFilterResult,
    AnalyticalContextIsolationPolicy,
)
from orion_mcp_v3.runtime.analytical_signature import (
    AnalyticalSignature,
    signature_from_evidence,
    signature_from_metadata,
    signature_from_plan,
    signatures_compatible,
)
from orion_mcp_v3.runtime.budget_allocator import AllocationResult, allocate, estimate_tokens
from orion_mcp_v3.runtime.prompt_render import render_blocks_to_prompt
from orion_mcp_v3.runtime.context_builder import AnalyticalContextBuilder
from orion_mcp_v3.runtime.context_state import CognitivePhase, ContextState
from orion_mcp_v3.runtime.conflict_resolution import (
    ConflictResolutionResult,
    ConflictStrategy,
    cap_system_blocks,
    resolve_cognitive_conflicts,
    resolve_duplicate_blocks,
    resolve_memory_digest_redundancy,
    resolve_redundant_analytics,
    resolve_repeated_user_turns,
    resolve_semantic_duplicates,
)
from orion_mcp_v3.runtime.cognitive_orchestrator import (
    CognitiveOrchestrationResult,
    CognitiveOrchestrator,
    build_fusion_layers,
)
from orion_mcp_v3.runtime.context_fusion import (
    ContextFusion,
    ContextFusionResult,
    FusionSource,
    classify_fusion_source,
)
from orion_mcp_v3.runtime.scheduler import (
    SchedulerProfile,
    SchedulerScoreBreakdown,
    composite_score,
    compute_score_breakdown,
    schedule_blocks,
    scheduler_profile_from_attention,
)
from orion_mcp_v3.runtime.decay import (
    apply_decay,
    apply_decay_to_sequence,
    apply_decay_with_clock,
    resolve_age_seconds,
)
from orion_mcp_v3.runtime.narrator import CognitiveNarrator, NarrationResult
from orion_mcp_v3.runtime.session_manager import Session, SessionManager
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
    "AllocationResult",
    "AnalyticalContextDecision",
    "AnalyticalContextFilterResult",
    "AnalyticalContextIsolationPolicy",
    "AnalyticalSignature",
    "AnalyticalContextBuilder",
    "apply_decay",
    "apply_decay_to_sequence",
    "apply_decay_with_clock",
    "AttentionPolicy",
    "AttentionPolicyDefinition",
    "AttentionShares",
    "CognitivePhase",
    "cap_system_blocks",
    "CognitiveNarrator",
    "CognitiveOrchestrationResult",
    "CognitiveOrchestrator",
    "ConflictResolutionResult",
    "ConflictStrategy",
    "build_fusion_layers",
    "build_analytical_system_block",
    "classify_fusion_source",
    "ContextFusion",
    "ContextFusionResult",
    "FusionSource",
    "IntentResolver",
    "map_attention_profile_to_policy",
    "NarrationResult",
    "ContextState",
    "policy_definition",
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
    "signature_from_evidence",
    "signature_from_metadata",
    "signature_from_plan",
    "signatures_compatible",
    "policy_shares",
    "resolve_age_seconds",
    "resolve_cognitive_conflicts",
    "resolve_duplicate_blocks",
    "resolve_memory_digest_redundancy",
    "resolve_redundant_analytics",
    "resolve_repeated_user_turns",
    "resolve_semantic_duplicates",
    "ProvenanceAnchor",
    "RuntimeEvent",
    "RuntimeEventType",
    "Session",
    "SessionManager",
    "SchedulerProfile",
    "SchedulerScoreBreakdown",
    "composite_score",
    "compute_score_breakdown",
    "schedule_blocks",
    "scheduler_profile_from_attention",
]
