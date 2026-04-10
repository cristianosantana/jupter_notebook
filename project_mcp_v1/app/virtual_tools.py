"""
Definições OpenAI de ferramentas virtuais executadas no host (não no MCP).
"""

from __future__ import annotations

from typing import Any

ANALYTICS_AGGREGATE_SESSION_TOOL_NAME = "analytics_aggregate_session"


def analytics_aggregate_session_openai_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": ANALYTICS_AGGREGATE_SESSION_TOOL_NAME,
            "description": (
                "Ferramenta do **host da API** (não aparece em tools/list do servidor MCP). "
                "Agrega um dataset obtido por `run_analytics_query` usando o campo `session_dataset_id` "
                "do JSON dessa resposta ou o id listado no digest «Datasets de analytics nesta sessão». "
                "**Nunca** peças `session_dataset_id` ao utilizador — lê-o do transcript/digest ou reexecuta "
                "`run_analytics_query` (mesmos argumentos) para o backend injectar o handle. "
                "Usa para Top N, somas, médias e participações. Se já tens um `session_dataset_id` válido "
                "para o mesmo período/query, **não** voltes a chamar `run_analytics_query` — agrega aqui."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_dataset_id": {
                        "type": "string",
                        "description": (
                            "Copiado do JSON da última run_analytics_query ou do digest de handles; "
                            "não peças ao utilizador."
                        ),
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Colunas para agrupar (devem existir nas linhas).",
                    },
                    "aggregations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {
                                    "type": "string",
                                    "description": "Coluna numérica (vazio para count de linhas se op=count).",
                                },
                                "op": {
                                    "type": "string",
                                    "enum": ["sum", "mean", "min", "max", "count"],
                                },
                            },
                            "required": ["op"],
                        },
                        "description": "Ex.: [{\"column\":\"qtd_os\",\"op\":\"sum\"}]",
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string"},
                                "op": {
                                    "type": "string",
                                    "enum": ["eq", "ne", "gt", "gte", "lt", "lte", "in"],
                                },
                                "value": {},
                            },
                            "required": ["column", "op"],
                        },
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Nome da coluna de saída (ex.: sum_qtd_os).",
                    },
                    "sort_dir": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "Por omissão: desc",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Limita o número de grupos após ordenação.",
                    },
                },
                "required": ["session_dataset_id", "group_by", "aggregations"],
            },
        },
    }
