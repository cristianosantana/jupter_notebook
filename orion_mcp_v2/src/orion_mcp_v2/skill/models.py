from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SkillSpec(BaseModel):
    name: str
    model: str = "gpt-5-mini"
    max_tokens: int = 500
    system_prompt: str = Field(default="", description="Template; placeholders {question},{data_summary}, etc.")

    def render_system(self, **kwargs: Any) -> str:
        text = self.system_prompt
        for k, v in kwargs.items():
            text = text.replace("{" + k + "}", str(v))
        return text
