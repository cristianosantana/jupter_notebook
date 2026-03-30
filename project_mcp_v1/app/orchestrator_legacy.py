import json
import time
from typing import Any

from ai_provider.base import ModelProvider
from mcp_client.client import Client
from mcp.types import CallToolResult, Tool  # pyright: ignore[reportMissingImports]


MAX_TOOL_ROUNDS = 24
MAX_HISTORY_MESSAGES = 20
# Mensagens mais antigas que isto (segundos) são removidas do início do histórico.
MAX_MESSAGE_AGE_SECONDS = 7200.0
TOOL_RESULT_PREVIEW_MAX = 500


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    s = str(raw).strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


def _mcp_result_to_text(result: CallToolResult) -> str:
    parts: list[str] = []
    for block in result.content:
        if block.type == "text":
            parts.append(block.text)
        else:
            parts.append(block.model_dump_json())
    text = "\n".join(parts) if parts else ""
    if result.isError:
        return text or "Erro ao executar a ferramenta."
    return text if text else "(sem conteúdo textual)"


class AgentOrchestrator:

    def __init__(
        self,
        model: ModelProvider,
        client: Client,
    ):
        self.model = model
        self.client = client
        self.messages: list[dict[str, Any]] = []
        self._message_times: list[float] = []
        self.tools: list[Tool] | None = None

    async def load_tools(self):
        tools = await self.client.list_tools()
        self.tools = tools

    def _append_message(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)
        self._message_times.append(time.time())

    def _prune_messages(self) -> None:
        """TTL no início, limite de tamanho, sem deixar mensagem 'tool' órfã no topo."""
        if len(self.messages) != len(self._message_times):
            self._message_times = [time.time() for _ in self.messages]

        now = time.time()
        cutoff = now - MAX_MESSAGE_AGE_SECONDS

        while self.messages and self._message_times and self._message_times[0] < cutoff:
            self.messages.pop(0)
            self._message_times.pop(0)

        while self.messages and self.messages[0].get("role") == "tool":
            self.messages.pop(0)
            self._message_times.pop(0)

        while len(self.messages) > MAX_HISTORY_MESSAGES:
            self.messages.pop(0)
            self._message_times.pop(0)

        while self.messages and self.messages[0].get("role") == "tool":
            self.messages.pop(0)
            self._message_times.pop(0)

    def _cap_messages(self) -> None:
        self._prune_messages()

    async def run(self, user_input: str) -> dict[str, Any]:
        """Reasoning loop: LLM → tool calls (MCP) → tool messages → até resposta final.

        Retorna ``{"assistant": {...}, "tools_used": [...]}`` para auditoria no cliente.
        """
        tools_used: list[dict[str, Any]] = []
        try:
            self._append_message({
                "role": "user",
                "content": user_input,
            })

            tools_payload = (
                [tool.model_dump() for tool in self.tools]
                if self.tools
                else None
            )

            step = 0
            while True:
                if step >= MAX_TOOL_ROUNDS:
                    raise RuntimeError(
                        f"Limite de {MAX_TOOL_ROUNDS} rodadas do agente excedido."
                    )
                step += 1

                response = await self.model.chat(
                    messages=self.messages,
                    tools=tools_payload,
                )

                tool_calls = response.get("tool_calls")
                if tool_calls:
                    response.setdefault(
                        "content",
                        "[Agent is requesting tool execution]",
                    )

                self._append_message(response)

                if not tool_calls:
                    return {"assistant": response, "tools_used": tools_used}

                requested = [
                    n
                    for tc in tool_calls
                    if (n := tc.get("function", {}).get("name"))
                ]
                print("🔧 Tool request detected:", requested)

                for tc in tool_calls:
                    tc_id = tc.get("id") or ""
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    if not name:
                        self._append_message({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": "Erro: nome da ferramenta ausente na resposta do modelo.",
                        })
                        tools_used.append({
                            "name": None,
                            "arguments": {},
                            "ok": False,
                            "error": "nome da ferramenta ausente",
                            "result_preview": None,
                        })
                        continue

                    print(f"⚙️ Executando tool: {name}")

                    args = _parse_tool_arguments(fn.get("arguments"))
                    try:
                        mcp_result = await self.client.call_tool(name, args)
                        content = _mcp_result_to_text(mcp_result)
                        preview = content[:TOOL_RESULT_PREVIEW_MAX]
                        if len(content) > TOOL_RESULT_PREVIEW_MAX:
                            preview += "…"
                        tools_used.append({
                            "name": name,
                            "arguments": args,
                            "ok": True,
                            "error": None,
                            "result_preview": preview,
                        })
                    except Exception as e:
                        content = f"Erro ao chamar a ferramenta: {e}"
                        tools_used.append({
                            "name": name,
                            "arguments": args,
                            "ok": False,
                            "error": str(e),
                            "result_preview": None,
                        })

                    self._append_message({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": content,
                    })
        finally:
            self._cap_messages()
