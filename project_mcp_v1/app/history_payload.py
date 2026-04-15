"""Montagem do histórico enviado ao LLM: janela + resumo + (opcional) kNN semântico no meio."""

from __future__ import annotations

import copy
import logging
from typing import Any, Awaitable, Callable

from app.config import Settings

_logger = logging.getLogger(__name__)

REC_SEM_START = "### Recuperação semântica (trechos anteriores)"
REC_SEM_END = "### Fim da recuperação semântica"


def latest_user_text_for_semantic(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        if m.get("_orch_synthetic"):
            continue
        t = _plain_text_content(m)
        if t.strip():
            return t.strip()[:8000]
    return ""


def _plain_text_content(msg: dict[str, Any]) -> str:
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for p in c:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return "\n".join(parts)
    return ""


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (na**0.5 * nb**0.5)


async def _semantic_markdown_block(
    middle: list[dict[str, Any]],
    query: str,
    embed_texts: Callable[[list[str]], Awaitable[list[list[float]]]],
    *,
    top_k: int,
    max_chars: int,
    max_embed_inputs: int,
) -> str:
    if top_k <= 0 or not middle or not (query or "").strip():
        return ""
    items: list[tuple[int, str, str]] = []
    slice_middle = middle[-max_embed_inputs:] if len(middle) > max_embed_inputs else middle
    offset = len(middle) - len(slice_middle)
    for j, m in enumerate(slice_middle):
        idx = offset + j
        role = str(m.get("role") or "")
        txt = _plain_text_content(m).strip()
        if len(txt) < 8:
            continue
        items.append((idx, role, txt[:12000]))
    if not items:
        return ""
    texts = [query.strip()[:8000]] + [f"{role}: {txt}" for _, role, txt in items]
    try:
        vecs = await embed_texts(texts)
    except Exception as e:
        _logger.warning("history semantic embed failed: %s", e)
        return ""
    if not vecs or len(vecs) != len(texts):
        return ""
    qv = vecs[0]
    scored: list[tuple[float, int, str, str]] = []
    for j, (idx, role, txt) in enumerate(items):
        sv = vecs[j + 1]
        scored.append((_cosine_sim(qv, sv), idx, role, txt))
    scored.sort(key=lambda x: -x[0])
    lines: list[str] = []
    used = 0
    for _, idx, role, txt in scored[:top_k]:
        chunk = f"- [{role} #{idx}] {txt[:1200]}"
        if used + len(chunk) + 2 > max_chars:
            break
        lines.append(chunk)
        used += len(chunk) + 2
    if not lines:
        return ""
    return f"{REC_SEM_START}\n" + "\n".join(lines) + f"\n{REC_SEM_END}"


async def build_compact_history_messages_for_llm(
    messages: list[dict[str, Any]],
    session_metadata: dict[str, Any] | None,
    *,
    embed_texts: Any,
    query_fallback: str,
    settings: Settings | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Devolve cópia das mensagens para enviar ao modelo (prefixo sintético + cauda).
    ``self.messages`` original não é alterado.
    """
    st = settings or get_settings()
    if not st.orchestrator_history_compact_enabled:
        return [copy.deepcopy(m) for m in messages], "compact_disabled"

    msgs = [copy.deepcopy(m) for m in messages]
    tail_n = max(1, int(st.orchestrator_history_tail_messages))
    if len(msgs) <= tail_n:
        return msgs, "short_history"

    head = msgs[:-tail_n]
    tail = msgs[-tail_n:]

    prefix: list[dict[str, Any]] = []
    if st.memory_conversation_summary_enabled and session_metadata:
        s = session_metadata.get("conversation_summary")
        if isinstance(s, str) and s.strip():
            body = s.strip()[:12000]
            prefix.append(
                {
                    "role": "user",
                    "content": (
                        "### Resumo da conversa (metadados; somente leitura)\n\n"
                        f"{body}\n\n### Fim do resumo"
                    ),
                    "_orch_synthetic": True,
                }
            )

    q = (query_fallback or "").strip() or latest_user_text_for_semantic(msgs)
    sem = ""
    if (
        st.orchestrator_history_semantic_enabled
        and embed_texts is not None
        and callable(embed_texts)
        and int(st.orchestrator_history_semantic_top_k) > 0
    ):
        sem = await _semantic_markdown_block(
            head,
            q,
            embed_texts,
            top_k=int(st.orchestrator_history_semantic_top_k),
            max_chars=max(0, int(st.orchestrator_history_semantic_max_chars)),
            max_embed_inputs=int(st.orchestrator_history_semantic_max_embed_inputs),
        )
    if sem:
        prefix.append({"role": "user", "content": sem, "_orch_synthetic": True})

    return prefix + tail, "ok"
