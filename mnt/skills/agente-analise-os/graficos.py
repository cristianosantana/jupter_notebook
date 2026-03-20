"""
Geração de gráficos PNG para o relatório semanal de OS.

Cada função recebe um DataFrame (1 linha = 1 serviço dentro de 1 OS)
com colunas prefixadas e retorna o caminho do PNG salvo.

Colunas esperadas (prefixadas):
  os.*             -> sem prefixo (id, created_at, cancelada, paga, os_paga, qtd_servicos ...)
  os_servicos      -> oss_ (oss_valor_venda_real, oss_cancelado, oss_servico_id ...)
  servicos         -> servico_nome, ser_id, ser_grupo_servico_id ...
  concessionarias  -> concessionaria_nome, con_uf, con_localidade ...
  funcionarios     -> vendedor_nome, func_id ...
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

STYLE = "seaborn-v0_8-darkgrid"
CMAP = "YlOrRd"
COLOR_PRIMARY = "#2563eb"
COLOR_SECONDARY = "#f97316"
COLOR_ACCENT = "#10b981"
COLOR_DANGER = "#ef4444"
COLORS_TOP = [
    "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd", "#bfdbfe",
    "#f97316", "#fb923c", "#fdba74", "#fed7aa", "#ffedd5",
]
FIG_DPI = 150


def _ensure_dir(out_dir: str) -> Path:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _filtrar(df: pd.DataFrame) -> pd.DataFrame:
    """Remove serviços com valor zero ou nulo."""
    mask = df["oss_valor_venda_real"].gt(0) & df["oss_valor_venda_real"].notna()
    return df.loc[mask].copy()


def _periodo_analise_caption(df: pd.DataFrame) -> Optional[str]:
    """Legenda com intervalo de datas do extract (min–max), para gráficos."""
    for col in ("created_at", "oss_created_at"):
        if col not in df.columns:
            continue
        ts = pd.to_datetime(df[col], errors="coerce").dropna()
        if ts.empty:
            continue
        d0 = ts.min().strftime("%d/%m/%Y")
        d1 = ts.max().strftime("%d/%m/%Y")
        return f"Período de análise: {d0} a {d1}"
    return None


def _fig_suptitle_com_periodo(
    fig,
    df: pd.DataFrame,
    *linhas_titulo: str,
    y: float = 1.02,
    fontsize: int = 11,
) -> None:
    """Suptitle: linhas fixas + período (ou aviso se não houver data no DataFrame)."""
    periodo = _periodo_analise_caption(df)
    sufixo = periodo if periodo else "(Período: data não disponível.)"
    texto = "\n".join([*linhas_titulo, sufixo])
    fig.suptitle(texto, fontsize=fontsize, fontweight="bold", y=y)


def grafico_s1_resumo_executivo(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
) -> str:
    """S1 - KPIs; suptitle com período de análise."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s1_resumo_executivo.png")

    total_servicos = len(df)
    fat_total = df["oss_valor_venda_real"].sum()
    ticket_medio = df["oss_valor_venda_real"].mean()
    ticket_mediana = df["oss_valor_venda_real"].median()
    n_conc = df["concessionaria_nome"].nunique() if "concessionaria_nome" in df.columns else 0
    n_pagas = df["os_paga"].sum() if "os_paga" in df.columns else 0
    n_nao_pagas = (df["os_paga"] == 0).sum() if "os_paga" in df.columns else 0

    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    _fig_suptitle_com_periodo(fig, df, "S1 — Resumo Executivo", y=1.12, fontsize=11)

    kpis = [
        ("Serviços Válidos", f"{total_servicos:,}".replace(",", "."), COLOR_PRIMARY),
        ("Faturamento Total", _brl(fat_total), COLOR_SECONDARY),
        ("Ticket Médio / Mediana", f"{_brl(ticket_medio)}\n{_brl(ticket_mediana)}", COLOR_ACCENT),
        ("Concessionárias Ativas", str(n_conc), COLOR_PRIMARY),
    ]
    for ax, (titulo, valor, cor) in zip(axes, kpis):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.text(0.5, 0.65, valor, ha="center", va="center", fontsize=16, fontweight="bold", color=cor)
        ax.text(0.5, 0.25, titulo, ha="center", va="center", fontsize=10, color="#374151")
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0.05, 0.05), 0.9, 0.9, fill=False, edgecolor=cor, lw=2, transform=ax.transAxes))

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s2_concessionarias(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
    top_n: int = 10,
) -> str:
    """S2 - Top concessionárias; suptitle com período."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s2_concessionarias.png")

    if "concessionaria_nome" not in df.columns:
        _placeholder(path, "S2 — Concessionárias", "Coluna concessionaria_nome ausente")
        return path

    grp = df.groupby("concessionaria_nome")["oss_valor_venda_real"]
    fat = grp.sum().nlargest(top_n).sort_values(ascending=False)
    ticket = grp.mean().nlargest(top_n).sort_values(ascending=False)

    # Volume: média de serviços por OS por concessionária (ordem de grandeza ~unidades, não centenas de linhas)
    tem_id_os = "id" in df.columns
    if tem_id_os:
        n_servicos_por_os = df.groupby(["concessionaria_nome", "id"], observed=True).size()
        vol_media_por_conc = n_servicos_por_os.groupby(level=0).mean()
        vol = vol_media_por_conc.nlargest(top_n).sort_values(ascending=False)
    else:
        vol = grp.count().nlargest(top_n).sort_values(ascending=False)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    _fig_suptitle_com_periodo(
        fig, df, "S2 — Faturamento e Ticket por Concessionária", y=1.06, fontsize=11
    )

    def _bar_conc_vertical(ax, series, color: str, y_formatter=None, ylabel: str = ""):
        x_pos = np.arange(len(series))
        ax.bar(x_pos, series.values, color=color)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(series.index, rotation=90, ha="center", va="top", fontsize=7)
        ax.set_xlabel("Concessionária")
        if ylabel:
            ax.set_ylabel(ylabel)
        if y_formatter:
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(y_formatter))

    _bar_conc_vertical(
        axes[0], fat, COLOR_PRIMARY, lambda x, _: _brl(x), "Faturamento"
    )
    axes[0].set_title(f"Top {top_n} Faturamento")

    _bar_conc_vertical(
        axes[1], ticket, COLOR_SECONDARY, lambda x, _: _brl(x), "Ticket médio"
    )
    axes[1].set_title(f"Top {top_n} Ticket Médio")

    vol_fmt = (lambda x, _: f"{x:.1f}".replace(".", ",")) if tem_id_os else None
    vol_ylabel = "Média serviços / OS" if tem_id_os else "Qtd. linhas (serviços)"
    vol_title = (
        f"Top {top_n} média serviços por OS"
        if tem_id_os
        else f"Top {top_n} Volume (Serviços)"
    )
    _bar_conc_vertical(axes[2], vol, COLOR_ACCENT, vol_fmt, vol_ylabel)
    axes[2].set_title(vol_title)

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s3_sazonalidade(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
) -> str:
    """S3 - Sazonalidade: volume = contagem de linhas de serviço (1 linha = 1 item na OS); faturamento = soma R$."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s3_sazonalidade.png")

    if "created_at" not in df.columns:
        _placeholder(path, "S3 — Sazonalidade", "Coluna created_at ausente")
        return path

    df = df.copy()
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df = df.dropna(subset=["created_at"])
    df["mes"] = df["created_at"].dt.to_period("M").dt.to_timestamp()
    df["dia_semana"] = df["created_at"].dt.day_name()
    df["hora"] = df["created_at"].dt.hour

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    _fig_suptitle_com_periodo(
        fig,
        df,
        "S3 — Sazonalidade",
        "(Volume = qtd. de linhas de serviço na OS; faturamento = soma em R$ — não é qtd. de OS)",
        y=1.05,
        fontsize=10,
    )

    # Série mensal: contagem de linhas de serviço (não número de ordens de serviço)
    mensal_vol = df.groupby("mes").size()
    axes[0, 0].plot(mensal_vol.index, mensal_vol.values, marker="o", color=COLOR_PRIMARY, lw=2)
    axes[0, 0].set_title("Qtd. mensal de serviços\n(1 linha do relatório = 1 item na OS)")
    axes[0, 0].set_ylabel("Linhas de serviço")
    axes[0, 0].tick_params(axis="x", rotation=45)

    # Faturamento em reais
    mensal_fat = df.groupby("mes")["oss_valor_venda_real"].sum()
    ax_fat = axes[0, 1]
    ax_fat.fill_between(mensal_fat.index, mensal_fat.values, alpha=0.3, color=COLOR_SECONDARY)
    ax_fat.plot(mensal_fat.index, mensal_fat.values, marker="o", color=COLOR_SECONDARY, lw=2)
    ax_fat.set_title("Faturamento mensal (R$)\n(soma de oss_valor_venda_real)")
    ax_fat.set_ylabel("R$")
    ax_fat.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))
    ax_fat.tick_params(axis="x", rotation=45)

    dias_ordem = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dia_vol = df["dia_semana"].value_counts().reindex(dias_ordem).fillna(0)
    axes[1, 0].bar(range(len(dia_vol)), dia_vol.values, color="skyblue", edgecolor="navy")
    axes[1, 0].set_xticks(range(len(dia_vol)))
    axes[1, 0].set_xticklabels(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"], fontsize=9)
    axes[1, 0].set_title("Serviços por dia da semana\n(contagem de linhas)")
    axes[1, 0].set_ylabel("Linhas de serviço")

    if len(df) > 0:
        pivot = df.pivot_table(index="hora", columns="dia_semana", values="oss_valor_venda_real", aggfunc="count")
        pivot = pivot.reindex(columns=dias_ordem).fillna(0)
        pivot.columns = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        sns.heatmap(
            pivot,
            annot=True,
            fmt=".0f",
            cmap=CMAP,
            ax=axes[1, 1],
            cbar_kws={"label": "Qtd. linhas de serviço"},
        )
        axes[1, 1].set_title("Hora × dia da semana\n(qtd. de serviços, não R$)")

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s4_produtos(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
    top_n: int = 15,
) -> str:
    """S4 - Top serviços por volume, faturamento e ticket médio; suptitle inclui período (created_at / oss_created_at)."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s4_produtos.png")

    if "servico_nome" not in df.columns:
        _placeholder(path, "S4 — Produtos", "Coluna servico_nome ausente")
        return path

    grp = df.groupby("servico_nome")["oss_valor_venda_real"]
    vol = grp.count().nlargest(top_n).sort_values(ascending=False)
    fat = grp.sum().nlargest(top_n).sort_values(ascending=False)
    ticket = grp.mean().nlargest(top_n).sort_values(ascending=False)

    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    _fig_suptitle_com_periodo(fig, df, "S4 — Produtos e Serviços", y=1.06, fontsize=11)

    def _bar_vertical(ax, series, color: str, y_formatter=None):
        x_pos = np.arange(len(series))
        ax.bar(x_pos, series.values, color=color)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(series.index, rotation=90, ha="center", va="top", fontsize=7)
        ax.set_xlabel("Serviço")
        if y_formatter:
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(y_formatter))

    _bar_vertical(axes[0], vol, "teal")
    axes[0].set_title(f"Top {top_n} por Volume")
    axes[0].set_ylabel("Quantidade")

    _bar_vertical(axes[1], fat, "purple", lambda x, _: _brl(x))
    axes[1].set_title(f"Top {top_n} por Faturamento")
    axes[1].set_ylabel("Faturamento")

    _bar_vertical(axes[2], ticket, COLOR_SECONDARY, lambda x, _: _brl(x))
    axes[2].set_title(f"Top {top_n} por Ticket Médio")
    axes[2].set_ylabel("Ticket médio")

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s5_vendedores(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
    top_n: int = 10,
    min_servicos_ranking_ticket: int = 10,
) -> str:
    """S5 - Top vendedores (faturamento, volume, ticket médio em barras); período no suptitle.

    O ranking de ticket médio só inclui vendedores com pelo menos ``min_servicos_ranking_ticket``
    linhas de serviço (evita outlier com 1 venda). Se ninguém passar no corte, usa todos.
    """
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s5_vendedores.png")

    if "vendedor_nome" not in df.columns:
        _placeholder(path, "S5 — Vendedores", "Coluna vendedor_nome ausente")
        return path

    grp = df.groupby("vendedor_nome")["oss_valor_venda_real"]
    fat = grp.sum().nlargest(top_n).sort_values(ascending=False)
    vol = grp.count().nlargest(top_n).sort_values(ascending=False)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    _fig_suptitle_com_periodo(fig, df, "S5 — Performance de Vendedores", y=1.06, fontsize=11)

    def _bar_vendedor_vertical(ax, series, color: str, y_formatter=None, ylabel: str = ""):
        x_pos = np.arange(len(series))
        ax.bar(x_pos, series.values, color=color)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(series.index, rotation=90, ha="center", va="top", fontsize=7)
        ax.set_xlabel("Vendedor")
        if ylabel:
            ax.set_ylabel(ylabel)
        if y_formatter:
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(y_formatter))

    _bar_vendedor_vertical(
        axes[0], fat, "darkblue", lambda x, _: _brl(x), "Faturamento"
    )
    axes[0].set_title(
        f"Top {top_n} por faturamento\n(soma de oss_valor_venda_real por vendedor)",
        fontsize=10,
    )

    _bar_vendedor_vertical(axes[1], vol, "green", None, "Qtd. serviços")
    axes[1].set_title(
        f"Top {top_n} por volume\n(qtd. de linhas de serviço por vendedor)",
        fontsize=10,
    )

    cnt = grp.count()
    ticket_medio = grp.mean()
    elig = ticket_medio[cnt >= min_servicos_ranking_ticket].dropna()
    ticket_top = (
        elig.nlargest(top_n).sort_values(ascending=False)
        if len(elig) > 0
        else ticket_medio.dropna().nlargest(top_n).sort_values(ascending=False)
    )
    _bar_vendedor_vertical(
        axes[2], ticket_top, COLOR_SECONDARY, lambda x, _: _brl(x), "Ticket médio (R$)"
    )
    sub_ticket = (
        f"(média de oss_valor_venda_real; mín. {min_servicos_ranking_ticket} serviços/vendedor)"
        if len(elig) > 0
        else "(média por vendedor; sem vendedor com volume mínimo — ranking sem corte)"
    )
    axes[2].set_title(f"Top {top_n} por ticket médio\n{sub_ticket}", fontsize=10)

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s6_distribuicao_tickets(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
) -> str:
    """S6 - Histograma, boxplot e faixas; títulos/subtítulos explicam métrica (ticket por linha de serviço)."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s6_distribuicao_tickets.png")

    vals = df["oss_valor_venda_real"].dropna()
    if len(vals) == 0:
        _placeholder(path, "S6 — Distribuição de Tickets", "Sem dados")
        return path

    media = vals.mean()
    mediana = vals.median()
    p25, p75, p95, p99 = vals.quantile([0.25, 0.75, 0.95, 0.99])

    fig, axes = plt.subplots(2, 2, figsize=(14, 11))
    _fig_suptitle_com_periodo(
        fig,
        df,
        "S6 — Distribuição de tickets",
        "Todos os gráficos: 1 linha = 1 serviço na OS (oss_valor_venda_real em R$).",
        "Não é valor total da OS nem quantidade de ordens.",
        y=1.07,
        fontsize=9,
    )

    # Histograma geral
    axes[0, 0].hist(vals, bins=50, color=COLOR_PRIMARY, edgecolor="white", alpha=0.8)
    axes[0, 0].axvline(media, color=COLOR_DANGER, ls="--", lw=2, label=f"Média: {_brl(media)}")
    axes[0, 0].axvline(mediana, color=COLOR_ACCENT, ls="-", lw=2, label=f"Mediana: {_brl(mediana)}")
    axes[0, 0].legend(fontsize=8)
    axes[0, 0].set_title(
        "Histograma — visão completa\n"
        "(eixo X: ticket R$; eixo Y: quantas linhas de serviço caem em cada faixa)",
        fontsize=10,
    )
    axes[0, 0].set_xlabel("Ticket (R$) por linha de serviço")
    axes[0, 0].set_ylabel("Frequência (qtd. linhas)")

    # Histograma até P95 (sem outliers)
    vals_p95 = vals[vals <= p95]
    axes[0, 1].hist(vals_p95, bins=40, color=COLOR_SECONDARY, edgecolor="white", alpha=0.8)
    axes[0, 1].axvline(mediana, color=COLOR_ACCENT, ls="-", lw=2, label=f"Mediana: {_brl(mediana)}")
    axes[0, 1].set_title(
        f"Histograma — até o percentil 95 (P95 = {_brl(p95)})\n"
        "(remove os 5% tickets mais altos para ver o 'miolo' sem cauda longa)",
        fontsize=10,
    )
    axes[0, 1].legend(fontsize=8)
    axes[0, 1].set_xlabel("Ticket (R$)")
    axes[0, 1].set_ylabel("Frequência (qtd. linhas)")

    # Boxplot
    bp = axes[1, 0].boxplot(vals, vert=False, widths=0.6, patch_artist=True,
                            boxprops=dict(facecolor=COLOR_PRIMARY, alpha=0.5))
    axes[1, 0].set_title(
        "Boxplot horizontal\n"
        "(caixa central: 50% dos valores entre P25 e P75; traço = mediana; pontos = outliers)",
        fontsize=10,
    )
    axes[1, 0].set_xlabel("Ticket (R$) por linha de serviço")
    axes[1, 0].set_ylabel("")
    axes[1, 0].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    # Faixas de preço
    bins_faixa = [0, 100, 250, 500, 1000, 2000, 5000, float("inf")]
    labels_faixa = ["0-100", "100-250", "250-500", "500-1K", "1K-2K", "2K-5K", "5K+"]
    df_temp = pd.DataFrame({"val": vals})
    df_temp["faixa"] = pd.cut(df_temp["val"], bins=bins_faixa, labels=labels_faixa, right=False)
    faixa_counts = df_temp["faixa"].value_counts().reindex(labels_faixa).fillna(0)
    axes[1, 1].bar(faixa_counts.index, faixa_counts.values, color="lightcoral", edgecolor="darkred")
    axes[1, 1].set_title(
        "Barras por faixa fixa de preço (R$)\n"
        "(conta quantos serviços estão em 0–100, 100–250, etc.; independente do histograma)",
        fontsize=10,
    )
    axes[1, 1].set_xlabel("Faixa de ticket (R$)")
    axes[1, 1].set_ylabel("Qtd. linhas de serviço")
    axes[1, 1].tick_params(axis="x", rotation=30)

    # Anotações
    texto_perc = f"P25={_brl(p25)}  P75={_brl(p75)}\nP95={_brl(p95)}  P99={_brl(p99)}"
    fig.text(0.5, -0.02, texto_perc, ha="center", fontsize=9, color="#6b7280")

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s7_cross_selling(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
) -> str:
    """S7 - Cross-selling; suptitle com período."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s7_cross_selling.png")

    if "qtd_servicos" not in df.columns:
        _placeholder(path, "S7 — Cross-Selling", "Coluna qtd_servicos ausente")
        return path

    df = df.copy()
    df["tipo_os"] = np.where(df["qtd_servicos"] >= 2, "Multi-item", "Single-item")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    _fig_suptitle_com_periodo(
        fig, df, "S7 — Cross-Selling (Single vs Multi-item)", y=1.08, fontsize=11
    )

    # Proporção
    prop = df["tipo_os"].value_counts()
    axes[0].pie(
        prop.values,
        labels=prop.index,
        autopct="%1.1f%%",
        colors=[COLOR_PRIMARY, COLOR_SECONDARY],
        startangle=90,
    )
    axes[0].set_title("Proporção de Registros")

    # Faturamento por tipo
    fat_tipo = df.groupby("tipo_os")["oss_valor_venda_real"].sum()
    axes[1].bar(fat_tipo.index, fat_tipo.values, color=[COLOR_PRIMARY, COLOR_SECONDARY])
    axes[1].set_title("Faturamento por Tipo")
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    # Ticket médio por tipo
    ticket_tipo = df.groupby("tipo_os")["oss_valor_venda_real"].mean()
    axes[2].bar(ticket_tipo.index, ticket_tipo.values, color=[COLOR_PRIMARY, COLOR_SECONDARY])
    axes[2].set_title("Ticket Médio por Tipo")
    axes[2].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s8_alertas(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
    top_n: int = 20,
) -> str:
    """S8 - Alertas; suptitle com período."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s8_alertas.png")

    if "concessionaria_nome" not in df.columns:
        _placeholder(path, "S8 — Alertas", "Coluna concessionaria_nome ausente")
        return path

    grp = df.groupby("concessionaria_nome")["oss_valor_venda_real"]
    fat = grp.sum()
    vol = grp.count()
    ticket = grp.mean()
    p95_global = df["oss_valor_venda_real"].quantile(0.95)

    top_conc = fat.nlargest(top_n).index
    metricas = pd.DataFrame({
        "Faturamento": fat.reindex(top_conc),
        "Volume": vol.reindex(top_conc),
        "Ticket Médio": ticket.reindex(top_conc),
    })

    fig, axes = plt.subplots(1, 2, figsize=(18, 8), gridspec_kw={"width_ratios": [3, 1]})
    _fig_suptitle_com_periodo(fig, df, "S8 — Alertas e Anomalias", y=1.03, fontsize=11)

    # Heatmap normalizado
    metricas_norm = metricas.apply(lambda s: (s - s.min()) / (s.max() - s.min() + 1e-9))
    sns.heatmap(metricas_norm, annot=metricas.map(lambda x: f"{x:,.0f}"),
                fmt="", cmap=CMAP, ax=axes[0], cbar_kws={"label": "Score normalizado"})
    axes[0].set_title(f"Top {top_n} Concessionárias — Métricas")
    axes[0].tick_params(axis="y", labelsize=8)

    # OS pagas vs não pagas
    if "os_paga" in df.columns:
        pag_conc = df.loc[df["concessionaria_nome"].isin(top_conc)].groupby(
            ["concessionaria_nome", "os_paga"]
        ).size().unstack(fill_value=0)
        pag_conc.columns = ["Sem pagamento", "Com pagamento"]
        pag_conc = pag_conc.reindex(top_conc)
        pag_conc.plot(kind="barh", stacked=True, ax=axes[1], color=[COLOR_DANGER, COLOR_ACCENT])
        axes[1].set_title("Pagamento")
        axes[1].tick_params(axis="y", labelsize=8)
        axes[1].legend(fontsize=7)
    else:
        axes[1].text(0.5, 0.5, "os_paga\nausente", ha="center", va="center", fontsize=12)
        axes[1].axis("off")

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _placeholder(path: str, titulo: str, msg: str) -> None:
    """Gera um PNG placeholder quando dados estão ausentes."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, f"{titulo}\n\n{msg}", ha="center", va="center", fontsize=14, color="#9ca3af")
    ax.axis("off")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def gerar_todos_graficos(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
) -> dict[str, str]:
    """Gera os 8 gráficos e retorna dict {secao: caminho_png}."""
    _ensure_dir(out_dir)
    return {
        "s1": grafico_s1_resumo_executivo(df, out_dir),
        "s2": grafico_s2_concessionarias(df, out_dir),
        "s3": grafico_s3_sazonalidade(df, out_dir),
        "s4": grafico_s4_produtos(df, out_dir),
        "s5": grafico_s5_vendedores(df, out_dir),
        "s6": grafico_s6_distribuicao_tickets(df, out_dir),
        "s7": grafico_s7_cross_selling(df, out_dir),
        "s8": grafico_s8_alertas(df, out_dir),
    }
