from orion_mcp.core.config.settings import Settings
from orion_mcp.core.llm.model_config import (
    resolve_chat_model_id,
    resolve_embedding_model_id,
    resolve_model,
)
from orion_mcp.core.strategy import Strategy


def test_resolve_chat_model_id_fast_vs_deep() -> None:
    s = Settings(
        llm_model_fast="fast-model",
        llm_model_reasoning="reason-model",
    )
    assert resolve_chat_model_id(s, Strategy.fast) == "fast-model"
    assert resolve_chat_model_id(s, Strategy.deep) == "reason-model"


def test_resolve_embedding_model_id() -> None:
    s = Settings(embedding_model="emb-xyz")
    assert resolve_embedding_model_id(s) == "emb-xyz"


def test_resolve_model_alias_matches_chat() -> None:
    s = Settings(llm_model_fast="a", llm_model_reasoning="b")
    assert resolve_model(s, Strategy.fast) == resolve_chat_model_id(s, Strategy.fast)
