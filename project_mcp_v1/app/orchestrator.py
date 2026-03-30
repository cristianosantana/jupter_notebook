"""
Orquestrador Modular para Maestro de Agentes.

Implementa:
1. SkillLoader: Carrega SKILLs dinamicamente com YAML frontmatter
2. ModelRouter: Roteamento inteligente de modelo (Haiku → Sonnet → Opus)
3. ModularOrchestrator: Agent loop com decomposição de tasks
"""

import json
import time
import re
from pathlib import Path
from typing import Any, Literal
from dataclasses import dataclass

from ai_provider.base import ModelProvider
from app.routing_tools import (
    MAESTRO_TOOLS_ONLY,
    ROUTE_TO_SPECIALIST_TOOL_NAME,
    parse_route_arguments,
    specialist_from_text_fallback,
)
from mcp_client.client import Client
from mcp.types import CallToolResult, Tool  # pyright: ignore[reportMissingImports]

# Configurações
MAX_TOOL_ROUNDS = 24
MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_AGE_SECONDS = 7200.0
TOOL_RESULT_PREVIEW_MAX = 500

# Enums
AgentType = Literal["maestro", "analise_os", "clusterizacao", "visualizador", "agregador", "projecoes"]
ModelType = Literal["haiku", "sonnet", "opus"]


@dataclass
class SkillMetadata:
    """Metadados extraídos do frontmatter YAML do SKILL."""
    model: ModelType
    context_budget: int
    max_tokens: int
    temperature: float
    role: str
    agent_type: AgentType | None = None


class SkillLoader:
    """Carrega SKILLs .md com YAML frontmatter e os cacheiza."""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._cache: dict[str, tuple[str, SkillMetadata]] = {}

    def load_skill(self, agent_type: AgentType) -> tuple[str, SkillMetadata]:
        """Carrega SKILL para agente, retorna (conteúdo, metadata)."""
        if agent_type in self._cache:
            return self._cache[agent_type]

        skill_file = self.skills_dir / f"{agent_type}.md"
        if not skill_file.is_file():
            raise FileNotFoundError(f"SKILL not found: {skill_file}")

        content = skill_file.read_text(encoding="utf-8")
        skill_text, metadata = self._parse_skill(content)

        self._cache[agent_type] = (skill_text, metadata)
        return skill_text, metadata

    @staticmethod
    def _parse_skill(content: str) -> tuple[str, SkillMetadata]:
        """Extrai YAML frontmatter e retorna (skill_text, metadata)."""
        # Padrão: --- \n yaml \n --- \n conteúdo
        match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
        if not match:
            raise ValueError("SKILL deve conter YAML frontmatter entre ---")

        yaml_str, skill_body = match.groups()

        # Parse YAML simplificado (evita dependência extra)
        metadata = SkillLoader._parse_yaml(yaml_str)
        return skill_body.strip(), metadata

    @staticmethod
    def _parse_yaml(yaml_str: str) -> SkillMetadata:
        """Parse simplificado de YAML frontmatter."""
        lines = yaml_str.strip().split("\n")
        data = {}
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                # Converte tipos básicos
                if value.isdigit():
                    data[key] = int(value)
                elif value.replace(".", "", 1).isdigit():
                    data[key] = float(value)
                else:
                    data[key] = value

        return SkillMetadata(
            model=data.get("model", "sonnet").split("-")[1].lower(),  # Extract "sonnet" from "claude-sonnet-4.6"
            context_budget=data.get("context_budget", 100000),
            max_tokens=data.get("max_tokens", 2000),
            temperature=data.get("temperature", 0.5),
            role=data.get("role", "analyst"),
            agent_type=data.get("agent_type"),
        )


class ModelRouter:
    """Mapeia AgentType → Modelo baseado em complexidade."""

    ROUTING_TABLE = {
        "maestro": "haiku",           # Rápido + barato (roteamento)
        "analise_os": "sonnet",       # Balanceado
        "clusterizacao": "opus",      # Complexo (machine learning)
        "visualizador": "sonnet",     # Visualização
        "agregador": "haiku",         # Síntese simples
        "projecoes": "opus",          # Complexo (forecasting)
    }

    @staticmethod
    def get_model(agent_type: AgentType) -> ModelType:
        """Retorna modelo ideal para agente."""
        return ModelRouter.ROUTING_TABLE.get(agent_type, "sonnet")


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


def _messages_with_skill(
    skill: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not skill:
        return list(messages)
    out = list(messages)
    if out and out[0].get("role") == "system":
        existing = (out[0].get("content") or "").strip()
        merged = f"{skill}\n\n{existing}".strip() if existing else skill
        out[0] = {**out[0], "content": merged}
    else:
        out.insert(0, {"role": "system", "content": skill})
    return out


class ModularOrchestrator:
    """
    Orquestrador Modular com suporte a múltiplos agentes especializados.

    Flow:
    1. Usuário envia pergunta ao Maestro
    2. Maestro roteía para agente correto (analise_os, clusterizacao, etc.)
    3. Agente especializado executa com seu SKILL e ferramentas
    4. Resultado retorna ao usuário
    """

    def __init__(
        self,
        model: ModelProvider,
        client: Client,
        skills_dir: Path | None = None,
    ):
        self.model = model
        self.client = client
        self.messages: list[dict[str, Any]] = []
        self._message_times: list[float] = []
        self.tools: list[Tool] | None = None

        # Inicializa SkillLoader
        if skills_dir is None:
            skills_dir = Path(__file__).resolve().parent / "skills"
        self.skill_loader = SkillLoader(skills_dir)
        self.current_agent: AgentType = "maestro"
        self.current_skill: str = ""
        self.current_metadata: SkillMetadata | None = None

    async def load_tools(self):
        """Carrega ferramentas do MCP server."""
        tools = await self.client.list_tools()
        self.tools = tools

    async def set_agent(self, agent_type: AgentType) -> None:
        """Muda agente ativo, carregando seu SKILL."""
        if agent_type == self.current_agent:
            return  # Já carregado

        print(f"🔄 Switching agent: {self.current_agent} → {agent_type}")
        self.current_skill, self.current_metadata = self.skill_loader.load_skill(agent_type)
        self.current_agent = agent_type
        self.messages.clear()  # Limpa histórico ao trocar agente
        self._message_times.clear()

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

    async def run(self, user_input: str, target_agent: AgentType | None = None) -> dict[str, Any]:
        """
        Executa agent loop.

        Se ``target_agent`` for None, o Maestro corre primeiro (só tool virtual
        ``route_to_specialist``), faz handoff para o especialista e só então
        expõe ferramentas MCP.
        """
        auto_route = target_agent is None
        tools_used: list[dict[str, Any]] = []

        if auto_route:
            await self.set_agent("maestro")
        else:
            await self.set_agent(target_agent)

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

            if auto_route:
                maestro_tool_choice: dict[str, Any] = {
                    "type": "function",
                    "function": {"name": ROUTE_TO_SPECIALIST_TOOL_NAME},
                }
                while self.current_agent == "maestro":
                    step += 1
                    if step > MAX_TOOL_ROUNDS:
                        raise RuntimeError(
                            f"Limite de {MAX_TOOL_ROUNDS} rodadas do agente excedido."
                        )

                    response = await self.model.chat(
                        messages=_messages_with_skill(self.current_skill, self.messages),
                        tools=MAESTRO_TOOLS_ONLY,
                        tool_choice=maestro_tool_choice,
                    )
                    tool_calls = response.get("tool_calls") or []

                    routed = False
                    for tc in tool_calls:
                        fn = tc.get("function") or {}
                        name = fn.get("name")
                        if name != ROUTE_TO_SPECIALIST_TOOL_NAME:
                            continue
                        args = _parse_tool_arguments(fn.get("arguments"))
                        try:
                            specialist = parse_route_arguments(args)
                        except ValueError as e:
                            return {
                                "assistant": {
                                    "role": "assistant",
                                    "content": (
                                        "Não foi possível rotear o pedido: argumentos inválidos na "
                                        f"ferramenta de roteamento ({e})."
                                    ),
                                },
                                "tools_used": tools_used,
                                "agent": self.current_agent,
                            }
                        tools_used.append({
                            "name": ROUTE_TO_SPECIALIST_TOOL_NAME,
                            "arguments": args,
                            "ok": True,
                            "error": None,
                            "result_preview": f"handoff → {specialist}",
                        })
                        print(f"🎯 Handoff: maestro → {specialist}")
                        await self.set_agent(specialist)
                        self._append_message({
                            "role": "user",
                            "content": user_input,
                        })
                        routed = True
                        break

                    if routed:
                        break

                    if not tool_calls:
                        fb = specialist_from_text_fallback(response.get("content") or "")
                        if fb is not None:
                            tools_used.append({
                                "name": ROUTE_TO_SPECIALIST_TOOL_NAME,
                                "arguments": {"agent": fb, "reason": "fallback_text_token"},
                                "ok": True,
                                "error": None,
                                "result_preview": f"handoff (fallback texto) → {fb}",
                            })
                            print(f"🎯 Handoff (fallback texto): maestro → {fb}")
                            await self.set_agent(fb)
                            self._append_message({
                                "role": "user",
                                "content": user_input,
                            })
                            break
                        return {
                            "assistant": {
                                "role": "assistant",
                                "content": (
                                    "Não foi possível determinar o agente especializado. "
                                    "Reformula a pergunta ou indica ``target_agent`` no pedido HTTP."
                                ),
                            },
                            "tools_used": tools_used,
                            "agent": "maestro",
                        }

                    return {
                        "assistant": {
                            "role": "assistant",
                            "content": (
                                "Resposta inesperada do Maestro (sem roteamento válido). "
                                "Tenta de novo ou usa ``target_agent`` explícito."
                            ),
                        },
                        "tools_used": tools_used,
                        "agent": "maestro",
                    }

            while True:
                step += 1
                if step > MAX_TOOL_ROUNDS:
                    raise RuntimeError(
                        f"Limite de {MAX_TOOL_ROUNDS} rodadas do agente excedido."
                    )

                response = await self.model.chat(
                    messages=_messages_with_skill(self.current_skill, self.messages),
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
                    return {"assistant": response, "tools_used": tools_used, "agent": self.current_agent}

                requested = [
                    n
                    for tc in tool_calls
                    if (n := tc.get("function", {}).get("name"))
                ]
                print(f"🔧 [{self.current_agent}] Tool request: {requested}")

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

                    args = _parse_tool_arguments(fn.get("arguments"))

                    if name == ROUTE_TO_SPECIALIST_TOOL_NAME and self.current_agent != "maestro":
                        msg = (
                            "Roteamento entre agentes só é feito pelo Maestro (pedido HTTP sem "
                            "`target_agent`). Como agente especialista, não podes usar "
                            "`route_to_specialist`. Resolve o pedido com as ferramentas MCP "
                            "disponíveis ou explica ao utilizador o que não consegues fazer "
                            "neste papel."
                        )
                        print(
                            f"⛔ [{self.current_agent}] Bloqueado: {name} "
                            "(apenas Maestro pode rotear)"
                        )
                        tools_used.append({
                            "name": name,
                            "arguments": args,
                            "ok": False,
                            "error": "route_to_specialist não permitido fora do Maestro",
                            "result_preview": None,
                        })
                        self._append_message({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": msg,
                        })
                        continue

                    print(f"⚙️  [{self.current_agent}] Executing: {name}")

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
