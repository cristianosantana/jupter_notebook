from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field


class Skill(BaseModel):
    name: str
    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_skill_yaml(text: str) -> Skill:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("skill yaml must be a mapping")
    return Skill.model_validate(data)
