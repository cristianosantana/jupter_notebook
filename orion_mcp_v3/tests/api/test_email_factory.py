from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator, Sequence

from orion_mcp_v3.api.email import EmailMessageFactory, EmailReport, build_report_from_text, render_response_email_html
from orion_mcp_v3.protocols.llm import ChatMessage, LLMResponse, LLMResponseMeta, LLMStreamChunk


FIXTURE = Path("tests/fixtures/email/fechamento_gerencial_marco.txt")
JANUARY_FIXTURE = Path("tests/fixtures/email/fechamento_gerencial_janeiro_narrator.txt")


class FakeLLMProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0
        self.last_messages: Sequence[ChatMessage] = ()

    async def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self.text, meta=LLMResponseMeta(model="fake"))

    async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        self.last_messages = messages
        return LLMResponse(text=self.text, meta=LLMResponseMeta(model="fake"))

    async def stream(self, messages: Sequence[ChatMessage], **kwargs: Any) -> AsyncIterator[LLMStreamChunk]:
        yield LLMStreamChunk(delta=self.text, finish_reason="stop")


async def test_email_factory_uses_llm_json_without_rendering_raw_html() -> None:
    provider = FakeLLMProvider(
        """
        {
          "headline": "Faturamento líquido — R$ 2.713.158,18",
          "period": "2026-03-01 a 2026-03-31",
          "sections": [
            {
              "title": "Faturamento por forma de pagamento",
              "kind": "revenue",
              "total": "R$ 2.713.158,18",
              "highlight": "Cartão de Crédito — R$ 1.352.045,28 (49,83%)",
              "items": ["Cartão <b>malicioso</b>: R$ 1.352.045,28"]
            }
          ],
          "alerts": ["Discrepância a verificar: R$ 3.770,00"],
          "actions": ["Conciliar cartão e parcelamento."]
        }
        """
    )

    report = await EmailMessageFactory(provider=provider).build_report(
        subject="Fechamento gerencial de março de 2026",
        body="Faturamento líquido em março: R$ 2.713.158,18 com <script>alert(1)</script>",
        from_name="CarSoul",
    )
    html = render_response_email_html(
        subject="Fechamento gerencial de março de 2026",
        body="texto original",
        from_name="CarSoul",
        report=report,
    )

    assert provider.calls == 1
    assert isinstance(report, EmailReport)
    assert report.sections[0].title == "Faturamento por forma de pagamento"
    assert "<b>malicioso</b>" not in html
    assert "&lt;b&gt;malicioso&lt;/b&gt;" in html
    assert "Discrepância a verificar" in html


async def test_email_factory_sends_message_type_and_schema_to_llm() -> None:
    provider = FakeLLMProvider(
        """
        {
          "type": "ranking",
          "period": "abril/2026",
          "metric": "total_comissao",
          "dimension": "concessionaria",
          "headline_value": "R$ 322.589,52",
          "items": [
            {"rank": 1, "label": "GWM BAMAQ", "value": "R$ 38.162,34", "pct": "11,83%"}
          ],
          "notes": []
        }
        """
    )

    report = await EmailMessageFactory(provider=provider).build_report(
        subject="Ranking de comissões",
        body="Top 5 concessionárias por comissão em abril/2026:\n1. GWM BAMAQ: R$ 38.162,34 (11,83%)",
        from_name="CarSoul",
    )

    prompt = provider.last_messages[-1].content
    assert provider.calls == 1
    assert '"message_type": "ranking"' in prompt
    assert '"ranking"' in prompt
    assert report.report_type == "ranking"
    assert report.sections[0].title == "Ranking"
    assert report.sections[0].items[0].label == "GWM BAMAQ"


async def test_email_factory_skips_llm_for_conversational_message() -> None:
    provider = FakeLLMProvider('{"type": "ranking", "items": [{"label": "errado"}]}')

    report = await EmailMessageFactory(provider=provider).build_report(
        subject="Resposta Orion",
        body="Olá, envie um período para eu consultar o fechamento.",
        from_name="CarSoul",
    )

    assert provider.calls == 0
    assert report.report_type == "conversacional"
    assert report.sections[0].title == "Mensagem"
    assert report.sections[0].items[0].label == "Olá, envie um período para eu consultar o fechamento."


async def test_email_factory_merges_structured_evidence_with_narrator_feedback() -> None:
    provider = FakeLLMProvider(
        """
        {
          "headline": "Faturamento total do período com concentração em cartão",
          "executive_summary": "O fechamento mostra concentração em cartão e comissão puxada por poucas concessionárias. A leitura executiva é priorizar conciliação e negociação de tarifas.",
          "alerts": ["Atenção à concentração em cartão mencionada pelo narrador."],
          "actions": ["Priorizar conciliação de cartão e revisar tarifas."]
        }
        """
    )
    evidence = FIXTURE.read_text(encoding="utf-8")
    narrative = (
        "O fechamento mostra concentração em cartão e comissão puxada por poucas concessionárias. "
        "Atenção à concentração em cartão mencionada pelo narrador. "
        "Priorizar conciliação de cartão e revisar tarifas."
    )

    report = await EmailMessageFactory(provider=provider).build_report(
        subject="Fechamento gerencial de março de 2026",
        body=narrative,
        structured_evidence=evidence,
        from_name="CarSoul",
    )

    prompt = provider.last_messages[-1].content
    assert provider.calls == 1
    assert narrative in prompt
    assert "Linha extra não deve aparecer" not in prompt
    assert report.report_type == "fechamento_gerencial"
    assert report.headline == "Faturamento total do período com concentração em cartão"
    assert report.executive_summary.startswith("O fechamento mostra concentração em cartão")
    assert "Faturamento por forma de pagamento" in [section.title for section in report.sections]
    commission = next(section for section in report.sections if section.title == "Faturamento e comissão por concessionária")
    assert commission.items[-1].label == "Linha extra não deve aparecer"
    assert report.alerts[0] == "Atenção à concentração em cartão mencionada pelo narrador."
    assert report.actions[0] == "Priorizar conciliação de cartão e revisar tarifas."


async def test_email_factory_enriches_short_llm_sections_with_fallback_top_10() -> None:
    provider = FakeLLMProvider(
        """
        {
          "headline": "Faturamento líquido no período 2026-03-01 a 2026-03-31 — R$ 2.713.158,18",
          "period": "2026-03-01 a 2026-03-31",
          "sections": [
            {
              "title": "Faturamento e comissão por concessionária",
              "kind": "commission",
              "total": "R$ 355.437,45",
              "highlight": "PORSCHE — R$ 41.195,20 (11,59%)",
              "items": ["PORSCHE: R$ 41.195,20 (11,59%)"]
            }
          ],
          "alerts": [],
          "actions": []
        }
        """
    )

    report = await EmailMessageFactory(provider=provider).build_report(
        subject="Fechamento gerencial de março de 2026",
        body=FIXTURE.read_text(encoding="utf-8"),
        from_name="CarSoul",
    )

    section = next(item for item in report.sections if item.title == "Faturamento e comissão por concessionária")
    labels = [item.label for item in section.items]
    assert len(section.items) == 11
    assert labels[:3] == ["PORSCHE", "GWM BAMAQ", "SAITAMA - HONDA"]
    assert "Kyoto Toyota" in labels
    assert "Linha extra não deve aparecer" in labels


async def test_email_factory_prefers_deterministic_sections_when_llm_mixes_sections() -> None:
    provider = FakeLLMProvider(
        """
        {
          "headline": "Faturamento líquido (01/01/2026 a 31/01/2026): R$ 2.154.503,81",
          "period": "01/01/2026 a 31/01/2026",
          "sections": [
            {
              "title": "Faturamento por tipo de pagamento",
              "kind": "payment",
              "total": "R$ 2.154.503,81",
              "highlight": "Cartão de Crédito R$ 1.143.256,71 (53,06%).",
              "items": ["Cartão de Crédito R$ 1.143.256,71 (53,06%)."]
            },
            {
              "title": "Faturamento por tipo de venda de produtos",
              "kind": "revenue",
              "total": "R$ 59.520,00",
              "highlight": "Venda de Materiais R$ 59.520,00 (100,00%).",
              "items": [
                "Faturamento e comissão por concessionária — Total: sem total explícito informado no template — Destaque: SAITAMA - HONDA R$ 33.828,00 (10,95%).",
                "Produção por serviço — Total: sem total explícito informado no template — Destaque: PPF REGENERATIVO - FULL - CARRO INTEIRO R$ 362.390,00 (17,29%)."
              ]
            }
          ],
          "alerts": [],
          "actions": []
        }
        """
    )

    report = await EmailMessageFactory(provider=provider).build_report(
        subject="Fechamento gerencial de janeiro de 2026",
        body=JANUARY_FIXTURE.read_text(encoding="utf-8"),
        from_name="CarSoul",
    )

    payment = next(section for section in report.sections if section.title == "Faturamento por tipo de pagamento")
    products = next(section for section in report.sections if section.title == "Faturamento por tipo de venda de produtos")
    commissions = next(section for section in report.sections if section.title == "Faturamento e comissão por concessionária")
    installments = next(section for section in report.sections if section.title == "Parcelamento de cartão")

    assert len(payment.items) == 8
    assert payment.items[0].label == "Cartão de Crédito"
    assert payment.items[0].value == "R$ 1.143.256,71"
    assert len(products.items) == 1
    assert products.items[0].label == "Venda de Materiais"
    assert all("Faturamento e comissão" not in item.label for item in products.items)
    assert commissions.items[0].label == "SAITAMA - HONDA"
    assert installments.items[0].label == "10X"
    assert len(report.alerts) == 2
    assert len(report.actions) == 2


async def test_email_factory_discards_llm_only_duplicate_summary_when_fallback_is_structured() -> None:
    provider = FakeLLMProvider(
        """
        {
          "headline": "Faturamento líquido por forma de pagamento: R$ 2.616.331,33",
          "period": "2026-04-01 a 2026-04-30",
          "sections": [
            {
              "title": "Visão geral",
              "kind": "summary",
              "items": [
                "Faturamento líquido total (por forma de pagamento) no período: R$ 2.616.331,33. A receita está concentrada em Cartão de Crédito.",
                "O fechamento foi produzido com 9 templates; a descrição dos templates e somas por seção está abaixo."
              ]
            },
            {
              "title": "Taxas de cartão de crédito",
              "kind": "fees",
              "total": "R$ 5.650,60",
              "highlight": "BH ESTÉTICA: R$ 1.787,20 (31,63%)",
              "items": [
                "Total: R$ 2.616.331,33",
                "Cartão de Crédito: R$ 1.089.898,35 (41,66%)",
                "Total (soma das linhas): R$ 2.513.987,26"
              ],
              "notes": [
                "Top 10 (de 31 linhas):",
                "Top 10 (de 61 linhas):"
              ]
            },
            {
              "title": "Formas de pagamento",
              "kind": "payment",
              "total": "R$ 2.616.331,33"
            }
          ],
          "alerts": ["Concentração alta por produto."],
          "actions": ["Priorizar negociação de tarifas."]
        }
        """
    )

    report = await EmailMessageFactory(provider=provider).build_report(
        subject="Fechamento gerencial de abril de 2026",
        body=JANUARY_FIXTURE.read_text(encoding="utf-8"),
        from_name="CarSoul",
    )

    titles = [section.title for section in report.sections]
    assert "Visão geral" not in titles
    assert "Formas de pagamento" not in titles

    fees = next(section for section in report.sections if section.title == "Taxas de cartão de crédito")
    assert [item.label for item in fees.items] == ["BH ESTÉTICA", "CARSOUL", "MFP ESTETICA AUTOMOTIVA"]
    assert not any(item.label == "Total" for item in fees.items)
    assert not any("Top 10" in note for note in fees.notes)


async def test_email_factory_fallback_splits_fechamento_into_business_sections() -> None:
    body = FIXTURE.read_text(encoding="utf-8")

    report = await EmailMessageFactory().build_report(
        subject="Fechamento gerencial de março de 2026",
        body=body,
        from_name="CarSoul",
    )

    titles = [section.title for section in report.sections]
    assert report.headline == "Faturamento líquido no período 2026-03-01 a 2026-03-31 — R$ 2.713.158,18"
    assert "Faturamento por forma de pagamento" in titles
    assert "Faturamento por tipo de venda" in titles
    assert "Faturamento e comissão por concessionária" in titles
    assert "Produção por serviço" in titles
    assert "Parcelamento de cartão" in titles
    assert "Taxas de cartão de crédito" in titles
    payment = next(section for section in report.sections if section.title == "Faturamento por forma de pagamento")
    commission = next(section for section in report.sections if section.title == "Faturamento e comissão por concessionária")
    product = next(section for section in report.sections if section.title == "Produção por produto")
    installments = next(section for section in report.sections if section.title == "Parcelamento de cartão")
    assert len(payment.items) == 8
    assert len(commission.items) == 11
    assert commission.items[-1].label == "Linha extra não deve aparecer"
    assert len(product.items) == 6
    assert product.items[-1].label == "Filme Solar STA"
    assert len(installments.items) == 10
    assert installments.items[-1].label == "7X"
    assert len(report.alerts) == 5
    assert len(report.actions) == 3
    assert report.alerts
    assert report.actions


def test_email_factory_fallback_parses_pipe_table_sections() -> None:
    body = "\n".join(
        [
            "Detalhe por seção do fechamento gerencial:",
            "",
            "## Comissão por tipo de O.S.",
            "Template: fechamento_faturamento_comissao_tipo_os_concessionaria_periodo",
            "Linhas disponíveis: 2",
            "concessionaria | venda normal | financiamento | total comissão",
            "Concessionária A | R$ 120.000,00 | R$ 80.000,00 | R$ 200.000,00",
            "Concessionária B | R$ 90.000,00 | R$ 0,00 | R$ 90.000,00",
        ]
    )

    parsed = build_report_from_text(
        subject="Fechamento",
        body=body,
        from_name="CarSoul",
        report_type="fechamento_gerencial",
    )

    section = parsed.sections[0]
    assert section.title == "Comissão por tipo de O.S."
    assert section.tables
    assert section.tables[0].headers == ("concessionaria", "venda normal", "financiamento", "total comissão")
    assert section.tables[0].rows[0] == ("Concessionária A", "R$ 120.000,00", "R$ 80.000,00", "R$ 200.000,00")


def test_structured_email_renderer_outputs_cards_badges_and_metric_rows() -> None:
    report = EmailReport.from_mapping(
        {
            "headline": "Faturamento líquido — R$ 2.713.158,18",
            "period": "2026-03",
            "sections": [
                {
                    "title": "Faturamento por forma de pagamento",
                    "kind": "revenue",
                    "total": "R$ 2.713.158,18",
                    "highlight": "Cartão de Crédito — R$ 1.352.045,28 (49,83%)",
                    "items": ["Cartão de Crédito: R$ 1.352.045,28 (49,83%)", "PIX: R$ 399.819,98 (14,74%)"],
                    "notes": ["Detalhe: todos os registros."],
                }
            ],
            "alerts": ["Discrepância a verificar: R$ 3.770,00"],
            "actions": ["Conciliar cartão e parcelamento."],
        }
    )

    html = render_response_email_html(
        subject="Fechamento gerencial de março de 2026",
        body="fallback text",
        from_name="CarSoul",
        report=report,
    )

    assert 'class="hero-card"' in html
    assert 'class="report-section section-revenue"' in html
    assert 'class="badge badge-highlight"' in html
    assert "<strong>Cartão de Crédito</strong>" in html
    assert 'class="alert-card"' in html
    assert 'class="action-card"' in html
