"""
Geração de PDF (12 páginas) com o relatório semanal de OS.

Estrutura do PDF:
  Pág  1  — Capa
  Pág  2  — Sumário / Índice
  Pág  3  — S1 Resumo Executivo (texto + gráfico)
  Pág  4  — S2 Concessionárias (texto + gráfico)
  Pág  5  — S3 Sazonalidade (texto + gráfico)
  Pág  6  — S4 Produtos e Serviços (texto + gráfico)
  Pág  7  — S5 Vendedores (texto + gráfico)
  Pág  8  — S6 Distribuição de Tickets (texto + gráfico)
  Pág  9  — S7 Cross-Selling (texto + gráfico)
  Pág 10  — S8 Alertas e Anomalias (texto + gráfico)
  Pág 11  — Consolidação de Alertas e Recomendações
  Pág 12  — Rodapé / Notas Metodológicas
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

COR_PRIMARIA = colors.HexColor("#2563eb")
COR_SECUNDARIA = colors.HexColor("#f97316")
COR_ACENTO = colors.HexColor("#10b981")
COR_PERIGO = colors.HexColor("#ef4444")
COR_FUNDO_CLARO = colors.HexColor("#f3f4f6")
COR_TEXTO = colors.HexColor("#1f2937")

ALERTA_CORES = {
    "normal": colors.HexColor("#10b981"),
    "atencao": colors.HexColor("#f59e0b"),
    "critico": colors.HexColor("#ef4444"),
}


def _styles() -> dict:
    ss = getSampleStyleSheet()
    custom = {}
    custom["titulo_capa"] = ParagraphStyle(
        "titulo_capa", parent=ss["Title"],
        fontSize=28, leading=34, textColor=COR_PRIMARIA, alignment=TA_CENTER,
        spaceAfter=12,
    )
    custom["subtitulo_capa"] = ParagraphStyle(
        "subtitulo_capa", parent=ss["Title"],
        fontSize=14, leading=18, textColor=COR_TEXTO, alignment=TA_CENTER,
        spaceAfter=6,
    )
    custom["secao_titulo"] = ParagraphStyle(
        "secao_titulo", parent=ss["Heading1"],
        fontSize=16, leading=20, textColor=COR_PRIMARIA,
        spaceBefore=10, spaceAfter=8,
        borderWidth=1, borderColor=COR_PRIMARIA, borderPadding=4,
    )
    custom["corpo"] = ParagraphStyle(
        "corpo", parent=ss["BodyText"],
        fontSize=10, leading=14, textColor=COR_TEXTO, alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    custom["corpo_small"] = ParagraphStyle(
        "corpo_small", parent=custom["corpo"],
        fontSize=8, leading=11,
    )
    custom["alerta_badge"] = ParagraphStyle(
        "alerta_badge", parent=ss["BodyText"],
        fontSize=10, leading=13, textColor=colors.white,
        alignment=TA_CENTER, spaceAfter=4,
    )
    custom["rodape"] = ParagraphStyle(
        "rodape", parent=ss["Normal"],
        fontSize=7, leading=9, textColor=colors.HexColor("#9ca3af"),
        alignment=TA_CENTER,
    )
    custom["sumario_item"] = ParagraphStyle(
        "sumario_item", parent=ss["BodyText"],
        fontSize=11, leading=16, textColor=COR_TEXTO,
        leftIndent=20, spaceAfter=4,
    )
    return custom


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#9ca3af"))
    canvas.drawString(MARGIN, PAGE_H - 1.2 * cm, "Relatório Semanal de OS — Análise Gerencial")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.2 * cm, datetime.now().strftime("%d/%m/%Y"))
    canvas.drawCentredString(PAGE_W / 2, 1 * cm, f"Página {doc.page}")
    canvas.setStrokeColor(COR_PRIMARIA)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - 1.5 * cm, PAGE_W - MARGIN, PAGE_H - 1.5 * cm)
    canvas.line(MARGIN, 1.5 * cm, PAGE_W - MARGIN, 1.5 * cm)
    canvas.restoreState()


def _capa_header_footer(canvas, doc):
    """Capa sem header/footer padrão."""
    pass


def _add_image(elements: list, img_path: str, max_width: float = CONTENT_W, max_height: float = 10 * cm):
    if img_path and os.path.isfile(img_path):
        img = Image(img_path)
        aspect = img.imageWidth / img.imageHeight
        w = min(max_width, img.imageWidth)
        h = w / aspect
        if h > max_height:
            h = max_height
            w = h * aspect
        img.drawWidth = w
        img.drawHeight = h
        elements.append(img)
        elements.append(Spacer(1, 6 * mm))


def _badge_alerta(nivel: str, styles: dict) -> Paragraph:
    cor = ALERTA_CORES.get(nivel, ALERTA_CORES["normal"])
    hex_cor = cor.hexval() if hasattr(cor, "hexval") else str(cor)
    return Paragraph(
        f'<font color="white"><b>  {nivel.upper()}  </b></font>',
        ParagraphStyle("badge", parent=styles["alerta_badge"], backColor=cor),
    )


def _secao_page(
    elements: list,
    titulo: str,
    texto_analise: str,
    nivel_alerta: str,
    img_path: Optional[str],
    styles: dict,
):
    elements.append(Paragraph(titulo, styles["secao_titulo"]))
    elements.append(_badge_alerta(nivel_alerta, styles))
    elements.append(Spacer(1, 4 * mm))

    for paragrafo in texto_analise.split("\n\n"):
        paragrafo = paragrafo.strip()
        if paragrafo:
            elements.append(Paragraph(paragrafo.replace("\n", "<br/>"), styles["corpo"]))

    elements.append(Spacer(1, 4 * mm))
    _add_image(elements, img_path)
    elements.append(PageBreak())


def gerar_relatorio_pdf(
    analise: Dict[str, Any],
    graficos: Dict[str, str],
    out_path: str = "output/relatorio_semanal_os.pdf",
    titulo: str = "Relatório Semanal de Ordens de Serviço",
    subtitulo: Optional[str] = None,
    periodo: Optional[str] = None,
) -> str:
    """
    Gera o PDF de 12 páginas.

    Args:
        analise: Dict com chaves S1_resumo_executivo, S1_alerta, S2_concessionarias, ...
                 alertas_consolidados, recomendacoes (conforme SKILL.md FASE 2)
        graficos: Dict {s1: path_png, s2: path_png, ...} retornado por gerar_todos_graficos()
        out_path: Caminho de saída do PDF
        titulo: Título da capa
        subtitulo: Subtítulo opcional
        periodo: String do período analisado

    Returns:
        Caminho absoluto do PDF gerado
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()

    frame_capa = Frame(MARGIN, MARGIN, CONTENT_W, PAGE_H - 2 * MARGIN, id="capa")
    frame_conteudo = Frame(MARGIN, 2 * cm, CONTENT_W, PAGE_H - 4 * cm, id="conteudo")

    doc = BaseDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    doc.addPageTemplates([
        PageTemplate(id="capa", frames=[frame_capa], onPage=_capa_header_footer),
        PageTemplate(id="conteudo", frames=[frame_conteudo], onPage=_header_footer),
    ])

    elements = []

    # === PÁGINA 1: CAPA ===
    elements.append(Spacer(1, 6 * cm))
    elements.append(Paragraph(titulo, styles["titulo_capa"]))
    if subtitulo:
        elements.append(Paragraph(subtitulo, styles["subtitulo_capa"]))
    if periodo:
        elements.append(Spacer(1, 1 * cm))
        elements.append(Paragraph(f"Período: {periodo}", styles["subtitulo_capa"]))
    elements.append(Spacer(1, 2 * cm))
    data_geracao = datetime.now().strftime("%d/%m/%Y às %H:%M")
    elements.append(Paragraph(f"Gerado automaticamente em {data_geracao}", styles["corpo"]))
    elements.append(Paragraph("Agente: agente_analise_os | Orquestrador: Maestro", styles["corpo"]))
    elements.append(NextPageTemplate("conteudo"))
    elements.append(PageBreak())

    # === PÁGINA 2: SUMÁRIO ===
    elements.append(Paragraph("Sumário", styles["secao_titulo"]))
    elements.append(Spacer(1, 8 * mm))
    secoes_sumario = [
        ("S1", "Resumo Executivo"),
        ("S2", "Faturamento e Ticket por Concessionária"),
        ("S3", "Sazonalidade"),
        ("S4", "Produtos e Serviços"),
        ("S5", "Performance de Vendedores"),
        ("S6", "Distribuição de Tickets"),
        ("S7", "Cross-Selling"),
        ("S8", "Alertas e Anomalias"),
        ("—", "Consolidação de Alertas e Recomendações"),
        ("—", "Notas Metodológicas"),
    ]
    for cod, nome in secoes_sumario:
        alerta_key = f"{cod}_alerta" if cod.startswith("S") else None
        nivel = analise.get(alerta_key, "") if alerta_key else ""
        cor_dot = ALERTA_CORES.get(nivel, colors.HexColor("#d1d5db"))
        hex_c = cor_dot.hexval() if hasattr(cor_dot, "hexval") else str(cor_dot)
        elements.append(Paragraph(
            f'<font color="{hex_c}">●</font>  <b>{cod}</b> — {nome}',
            styles["sumario_item"],
        ))
    elements.append(PageBreak())

    # === PÁGINAS 3-10: SEÇÕES S1 A S8 ===
    secoes_config = [
        ("S1 — Resumo Executivo", "S1_resumo_executivo", "S1_alerta", "s1"),
        ("S2 — Faturamento e Ticket por Concessionária", "S2_concessionarias", "S2_alerta", "s2"),
        ("S3 — Sazonalidade", "S3_sazonalidade", "S3_alerta", "s3"),
        ("S4 — Produtos e Serviços", "S4_produtos", "S4_alerta", "s4"),
        ("S5 — Performance de Vendedores", "S5_vendedores", "S5_alerta", "s5"),
        ("S6 — Distribuição de Tickets", "S6_faixas_preco", "S6_alerta", "s6"),
        ("S7 — Cross-Selling", "S7_cross_selling", "S7_alerta", "s7"),
        ("S8 — Alertas e Anomalias", "S8_alertas_anomalias", "S8_alerta", "s8"),
    ]
    for titulo_sec, chave_texto, chave_alerta, chave_graf in secoes_config:
        texto = analise.get(chave_texto, "Análise não disponível para esta seção.")
        nivel = analise.get(chave_alerta, "normal")
        img = graficos.get(chave_graf)
        _secao_page(elements, titulo_sec, texto, nivel, img, styles)

    # === PÁGINA 11: CONSOLIDAÇÃO DE ALERTAS E RECOMENDAÇÕES ===
    elements.append(Paragraph("Consolidação de Alertas e Recomendações", styles["secao_titulo"]))
    elements.append(Spacer(1, 6 * mm))

    alertas_consolidados = analise.get("alertas_consolidados", [])
    if alertas_consolidados:
        elements.append(Paragraph("<b>Alertas Prioritários:</b>", styles["corpo"]))
        for i, alerta in enumerate(alertas_consolidados, 1):
            elements.append(Paragraph(f"{i}. {alerta}", styles["corpo"]))
        elements.append(Spacer(1, 6 * mm))

    recomendacoes = analise.get("recomendacoes", [])
    if recomendacoes:
        elements.append(Paragraph("<b>Recomendações de Ação:</b>", styles["corpo"]))
        elements.append(Spacer(1, 3 * mm))

        header = [
            Paragraph("<b>Área</b>", styles["corpo_small"]),
            Paragraph("<b>Ação</b>", styles["corpo_small"]),
            Paragraph("<b>Impacto</b>", styles["corpo_small"]),
            Paragraph("<b>Prazo</b>", styles["corpo_small"]),
        ]
        table_data = [header]
        for rec in recomendacoes:
            if isinstance(rec, dict):
                row = [
                    Paragraph(str(rec.get("area", "")), styles["corpo_small"]),
                    Paragraph(str(rec.get("acao", "")), styles["corpo_small"]),
                    Paragraph(str(rec.get("impacto", "")), styles["corpo_small"]),
                    Paragraph(str(rec.get("prazo", "")), styles["corpo_small"]),
                ]
            else:
                row = [Paragraph(str(rec), styles["corpo_small"])] * 4
            table_data.append(row)

        col_widths = [2.5 * cm, 8.5 * cm, 2.5 * cm, 3 * cm]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COR_FUNDO_CLARO]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(tbl)

    elements.append(PageBreak())

    # === PÁGINA 12: NOTAS METODOLÓGICAS ===
    elements.append(Paragraph("Notas Metodológicas", styles["secao_titulo"]))
    elements.append(Spacer(1, 6 * mm))

    notas = [
        "<b>Fonte dos dados:</b> Banco de dados MySQL de produção, tabelas: os, os_servicos, servicos, "
        "concessionarias, funcionarios. Pagamentos verificados via EXISTS na tabela caixas.",
        "<b>Granularidade:</b> Cada linha do dataset representa 1 serviço dentro de 1 OS (relação 1:N). "
        "Uma OS com 3 serviços gera 3 registros.",
        "<b>Filtros aplicados:</b> os.deleted_at IS NULL (exclui cancelados), os.created_at >= 2023-01-01, "
        "oss_valor_venda_real > 0 (exclui serviços zerados).",
        "<b>Coluna os_paga:</b> Derivada via EXISTS(SELECT 1 FROM caixas cx WHERE cx.os_id = os.id AND "
        "cx.cancelado = 0 AND cx.deleted_at IS NULL). Não equivale necessariamente a inadimplência — "
        "valores 0 podem incluir OS em processamento, cortesia ou cancelamento operacional.",
        "<b>Cross-selling:</b> Baseado em qtd_servicos (COUNT de serviços por OS). "
        "OS com qtd_servicos >= 2 classificada como multi-item.",
        "<b>Outliers:</b> Distribuições com média > 1.5× mediana indicam cauda longa. "
        "Nestes casos, a mediana é reportada como referência principal para 'ticket típico'.",
        "<b>Tratamento de datas:</b> created_at normalizado para datetime sem timezone.",
        f"<b>Geração:</b> Relatório gerado automaticamente em {data_geracao} pelo agente_analise_os, "
        "orquestrado pelo Maestro.",
    ]
    for nota in notas:
        elements.append(Paragraph(nota, styles["corpo"]))
        elements.append(Spacer(1, 3 * mm))

    doc.build(elements)

    abs_path = os.path.abspath(out_path)
    return abs_path
