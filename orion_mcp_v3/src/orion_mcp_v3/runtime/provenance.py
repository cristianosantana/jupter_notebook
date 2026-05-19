"""Re-export de proveniência em ``contracts`` (compatibilidade com imports legados)."""

from orion_mcp_v3.contracts.provenance import (
    CoverageInfo,
    ProvenanceAnchor,
    merge_coverage_infos,
    merge_provenance_anchors,
)

__all__ = [
    "CoverageInfo",
    "ProvenanceAnchor",
    "merge_coverage_infos",
    "merge_provenance_anchors",
]
