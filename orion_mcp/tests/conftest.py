"""
Isola testes do `.env` do repositório: evita ORION_ENV=production (re-lança erro de Postgres)
e credenciais OpenAI que mudam o comportamento do `build_llm`.
"""
from __future__ import annotations

import os

# Deve executar antes de qualquer `get_settings()` / `create_app()`.
os.environ["ORION_ENV"] = "development"
os.environ["ORION_DB_REQUIRED"] = "false"
os.environ["ORION_ENABLE_LONG_MEMORY"] = "false"
os.environ.pop("ORION_OPENAI_API_KEY", None)
# Valor vazio costuma ser ignorado pelo pydantic-settings e cair no default; usar URL inválida
# força `create_pool` a falhar de forma controlada e devolver None em desenvolvimento.
os.environ["ORION_DATABASE_URL"] = "postgresql://__orion_test__:__orion_test__@127.0.0.1:1/__none__"
# Não herdar parada de depuração LLM do `.env` do repositório (sobrepõe ficheiro).
os.environ["ORION_LLM_HALT_BEFORE_CHAT"] = "false"
os.environ["ORION_ORCHESTRATOR_CHAT_TRACE"] = "false"
# Tetos LLM unificados: não herdar do `.env` do repo (valores imprevisíveis nos testes).
for _k in (
    "ORION_LLM_PROMPT_TOKEN_BUDGET",
    "ORION_TOOL_LLM_SUMMARY_MAX_CHARS",
    "ORION_LLM_TOOL_CONTEXT_CHARS",
    "ORION_LLM_COMPLETION_MAX_TOKENS",
    "ORION_LLM_INSIGHTS_MAX_TOKENS",
    "ORION_LLM_CONTEXT_MAX_CHARS",
):
    os.environ.pop(_k, None)

from orion_mcp.core.config.settings import get_settings

get_settings.cache_clear()
