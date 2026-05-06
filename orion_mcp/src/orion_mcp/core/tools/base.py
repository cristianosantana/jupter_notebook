from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class Tool(ABC):
    name: str
    description: str = ""

    @property
    @abstractmethod
    def input_model(self) -> type[BaseModel]: ...

    def schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    @abstractmethod
    async def run(self, args: BaseModel) -> dict[str, Any]: ...
