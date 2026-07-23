"""Parâmetros OpenAI do Chat Público — max_tokens vs max_completion_tokens."""

from __future__ import annotations

from orion_mcp_v3.public_chat.infrastructure.llm.openai_provider import OpenAIPublicLLMProvider


def _provider(*, model: str, max_tokens: int = 1024) -> OpenAIPublicLLMProvider:
    provider = object.__new__(OpenAIPublicLLMProvider)
    provider._model = model
    provider._max_tokens = max_tokens
    provider._temperature = 0.3
    return provider


def test_gpt5_mini_uses_max_completion_tokens_and_omits_temperature() -> None:
    params = _provider(model="gpt-5-mini")._params({"max_tokens": 1024, "temperature": 0})
    assert params["model"] == "gpt-5-mini"
    assert params["max_completion_tokens"] == 8192
    assert "max_tokens" not in params
    assert "temperature" not in params


def test_gpt4o_mini_keeps_max_tokens_and_temperature() -> None:
    params = _provider(model="gpt-4o-mini")._params({"max_tokens": 512, "temperature": 0.2})
    assert params["max_tokens"] == 512
    assert params["temperature"] == 0.2
    assert "max_completion_tokens" not in params


def test_is_constrained_chat_model_prefixes() -> None:
    assert OpenAIPublicLLMProvider._is_constrained_chat_model("gpt-5-mini")
    assert OpenAIPublicLLMProvider._is_constrained_chat_model("o3-mini")
    assert not OpenAIPublicLLMProvider._is_constrained_chat_model("gpt-4o-mini")
