import json
from pathlib import Path

import pytest

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.llm.request_dump import (
    build_chat_completion_messages,
    write_llm_debug_json,
)


def test_build_chat_completion_messages_with_and_without_system() -> None:
    m = build_chat_completion_messages(system_prompt=None, user_text="u")
    assert m == [{"role": "user", "content": "u"}]
    m2 = build_chat_completion_messages(system_prompt="  S  ", user_text="u")
    assert m2[0] == {"role": "system", "content": "S"}
    assert m2[1] == {"role": "user", "content": "u"}


def test_settings_llm_halt_coerced_from_string() -> None:
    s = Settings.model_validate({"llm_halt_before_chat": "TRUE"})
    assert s.llm_halt_before_chat is True
    s2 = Settings.model_validate({"llm_halt_before_chat": "0"})
    assert s2.llm_halt_before_chat is False


@pytest.mark.parametrize("raw", ("1", "true", "yes", "on", " True "))
def test_settings_llm_halt_truthy_strings(raw: str) -> None:
    s = Settings.model_validate({"llm_halt_before_chat": raw})
    assert s.llm_halt_before_chat is True


def test_write_llm_debug_json_creates_unique_file(tmp_path: Path) -> None:
    p1 = write_llm_debug_json(
        str(tmp_path),
        kind="chat_completion",
        transport="chat",
        session_id="sid",
        halted=True,
        openai_request={"model": "m", "messages": []},
    )
    p2 = write_llm_debug_json(
        str(tmp_path),
        kind="chat_completion",
        transport="chat",
        session_id="sid",
        halted=True,
        openai_request={"model": "m", "messages": []},
    )
    assert p1 != p2
    data = json.loads(Path(p1).read_text(encoding="utf-8"))
    assert data["halted"] is True
    assert data["openai_request"]["model"] == "m"
    assert data["schema"] == "orion_llm_debug/v1"
