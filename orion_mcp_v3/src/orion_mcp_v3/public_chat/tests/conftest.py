"""Pytest: carrega env do módulo public_chat e do projeto."""

from __future__ import annotations

from pathlib import Path

_MODULE_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _MODULE_ROOT.parents[1]

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment, misc]

if load_dotenv is not None:
    load_dotenv(_MODULE_ROOT / ".env")
    load_dotenv(_PROJECT_ROOT / ".env")

import pytest

from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import shutdown_public_chat_file_logging


@pytest.fixture(autouse=True)
def _isolate_public_chat_pipeline_logs(monkeypatch) -> None:
    """Evita gravar JSONL no repo durante a suite de testes."""
    monkeypatch.setenv("PUBLIC_CHAT_PIPELINE_TRACE", "false")
    shutdown_public_chat_file_logging()
    yield
    shutdown_public_chat_file_logging()


def make_resolved_hit(hit, rule, *, fact_key: str, semantics_version: str = "v1"):
    """Helper de teste: ``ResolvedMemoryHit`` com ``resolution_trace`` montado no branch."""
    from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import ResolvedMemoryHit
    from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionRule, build_resolution_trace

    trace = build_resolution_trace(
        fact_key=fact_key,
        hit_origin_id=hit.origin_id,
        hit_context_key=hit.context_key,
        rule=rule,
        semantics_version=semantics_version,
    )
    return ResolvedMemoryHit(hit=hit, rule=rule, resolution_trace=trace)
