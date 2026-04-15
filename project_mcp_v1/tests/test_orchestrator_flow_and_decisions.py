"""Testes mínimos: modo de fluxo A/B e decisões de pipelines."""

from __future__ import annotations

import pytest

from app import orchestrator_flow as of
from app.config import Settings
from app.conversation_state import ConversationStateV1
from app.orchestrator_decisions import decide_next_action, should_run_post_pipelines


def test_resolve_flow_mode_from_settings():
    s = Settings.model_construct(orchestrator_flow_mode="fast_skeleton")
    assert of.resolve_orchestrator_flow_mode(s) == "fast_skeleton"
    s2 = Settings.model_construct(orchestrator_flow_mode="legacy")
    assert of.resolve_orchestrator_flow_mode(s2) == "legacy"


def test_resolve_flow_mode_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(of, "ORCHESTRATOR_FLOW_OVERRIDE", "fast_skeleton")
    s = Settings.model_construct(orchestrator_flow_mode="legacy")
    assert of.resolve_orchestrator_flow_mode(s) == "fast_skeleton"
    monkeypatch.setattr(of, "ORCHESTRATOR_FLOW_OVERRIDE", None)


def test_should_run_post_pipelines_heuristic_low():
    st = Settings.model_construct(orchestrator_post_pipelines_mode="heuristic")
    conv = ConversationStateV1(complexity="low")
    flags = should_run_post_pipelines(st, conv, flow_mode="legacy")
    assert flags == {"critique": False, "formatador": False, "f3": False}


def test_should_run_post_pipelines_fast_skeleton_always_off():
    st = Settings.model_construct(orchestrator_post_pipelines_mode="always")
    conv = ConversationStateV1(complexity="high")
    flags = should_run_post_pipelines(st, conv, flow_mode="fast_skeleton")
    assert flags == {"critique": False, "formatador": False, "f3": False}


def test_decide_next_action_skip():
    st = Settings.model_construct(orchestrator_post_pipelines_mode="heuristic")
    conv = ConversationStateV1(complexity="low")
    assert decide_next_action(st, conv, flow_mode="legacy") == "SKIP_POST_PIPELINES"


def test_parse_fast_skeleton_plan_json():
    from app.orchestrator import ModularOrchestrator

    raw = '{"planned_tools":[{"name":"x","arguments":{"a":1}}]}'
    got = ModularOrchestrator._parse_fast_skeleton_plan_json(None, raw)
    assert got == [{"name": "x", "arguments": {"a": 1}}]
