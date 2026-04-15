"""Fusão hit/miss de vectores por mensagem (``merge_message_vectors_for_retrieve``)."""

from __future__ import annotations

from mcp_server.context_retrieval.vectors import merge_message_vectors_for_retrieve


def test_merge_all_hits() -> None:
    msgs = [{"id": 1, "role": "u"}, {"id": 2, "role": "a"}]
    cached = {1: [1.0, 0.0], 2: [0.0, 1.0]}
    m, h, m_ = merge_message_vectors_for_retrieve(
        msgs, cached=cached, fresh={}, query_dim=2
    )
    assert m is not None
    vecs, hits, misses = m, h, m_
    assert hits == 2 and misses == 0
    assert vecs == [[1.0, 0.0], [0.0, 1.0]]


def test_merge_hits_and_fresh() -> None:
    msgs = [{"id": 10, "role": "u"}, {"id": 20, "role": "a"}]
    cached = {10: [3.0, 4.0]}
    fresh = {20: [0.0, 1.0]}
    out = merge_message_vectors_for_retrieve(
        msgs, cached=cached, fresh=fresh, query_dim=2
    )
    assert out is not None
    vecs, hits, misses = out
    assert hits == 1 and misses == 1
    assert vecs[0] == [3.0, 4.0] and vecs[1] == [0.0, 1.0]


def test_merge_returns_none_when_fresh_missing() -> None:
    msgs = [{"id": 1, "role": "u"}]
    assert (
        merge_message_vectors_for_retrieve(
            msgs, cached={}, fresh={}, query_dim=4
        )
        is None
    )


def test_wrong_cached_dim_treated_as_miss() -> None:
    msgs = [{"id": 1, "role": "u"}]
    cached = {1: [1.0]}  # dim 1 != query_dim 2
    fresh = {1: [2.0, 3.0]}
    out = merge_message_vectors_for_retrieve(
        msgs, cached=cached, fresh=fresh, query_dim=2
    )
    assert out is not None
    assert out[1:] == (0, 1)
    assert out[0] == [[2.0, 3.0]]
