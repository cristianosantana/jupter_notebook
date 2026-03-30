"""Callback MCP sampling/createMessage → OpenAI chat completions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import mcp.types as types
from mcp.shared.context import RequestContext  # pyright: ignore[reportMissingImports]

if TYPE_CHECKING:
    from openai import AsyncOpenAI


def _sampling_content_to_text(content: types.SamplingMessageContentBlock | list[types.SamplingMessageContentBlock]) -> str:
    blocks = content if isinstance(content, list) else [content]
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, types.TextContent):
            parts.append(b.text)
        else:
            parts.append(str(b.model_dump()))
    return "\n".join(parts)


def build_openai_sampling_callback(client: "AsyncOpenAI", model: str):
    """Devolve função compatível com ClientSession(sampling_callback=...)."""

    async def sampling_callback(
        context: RequestContext[Any, Any],
        params: types.CreateMessageRequestParams,
    ) -> types.CreateMessageResult | types.ErrorData:
        try:
            oai_messages: list[dict[str, str]] = []
            if params.systemPrompt:
                oai_messages.append({"role": "system", "content": params.systemPrompt})
            for m in params.messages:
                oai_messages.append(
                    {"role": m.role, "content": _sampling_content_to_text(m.content)}
                )

            resp = await client.chat.completions.create(
                model=model,
                messages=oai_messages,
                max_tokens=params.maxTokens,
                temperature=params.temperature,
            )
            choice = resp.choices[0].message
            text = choice.content or ""
            return types.CreateMessageResult(
                role="assistant",
                content=types.TextContent(type="text", text=text),
                model=resp.model or model,
                stopReason="endTurn",
            )
        except Exception as e:
            return types.ErrorData(
                code=types.INVALID_REQUEST,
                message=f"sampling OpenAI falhou: {e}",
            )

    return sampling_callback
