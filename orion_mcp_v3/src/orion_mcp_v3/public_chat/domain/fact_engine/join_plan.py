"""Plano de join entre memórias por período."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemorySourceRequirement:
    theme_slug: str
    fact_keys: tuple[str, ...]
    required: bool = True

    def as_mapping(self) -> dict[str, object]:
        return {
            "theme_slug": self.theme_slug,
            "fact_keys": list(self.fact_keys),
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class MemoryJoinPlan:
    period: str
    required_sources: tuple[MemorySourceRequirement, ...]
    join_keys: tuple[str, ...] = ("period",)

    def as_mapping(self) -> dict[str, object]:
        return {
            "period": self.period,
            "required_sources": [item.as_mapping() for item in self.required_sources],
            "join_keys": list(self.join_keys),
        }
