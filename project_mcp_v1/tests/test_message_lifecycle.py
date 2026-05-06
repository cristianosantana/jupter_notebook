"""Poda por segmentos (``app.message_lifecycle``)."""

from __future__ import annotations

from app.message_lifecycle import (
    first_prunable_segment_len,
    pop_first_segment,
    strip_leading_orphan_tools,
)


def test_strip_leading_orphan_tools() -> None:
    msgs = [
        {"role": "tool", "content": "x"},
        {"role": "tool", "content": "y"},
        {"role": "user", "content": "hi"},
    ]
    times = [1.0, 2.0, 3.0]
    strip_leading_orphan_tools(msgs, times)
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    assert times == [3.0]


def test_first_segment_len_leading_tools() -> None:
    msgs = [{"role": "tool"}, {"role": "tool"}, {"role": "user"}]
    assert first_prunable_segment_len(msgs) == 2


def test_first_segment_len_user_turn_with_tools() -> None:
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a", "content": "x" * 500},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "q2"},
    ]
    assert first_prunable_segment_len(msgs) == 4


def test_first_segment_anchor_blocks() -> None:
    msgs = [{"role": "user", "_orch_anchor": True, "content": "a"}]
    assert first_prunable_segment_len(msgs) == 0


def test_pop_first_segment_removes_full_turn() -> None:
    msgs = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "c", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": "{}"},
        {"role": "user", "content": "new"},
    ]
    times = [1.0, 2.0, 3.0, 4.0]
    assert pop_first_segment(msgs, times) is True
    assert len(msgs) == 1 and msgs[0]["content"] == "new"
    assert times == [4.0]


def test_multiple_pops_preserve_tool_chain() -> None:
    """Após remover o primeiro turno, o segundo começa por user (nunca tool órfã)."""
    msgs = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t"}]},
        {"role": "tool", "tool_call_id": "t", "content": "ok"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "done"},
    ]
    times = [float(i) for i in range(5)]
    assert pop_first_segment(msgs, times) is True
    strip_leading_orphan_tools(msgs, times)
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
