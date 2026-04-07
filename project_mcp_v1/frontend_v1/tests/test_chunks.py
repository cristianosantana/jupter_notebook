from smartchat.message_processing.chunks import parse_assistant_chunks, trim_spacer_edges


def test_heading_and_paragraph():
    lines = ["# Título", "", "Parágrafo simples"]
    chunks = trim_spacer_edges(parse_assistant_chunks(lines))
    kinds = [type(c).__name__ for c in chunks]
    assert "ChunkHeading" in kinds
    assert "ChunkParagraph" in kinds
