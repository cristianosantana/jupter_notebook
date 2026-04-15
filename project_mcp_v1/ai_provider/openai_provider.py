import time
from typing import Any, List, Dict

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.agent_trace import (
    get_openai_chat_stats,
    get_trace_llm_phase,
    get_trace_logger,
)
from app.config import get_settings
from app.orchestrator_analysis import analise
from app.orchestrator_llm_budget import (
    degraded_llm_assistant_message,
    llm_budget_try_consume,
)
from ai_provider.base import ModelProvider
from ai_provider.openai_chat_sanitize import sanitize_openai_chat_messages


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
        tout = float(settings.openai_http_timeout_seconds)
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key or None,
            timeout=tout,
        )
        self.model = settings.openai_model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: Any | None = None,
        model_override: str | None = None,
    ) -> Dict[str, Any]:

        safe_messages = sanitize_openai_chat_messages(messages)
        if not llm_budget_try_consume():
            tr0 = get_trace_logger()
            if tr0:
                tr0.record(
                    "llm.skipped_budget",
                    model=(model_override or "").strip() or self.model,
                    llm_phase=get_trace_llm_phase(),
                )
            analise(
                "openai_chat_bloqueado_orçamento_llm",
                modelo=(model_override or "").strip() or self.model,
                fase_llm=get_trace_llm_phase(),
            )
            return degraded_llm_assistant_message()
        kwargs: Dict[str, Any] = {
            "model": (model_override or "").strip() or self.model,
            "messages": safe_messages,
        }
        if tools:
            kwargs["tools"] = _tools_for_openai_api(tools)
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        stats = get_openai_chat_stats()
        call_idx = stats.begin_request() if stats else None

        tr = get_trace_logger()
        llm_phase = get_trace_llm_phase()
        analise(
            "openai_chat_início",
            modelo=kwargs["model"],
            fase_llm=llm_phase,
            indice_chamada=call_idx,
            n_mensagens=len(safe_messages),
            com_tools=bool(tools),
        )
        if tr:
            tr.record(
                "llm.request",
                model=kwargs["model"],
                messages=safe_messages,
                tools=tools,
                tool_choice=tool_choice,
                llm_phase=llm_phase,
                openai_call_index=call_idx,
            )

        t0 = time.monotonic()
        response = await self.client.chat.completions.create(**kwargs)
        elapsed = time.monotonic() - t0
        out = _normalized_assistant_message(response)
        if stats:
            stats.complete_response(llm_phase, elapsed)
        if tr:
            tr.record(
                "llm.response",
                model=response.model,
                assistant_message=out,
                llm_phase=llm_phase,
                openai_call_index=call_idx,
            )
        analise(
            "openai_chat_fim",
            modelo=response.model,
            fase_llm=llm_phase,
            duração_s=round(elapsed, 4),
            tem_tool_calls=bool(out.get("tool_calls")),
            content_preview=str(out.get("content") or "")[:240],
        )
        return out

    async def embed_texts(self, inputs: List[str]) -> List[List[float]]:
        """Embeddings OpenAI (histórico semântico / kNN)."""
        settings = get_settings()
        model = (settings.context_embedding_model or "text-embedding-3-small").strip()
        safe: List[str] = []
        for s in inputs:
            if not isinstance(s, str):
                safe.append("")
            else:
                safe.append(s[:50000])
        if not safe:
            return []
        resp = await self.client.embeddings.create(model=model, input=safe)
        return [list(d.embedding) for d in resp.data]
