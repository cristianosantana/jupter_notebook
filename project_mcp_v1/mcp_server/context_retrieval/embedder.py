from __future__ import annotations

import logging
from functools import lru_cache

from openai import AsyncOpenAI

_logger = logging.getLogger(__name__)

# Modelos text-embedding-3-* e ada-002 usam tokenização cl100k_base (documentação OpenAI).
_OFFICIAL_EMBEDDING_MAX_TOKENS = 8192


@lru_cache(maxsize=1)
def _cl100k_encoder():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def truncate_text_for_embedding(text: str, max_tokens: int) -> tuple[str, bool]:
    """
    Garante ``len(tokens) <= max_tokens`` para a API de embeddings.

    Devolve ``(texto, truncado)``.
    """
    if max_tokens < 1:
        max_tokens = 1
    enc = _cl100k_encoder()
    ids = enc.encode(text or "", disallowed_special=())
    if len(ids) <= max_tokens:
        return text, False
    out = enc.decode(ids[:max_tokens])
    return out, True


async def embed_texts(
    texts: list[str],
    *,
    model: str,
) -> list[list[float]]:
    if not texts:
        return []
    from app.config import get_settings

    st = get_settings()
    key = (st.openai_api_key or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY em falta para embeddings.")
    max_tok = min(
        _OFFICIAL_EMBEDDING_MAX_TOKENS,
        max(256, int(st.context_embedding_max_input_tokens)),
    )
    trimmed: list[str] = []
    n_trunc = 0
    for t in texts:
        s, did = truncate_text_for_embedding(t, max_tok)
        trimmed.append(s)
        if did:
            n_trunc += 1
    if n_trunc:
        _logger.warning(
            "embed_texts: truncados %s/%s textos a <=%s tokens (modelo=%s)",
            n_trunc,
            len(texts),
            max_tok,
            model,
        )
    client = AsyncOpenAI(api_key=key)
    res = await client.embeddings.create(model=model, input=trimmed)
    return [list(d.embedding) for d in res.data]
