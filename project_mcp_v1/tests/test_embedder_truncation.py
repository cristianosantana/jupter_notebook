"""Truncagem de entradas para embeddings (limite de tokens OpenAI)."""

from mcp_server.context_retrieval.embedder import (
    truncate_text_for_embedding,
    _cl100k_encoder,
)


def test_truncate_text_for_embedding_noop_when_short():
    s = "hello world"
    out, trunc = truncate_text_for_embedding(s, max_tokens=8192)
    assert out == s
    assert trunc is False


def test_truncate_text_for_embedding_long_repeated_token():
    enc = _cl100k_encoder()
    # Repetição gera muitos tokens com texto curto em caracteres.
    chunk = " ab" * 5000
    ids = enc.encode(chunk, disallowed_special=())
    assert len(ids) > 100
    out, trunc = truncate_text_for_embedding(chunk, max_tokens=50)
    assert trunc is True
    assert len(enc.encode(out, disallowed_special=())) <= 50
