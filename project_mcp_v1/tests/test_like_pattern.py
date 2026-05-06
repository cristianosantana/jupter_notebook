from mcp_server.context_retrieval.like_pattern import question_to_ilike_pattern


def test_ilike_pattern_wraps_tokens():
    p = question_to_ilike_pattern("volume  OS")
    assert p.startswith("%")
    assert "%" in p
