"""
Ferramentas virtuais de roteamento (não existem no MCP).

O Maestro só vê `MAESTRO_TOOLS_ONLY`; o orquestrador intercepta
`route_to_specialist` e faz handoff para o agente especializado.
"""

from typing import Any, Literal

SpecialistAgent = Literal["analise_os", "clusterizacao", "visualizador", "agregador", "projecoes"]

ROUTE_TO_SPECIALIST_TOOL_NAME = "route_to_specialist"

SPECIALIST_AGENTS: tuple[str, ...] = (
    "analise_os",
    "clusterizacao",
    "visualizador",
    "agregador",
    "projecoes",
)

MAESTRO_TOOLS_ONLY: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": ROUTE_TO_SPECIALIST_TOOL_NAME,
            "description": (
                "Obrigatório: escolhe exatamente um agente especializado para processar o pedido do utilizador. "
                "Não executa análises nem chama ferramentas de dados; apenas roteia."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": list(SPECIALIST_AGENTS),
                        "description": "Identificador do agente especializado.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Justificação breve da escolha (opcional).",
                    },
                },
                "required": ["agent"],
            },
        },
    }
]

# Tokens legados da skill (fallback se a API não devolver tool call)
FALLBACK_TOKENS: dict[str, SpecialistAgent] = {
    "ANALISE_OS": "analise_os",
    "CLUSTERIZACAO": "clusterizacao",
    "VISUALIZADOR": "visualizador",
    "AGREGADOR": "agregador",
    "PROJECOES": "projecoes",
}


def parse_route_arguments(raw: Any) -> SpecialistAgent:
    args = raw if isinstance(raw, dict) else {}
    agent = args.get("agent")
    if agent not in SPECIALIST_AGENTS:
        raise ValueError(f"agent inválido para roteamento: {agent!r}")
    return agent  # type: ignore[return-value]


def specialist_from_text_fallback(content: str) -> SpecialistAgent | None:
    upper = content.upper()
    for token, agent in FALLBACK_TOKENS.items():
        if token in upper:
            return agent
    return None
