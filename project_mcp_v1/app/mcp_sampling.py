"""Callback MCP sampling/createMessage → OpenAI chat completions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import mcp.types as types
from mcp.shared.context import RequestContext  # pyright: ignore[reportMissingImports]

from app.agent_trace import get_trace_logger

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
        tr = get_trace_logger()
        oai_messages: list[dict[str, str]] = []
        if params.systemPrompt:
            oai_messages.append({"role": "system", "content": params.systemPrompt})
        for m in params.messages:
            oai_messages.append(
                {"role": m.role, "content": _sampling_content_to_text(m.content)}
            )
        total_chars = sum(len(m.get("content") or "") for m in oai_messages)
        if tr:
            tr.record(
                "mcp.sampling.request",
                llm_phase="mcp_sampling",
                system_prompt=params.systemPrompt,
                max_tokens=params.maxTokens,
                temperature=params.temperature,
                messages=oai_messages,
                message_count=len(oai_messages),
                total_chars=total_chars,
            )
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=oai_messages,
                max_tokens=params.maxTokens,
                temperature=params.temperature,
            )
            choice = resp.choices[0].message
            text = choice.content or ""
            msg = types.CreateMessageResult(
                role="assistant",
                content=types.TextContent(type="text", text=text),
                model=resp.model or model,
                stopReason="endTurn",
            )
            if tr:
                tr.record(
                    "mcp.sampling.response",
                    llm_phase="mcp_sampling",
                    model=resp.model or model,
                    text=text,
                    text_chars=len(text),
                    stop_reason="endTurn",
                )
            return msg
        except Exception as e:
            if tr:
                tr.record("mcp.sampling.error", llm_phase="mcp_sampling", error=str(e))
            return types.ErrorData(
                code=types.INVALID_REQUEST,
                message=f"sampling OpenAI falhou: {e}",
            )

    return sampling_callback
