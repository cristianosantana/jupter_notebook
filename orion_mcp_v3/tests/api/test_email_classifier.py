from __future__ import annotations

from orion_mcp_v3.api.email.classifier import classify_message


def test_email_classifier_detects_fechamento_gerencial() -> None:
    body = (
        "Detalhe por seção do fechamento gerencial:\n"
        "## Faturamento por tipo de pagamento\n"
        "Linhas disponíveis: 8\n"
        "1. Cartão de Crédito: R$ 1.143.256,71 (53,06%)\n"
        "Fechamento projetado com 9 template(s)."
    )

    assert classify_message(body) == "fechamento_gerencial"


def test_email_classifier_detects_ranking() -> None:
    body = "Top 5 concessionárias por comissão:\n1. GWM BAMAQ: R$ 38.162,34 (11,83%)"

    assert classify_message(body) == "ranking"


def test_email_classifier_detects_comparacao() -> None:
    body = "Comparação entre março e abril: houve aumento de R$ 120.000,00 e variação de 12%."

    assert classify_message(body) == "comparacao"


def test_email_classifier_detects_analise_unica() -> None:
    body = "Faturamento líquido em abril de 2026: R$ 2.616.331,33."

    assert classify_message(body) == "analise_unica"


def test_email_classifier_detects_conversacional() -> None:
    body = "Olá, posso ajudar com uma análise quando você enviar o período."

    assert classify_message(body) == "conversacional"
