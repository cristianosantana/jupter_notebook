from __future__ import annotations

import json

import pytest

from orion_mcp_v3.public_chat.config.settings import PublicChatSettings
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import (
    begin_turn_trace,
    configure_public_chat_file_logging,
    current_log_file_path,
    log_public_chat_event,
    shutdown_public_chat_file_logging,
)


@pytest.fixture(autouse=True)
def _reset_pipeline_logging():
    shutdown_public_chat_file_logging()
    yield
    shutdown_public_chat_file_logging()


def test_file_logging_writes_jsonl(tmp_path) -> None:
    settings = PublicChatSettings(
        pipeline_trace=True,
        pipeline_log_dir=str(tmp_path),
    )
    configure_public_chat_file_logging(settings)
    trace_id = begin_turn_trace()
    log_public_chat_event(
        etapa="test.etapa",
        fase="pre",
        dados={"message_preview": "oi"},
    )

    path = current_log_file_path()
    assert path is not None
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["canal"] == "public_chat_pipeline"
    assert payload["etapa"] == "test.etapa"
    assert payload["trace_id"] == trace_id


def test_log_skipped_when_trace_disabled(tmp_path) -> None:
    settings = PublicChatSettings(
        pipeline_trace=False,
        pipeline_log_dir=str(tmp_path),
    )
    configure_public_chat_file_logging(settings)
    log_public_chat_event(etapa="test.etapa", fase="pre")
    assert current_log_file_path() is None
    assert list(tmp_path.iterdir()) == []
