from smartchat.message_processing.dedupe import extract_tsv_table_from_prose, strip_duplicate_concessionaria_list


def test_strip_duplicate_list_when_reference_rows_match():
    row = (
        "OS 10001 Recebido 10 Pendente 5 Faturamento Previsto 99 — detalhe extra"
    )
    prose = "Intro\n\n" + "\n".join([row, row, row]) + "\nFim"
    out = strip_duplicate_concessionaria_list(prose, 3)
    assert "OS 10001" not in out
    assert "Fim" in out


def test_extract_tsv_basic():
    # Cabeçalho deve passar o heurístico de `find_tsv_block` (palavras-chave).
    prose = "Título\nConcessionária\tQtd\tRecebido\tPendente\n1\t2\t3\t4\n4\t5\t6\t7\n"
    r = extract_tsv_table_from_prose(prose)
    assert r.table is not None
    assert r.table.columns == ["Concessionária", "Qtd", "Recebido", "Pendente"]
    assert len(r.table.rows) == 2
