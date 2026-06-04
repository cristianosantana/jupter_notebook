from __future__ import annotations

from orion_mcp_v3.api.email_html_renderer import render_response_email_html


def test_render_response_email_html_builds_executive_sections() -> None:
    html = render_response_email_html(
        subject="Fechamento gerencial de maio-2026",
        body=(
            "Visão geral (período de referência: 2026-05-01 a 2026-05-31)\n"
            "- Receita concentrada em poucas concessionárias.\n\n"
            "Destaques\n"
            "- Top 3 concessionárias por total vendido: GWM BAMAQ — R$ 171.543,90.\n\n"
            "Alertas\n"
            "- Cobertura parcial indicada (confiança 0,65).\n\n"
            "Conclusão acionável\n"
            "- Priorizar agenda para PPF REGENERATIVO - FULL."
        ),
        from_name="CarSoul",
    )

    assert "<!doctype html>" in html
    assert "Fechamento gerencial de maio-2026" in html
    assert "CarSoul" in html
    assert 'class="section section-overview"' in html
    assert 'class="section section-highlights"' in html
    assert 'class="section section-alerts"' in html
    assert 'class="section section-actions"' in html
    assert "<li>Receita concentrada em poucas concessionárias.</li>" in html


def test_render_response_email_html_escapes_untrusted_content() -> None:
    html = render_response_email_html(
        subject="<script>alert('subject')</script>",
        body=(
            "Visão geral\n"
            "- Item seguro <script>alert('body')</script>\n\n"
            "Destaques\n"
            "- Valor <b>não deve virar HTML</b>"
        ),
        from_name="<b>Orion</b>",
    )

    assert "<script>" not in html
    assert "<b>Orion</b>" not in html
    assert "&lt;script&gt;alert(&#x27;body&#x27;)&lt;/script&gt;" in html
    assert "&lt;b&gt;não deve virar HTML&lt;/b&gt;" in html


def test_render_response_email_html_preserves_composed_direct_answer_blocks() -> None:
    html = render_response_email_html(
        subject="Fechamento",
        body=(
            "Resposta direta composta:\n"
            "## fechamento_faturamento_comissao_concessionaria_periodo\n"
            "Resposta direta: total vendido por concessionaria:\n"
            "1. GWM BAMAQ: R$ 171.543,90\n"
            "2. STRADA JEEP: R$ 154.602,90\n"
            "## fechamento_faturamento_tipo_pagamento\n"
            "Resposta direta: total liquido por tipo de pagamento:\n"
            "1. Cartão de Crédito: R$ 1.274.119,02"
        ),
        from_name="Orion",
    )

    assert 'class="section section-direct-answer"' in html
    assert "<h3>fechamento_faturamento_comissao_concessionaria_periodo</h3>" in html
    assert "<h3>fechamento_faturamento_tipo_pagamento</h3>" in html
    assert "<li>GWM BAMAQ: R$ 171.543,90</li>" in html
    assert "<li>Cartão de Crédito: R$ 1.274.119,02</li>" in html


def test_render_response_email_html_preserves_inline_composed_direct_answer() -> None:
    html = render_response_email_html(
        subject="Fechamento",
        body=(
            "Resposta direta composta: ## fechamento_faturamento_comissao_concessionaria_periodo "
            "Resposta direta: total de comissao por concessionaria: "
            "1. GWM BAMAQ: R$ 43.584,46 "
            "2. SAITAMA - HONDA: R$ 36.755,90 "
            "## fechamento_faturamento_tipo_pagamento "
            "Resposta direta: total liquido por tipo de pagamento: "
            "1. Cartão de Crédito: R$ 1.274.119,02"
        ),
        from_name="Orion",
    )

    assert 'class="section section-direct-answer"' in html
    assert "<h3>fechamento_faturamento_comissao_concessionaria_periodo</h3>" in html
    assert "<h3>fechamento_faturamento_tipo_pagamento</h3>" in html
    assert "total de comissao por concessionaria" in html
    assert "<li>GWM BAMAQ: R$ 43.584,46</li>" in html
    assert "<li>SAITAMA - HONDA: R$ 36.755,90</li>" in html
    assert "<li>Cartão de Crédito: R$ 1.274.119,02</li>" in html
