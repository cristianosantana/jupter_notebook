from __future__ import annotations

from pathlib import Path


FORBIDDEN_RUNTIME_FILES = (
    Path("src/orion_mcp_v3/api/main.py"),
    Path("src/orion_mcp_v3/api/routes/chat.py"),
    Path("src/orion_mcp_v3/memory/retrieval_pipeline.py"),
    Path("src/orion_mcp_v3/memory/chat_turn_embedding_store.py"),
)


def test_remissive_distillation_is_not_hooked_into_chat_runtime() -> None:
    forbidden_tokens = (
        "DistillSupervisedMemoryCommand",
        "distill_supervised_memory",
        "RemissiveMemoryStore",
        "SupervisedConversationReader",
    )

    for path in FORBIDDEN_RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden_tokens), path
