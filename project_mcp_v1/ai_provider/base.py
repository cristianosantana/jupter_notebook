from abc import ABC, abstractmethod
from typing import Any, List, Dict

class ModelProvider(ABC):

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: Any | None = None,
    ) -> Dict[str, Any]:
        """
        Recebe mensagens e opcionalmente ferramentas.
        Retorna mensagem do assistente: role, content (str), tool_calls opcional.
        """
        pass