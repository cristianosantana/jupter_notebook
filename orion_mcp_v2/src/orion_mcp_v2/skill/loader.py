from __future__ import annotations

import logging
from pathlib import Path

import yaml

from orion_mcp_v2.skill.models import SkillSpec

_logger = logging.getLogger(__name__)


def skills_dir() -> Path:
    return Path(__file__).resolve().parent / "skills"


class SkillRegistry:
    def __init__(self, specs: dict[str, SkillSpec]):
        self._specs = specs

    def get(self, name: str) -> SkillSpec:
        if name not in self._specs:
            raise KeyError(f"skill não registada: {name}")
        return self._specs[name]


def load_all_skills() -> SkillRegistry:
    reg: dict[str, SkillSpec] = {}
    for path in sorted(skills_dir().glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: YAML inválido")
        spec = SkillSpec.model_validate(raw)
        reg[spec.name] = spec
        _logger.debug("skill_loaded", extra={"name": spec.name})
    if not reg:
        raise RuntimeError(f"nenhuma skill em {skills_dir()}")
    return SkillRegistry(reg)
