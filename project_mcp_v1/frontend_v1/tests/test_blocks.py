import json

from smartchat.message_processing.blocks import extract_reply_content_blocks, parse_content_blocks


def test_parse_content_blocks_minimal():
    raw = {"version": 1, "blocks": [{"type": "paragraph", "text": "Olá"}]}
    p = parse_content_blocks(raw)
    assert p is not None
    assert len(p["blocks"]) == 1
    assert p["blocks"][0]["text"] == "Olá"


def test_extract_reply_from_fence():
    inner = json.dumps({"version": 1, "blocks": [{"type": "paragraph", "text": "X"}]})
    reply = f"Antes\n```json\n{inner}\n```\nDepois"
    display, payload = extract_reply_content_blocks(reply)
    assert "Antes" in display
    assert "Depois" in display
    assert "```" not in display
    assert payload is not None
    assert payload["blocks"][0]["text"] == "X"
