from abc import ABC, abstractmethod
from typing import List, Dict, Any

class ModelProvider(ABC):

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """
        Recebe mensagens e opcionalmente ferramentas.
        Retorna mensagem do assistente: role, content (str), tool_calls opcional.
        """
        pass