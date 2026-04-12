"""Truncagem segura de resultados de tool."""

import json

from app.tool_truncation import safe_truncate_tool_content


def test_no_truncation_when_under_cap():
    s = '{"a":1}'
    assert safe_truncate_tool_content(s, 1000) == s


def test_truncation_produces_valid_json():
    long = json.dumps({"rows": [{"x": i} for i in range(500)]})
    out = safe_truncate_tool_content(long, 400)
    data = json.loads(out)
    assert data.get("_truncated") is True
    assert "hint" in data
