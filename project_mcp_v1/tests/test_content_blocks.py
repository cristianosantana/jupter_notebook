"""Testes do parser ``split_reply_and_blocks``."""

from app.content_blocks import split_reply_and_blocks


def test_strips_trailing_json_fence():
    text = """Resumo.

```json
{"version": 1, "content_blocks": [{"type": "paragraph", "text": "x"}]}
```
"""
    display, blocks = split_reply_and_blocks(text)
    assert "Resumo" in display
    assert "```" not in display
    assert blocks is not None
    assert blocks["version"] == 1
    assert len(blocks["content_blocks"]) == 1


def test_legacy_blocks_key_still_parsed():
    text = """Legado.

```json
{"version": 1, "blocks": [{"type": "paragraph", "text": "y"}]}
```
"""
    display, payload = split_reply_and_blocks(text)
    assert "Legado" in display
    assert payload is not None
    assert payload["version"] == 1
    assert len(payload["content_blocks"]) == 1
    assert payload["content_blocks"][0]["text"] == "y"


def test_invalid_fence_ignored():
    text = "Só texto ```json\nnot json\n``` fim"
    display, blocks = split_reply_and_blocks(text)
    assert blocks is None
    assert display == text


def test_whole_body_json():
    raw = (
        '{"version": 1, "content_blocks": '
        '[{"type": "heading", "level": 2, "text": "T"}]}'
    )
    display, blocks = split_reply_and_blocks(raw)
    assert display == ""
    assert blocks is not None
    assert blocks["content_blocks"][0]["type"] == "heading"
