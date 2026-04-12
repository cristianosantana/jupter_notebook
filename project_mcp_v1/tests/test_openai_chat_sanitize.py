"""``sanitize_openai_chat_messages`` (OpenAI chat grammar)."""

from __future__ import annotations

from ai_provider.openai_chat_sanitize import sanitize_openai_chat_messages


def test_drops_leading_tool() -> None:
    out = sanitize_openai_chat_messages(
        [
            {"role": "tool", "tool_call_id": "x", "content": "{}"},
            {"role": "user", "content": "hi"},
        ]
    )
    assert len(out) == 1 and out[0]["role"] == "user"


def test_drops_tool_after_user_without_assistant() -> None:
    out = sanitize_openai_chat_messages(
        [
            {"role": "user", "content": "q"},
            {"role": "tool", "tool_call_id": "a", "content": "{}"},
        ]
    )
    assert [m["role"] for m in out] == ["user"]


def test_drops_tool_after_assistant_without_tool_calls() -> None:
    out = sanitize_openai_chat_messages(
        [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "text only"},
            {"role": "tool", "tool_call_id": "a", "content": "{}"},
        ]
    )
    assert [m["role"] for m in out] == ["user", "assistant"]


def test_keeps_tool_after_assistant_with_tool_calls() -> None:
    out = sanitize_openai_chat_messages(
        [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "a", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "a", "content": "{}"},
        ]
    )
    assert [m["role"] for m in out] == ["user", "assistant", "tool"]


def test_keeps_multiple_tools_same_round() -> None:
    out = sanitize_openai_chat_messages(
        [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                    {"id": "2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "1", "content": "{}"},
            {"role": "tool", "tool_call_id": "2", "content": "{}"},
        ]
    )
    assert [m["role"] for m in out] == ["user", "assistant", "tool", "tool"]


def test_strips_empty_tool_calls_list() -> None:
    out = sanitize_openai_chat_messages(
        [
            {"role": "assistant", "content": "x", "tool_calls": []},
            {"role": "tool", "tool_call_id": "z", "content": "{}"},
        ]
    )
    assert "tool_calls" not in out[0]
    assert len(out) == 1


def test_strips_orch_keys() -> None:
    out = sanitize_openai_chat_messages(
        [{"role": "user", "content": "a", "_orch_anchor": True}]
    )
    assert "_orch_anchor" not in out[0]
