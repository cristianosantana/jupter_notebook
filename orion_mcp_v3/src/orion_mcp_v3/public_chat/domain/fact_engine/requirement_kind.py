"""Taxonomia de requirements analíticos."""

from __future__ import annotations

from enum import Enum


class RequirementKind(str, Enum):
    LOOKUP = "lookup"
    DERIVED = "derived"
    COMPOSITION = "composition"
    COMPARISON = "comparison"
