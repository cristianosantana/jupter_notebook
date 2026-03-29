from typing import List, Dict, Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.config import get_settings
from ai_provider.base import ModelProvider


def _normalized_assistant_message(completion: ChatCompletion) -> Dict[str, Any]:
    msg = completion.choices[0].message
    out: Dict[str, Any] = {
        "role": msg.role,
        "content": msg.content if msg.content is not None else "",
    }
    if msg.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return out


def _tools_for_openai_api(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converte ferramentas no formato MCP (model_dump) para o formato da API OpenAI."""
    out: List[Dict[str, Any]] = []
    for t in tools:
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            out.append(t)
            continue
        name = t.get("name")
        if not name:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": t.get("description") or "",
                    "parameters": t.get("inputSchema")
                    or {"type": "object", "properties": {}},
                },
            }
        )
    return out


class OpenAIProvider(ModelProvider):

    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key or None,
        )
        self.model = settings.openai_model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = _tools_for_openai_api(tools)

        response = await self.client.chat.completions.create(**kwargs)

        return _normalized_assistant_message(response)
