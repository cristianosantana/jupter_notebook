from __future__ import annotations

from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry


def test_public_chat_prompt_registry_loads_intent_prompt() -> None:
    registry = get_public_chat_prompt_registry()
    text = registry.get_text("public_chat_intent.system")
    assert "interpretador de intenção" in text
    assert registry.get("public_chat_intent.system").owner == "public_chat.intent_interpreter"
