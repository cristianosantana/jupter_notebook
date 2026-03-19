"""
PDF ~14 páginas: capa, sumário, S1–S12 (texto + gráfico), consolidação, notas.
Reutiliza helpers do relatório agente-analise-os via importlib.
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.platypus import NextPageTemplate, PageBreak, Paragraph, Spacer

_BASE = Path(__file__).resolve().parent.parent / "agente-analise-os" / "relatorio.py"
_spec = importlib.util.spec_from_file_location("_rel_os_base_conc", _BASE)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

_styles = _mod._styles
_header_footer = _mod._header_footer
_capa_header_footer = _mod._capa_header_footer
_secao_page = _mod._secao_page
PAGE_W = _mod.PAGE_W
PAGE_H = _mod.PAGE_H
MARGIN = _mod.MARGIN
CONTENT_W = _mod.CONTENT_W
COR_PRIMARIA = _mod.COR_PRIMARIA
COR_FUNDO_CLARO = _mod.COR_FUNDO_CLARO
ALERTA_CORES = _mod.ALERTA_CORES

Frame = _mod.Frame
BaseDocTemplate = _mod.BaseDocTemplate
PageTemplate = _mod.PageTemplate


def gerar_relatorio_pdf(
    analise: Dict[str, Any],
    graficos: Dict[str, str],
    out_path: str = "output/relatorio_concessionaria.pdf",
    titulo: str = "Relatório — Análise de Concessionária",
    subtitulo: Optional[str] = None,
    periodo: Optional[str] = None,
) -> str:
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
    data_geracao = datetime.now().strftime("%d/%m/%Y às %H:%M")

    elements.append(Spacer(1, 5 * cm))
    elements.append(Paragraph(titulo, styles["titulo_capa"]))
    if subtitulo:
        elements.append(Paragraph(subtitulo, styles["subtitulo_capa"]))
    if periodo:
        elements.append(Spacer(1, 1 * cm))
        elements.append(Paragraph(f"Período: {periodo}", styles["subtitulo_capa"]))
    elements.append(Spacer(1, 2 * cm))
    elements.append(Paragraph(f"Gerado em {data_geracao}", styles["corpo"]))
    elements.append(Paragraph("Agente: agente-analise-concessionaria | Maestro", styles["corpo"]))
    elements.append(NextPageTemplate("conteudo"))
    elements.append(PageBreak())

    elementos_sumario = [
        ("S1", "Resumo executivo"), ("S2", "Séries temporais"), ("S3", "Sazonalidade"),
        ("S4", "Distribuição de tickets"), ("S5", "Mix de serviços"), ("S6", "Tração de serviços"),
        ("S7", "Performance vendedoras"), ("S8", "Troca de time"), ("S9", "Picos e anomalias"),
        ("S10", "Projeção faturamento"), ("S11", "Projeção volume"), ("S12", "Plano de ação"),
        ("—", "Consolidação"), ("—", "Notas"),
    ]
    elements.append(Paragraph("Sumário", styles["secao_titulo"]))
    elements.append(Spacer(1, 8 * mm))
    for cod, nome in elementos_sumario:
        alerta_key = f"{cod}_alerta" if cod.startswith("S") else None
        nivel = analise.get(alerta_key, "") if alerta_key else ""
        cor_dot = ALERTA_CORES.get(nivel, colors.HexColor("#d1d5db"))
        hex_c = cor_dot.hexval() if hasattr(cor_dot, "hexval") else str(cor_dot)
        elements.append(Paragraph(
            f'<font color="{hex_c}">●</font>  <b>{cod}</b> — {nome}',
            styles["sumario_item"],
        ))
    elements.append(PageBreak())

    secoes_config = [
        ("S1 — Resumo executivo", "S1_resumo_executivo", "S1_alerta", "g1"),
        ("S2 — Séries temporais", "S2_serie_temporal", "S2_alerta", "g2"),
        ("S3 — Sazonalidade", "S3_sazonalidade", "S3_alerta", "g3"),
        ("S4 — Distribuição de tickets", "S4_distribuicao_tickets", "S4_alerta", "g4"),
        ("S5 — Mix de serviços", "S5_mix_servicos", "S5_alerta", "g5"),
        ("S6 — Tração de serviços", "S6_tencao_servicos", "S6_alerta", "g6"),
        ("S7 — Performance vendedoras", "S7_performance_vendedoras", "S7_alerta", "g7"),
        ("S8 — Impacto troca vendedoras", "S8_impacto_troca_vendedoras", "S8_alerta", "g8"),
        ("S9 — Picos e anomalias", "S9_picos_anomalias", "S9_alerta", "g9"),
        ("S10 — Projeção faturamento", "S10_projecao_faturamento", "S10_alerta", "g10"),
        ("S11 — Projeção volume", "S11_projecao_volume", "S11_alerta", "g11"),
    ]

    for titulo_sec, chave_texto, chave_alerta, chave_graf in secoes_config:
        texto = analise.get(chave_texto, "Análise não disponível.")
        nivel = analise.get(chave_alerta, "normal")
        img = graficos.get(chave_graf)
        _secao_page(elements, titulo_sec, str(texto), nivel, img, styles)

    s12_texto = analise.get("S12_texto_plano", "") or ""
    pl = analise.get("S12_plano_acao")
    if isinstance(pl, dict):
        s12_texto += "\n\n" + json.dumps(pl, ensure_ascii=False, indent=2)
    nivel12 = analise.get("S12_alerta", "normal")
    _secao_page(elements, "S12 — Plano de ação", s12_texto.strip() or "—", nivel12, graficos.get("g12"), styles)

    elements.append(Paragraph("Consolidação de alertas e recomendações", styles["secao_titulo"]))
    elements.append(Spacer(1, 6 * mm))
    alertas = analise.get("alertas_consolidados") or []
    for i, a in enumerate(alertas, 1):
        elements.append(Paragraph(f"{i}. {a}", styles["corpo"]))
    recs = analise.get("recomendacoes") or []
    if recs:
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph("<b>Recomendações:</b>", styles["corpo"]))
        for rec in recs:
            if isinstance(rec, dict):
                elements.append(Paragraph(
                    f"{rec.get('area', '')}: {rec.get('acao', '')} ({rec.get('prazo', '')})",
                    styles["corpo"],
                ))
    elements.append(PageBreak())

    elements.append(Paragraph("Notas metodológicas", styles["secao_titulo"]))
    notas = [
        "Análise profunda de uma concessionária; dados em granularidade linha=serviço.",
        "Faturamento: oss_valor_venda_real. Datas: created_at.",
        "Janelas móveis relativas à última data no dataset.",
        "double_window compara períodos recente vs base conforme executor.",
        "Projeções S10–S11 são interpretativas na FASE 2.",
    ]
    for n in notas:
        elements.append(Paragraph(n, styles["corpo"]))
        elements.append(Spacer(1, 3 * mm))

    doc.build(elements)
    return os.path.abspath(out_path)
