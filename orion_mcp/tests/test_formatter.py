from orion_mcp.core.formatter.formatter import FormatRequest, format_response


def test_formatter_lista() -> None:
    out = format_response(FormatRequest(content="a\nb", format="lista"))
    assert out["format"] == "lista"
    assert "<ul>" in out["body"]


def test_formatter_no_state() -> None:
    req = FormatRequest(content="x", format="html")
    assert "article" in format_response(req)["body"]
