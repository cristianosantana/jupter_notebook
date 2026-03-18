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


def grafico_s1_resumo_executivo(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
) -> str:
    """S1 - Cards de KPIs principais + mini barras comparando 7d vs 14d."""
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
    fig.suptitle("S1 — Resumo Executivo", fontsize=14, fontweight="bold", y=1.02)

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
    """S2 - Top concessionárias por faturamento, ticket e volume."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s2_concessionarias.png")

    if "concessionaria_nome" not in df.columns:
        _placeholder(path, "S2 — Concessionárias", "Coluna concessionaria_nome ausente")
        return path

    grp = df.groupby("concessionaria_nome")["oss_valor_venda_real"]
    fat = grp.sum().nlargest(top_n).sort_values()
    ticket = grp.mean().nlargest(top_n).sort_values()
    vol = grp.count().nlargest(top_n).sort_values()

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("S2 — Faturamento e Ticket por Concessionária", fontsize=14, fontweight="bold", y=1.02)

    axes[0].barh(fat.index, fat.values, color=COLOR_PRIMARY)
    axes[0].set_title(f"Top {top_n} Faturamento")
    axes[0].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    axes[1].barh(ticket.index, ticket.values, color=COLOR_SECONDARY)
    axes[1].set_title(f"Top {top_n} Ticket Médio")
    axes[1].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    axes[2].barh(vol.index, vol.values, color=COLOR_ACCENT)
    axes[2].set_title(f"Top {top_n} Volume (Serviços)")

    for ax in axes:
        ax.tick_params(axis="y", labelsize=8)

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s3_sazonalidade(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
) -> str:
    """S3 - Séries temporais mensais/semanais + heatmap hora x dia."""
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
    fig.suptitle("S3 — Sazonalidade", fontsize=14, fontweight="bold", y=1.02)

    # Série mensal de volume
    mensal_vol = df.groupby("mes").size()
    axes[0, 0].plot(mensal_vol.index, mensal_vol.values, marker="o", color=COLOR_PRIMARY, lw=2)
    axes[0, 0].set_title("Volume Mensal (Serviços)")
    axes[0, 0].tick_params(axis="x", rotation=45)

    # Série mensal de faturamento
    mensal_fat = df.groupby("mes")["oss_valor_venda_real"].sum()
    ax_fat = axes[0, 1]
    ax_fat.fill_between(mensal_fat.index, mensal_fat.values, alpha=0.3, color=COLOR_SECONDARY)
    ax_fat.plot(mensal_fat.index, mensal_fat.values, marker="o", color=COLOR_SECONDARY, lw=2)
    ax_fat.set_title("Faturamento Mensal")
    ax_fat.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))
    ax_fat.tick_params(axis="x", rotation=45)

    # Volume por dia da semana
    dias_ordem = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dia_vol = df["dia_semana"].value_counts().reindex(dias_ordem).fillna(0)
    axes[1, 0].bar(range(len(dia_vol)), dia_vol.values, color="skyblue", edgecolor="navy")
    axes[1, 0].set_xticks(range(len(dia_vol)))
    axes[1, 0].set_xticklabels(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"], fontsize=9)
    axes[1, 0].set_title("Volume por Dia da Semana")

    # Heatmap hora x dia
    if len(df) > 0:
        pivot = df.pivot_table(index="hora", columns="dia_semana", values="oss_valor_venda_real", aggfunc="count")
        pivot = pivot.reindex(columns=dias_ordem).fillna(0)
        pivot.columns = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        sns.heatmap(pivot, annot=True, fmt=".0f", cmap=CMAP, ax=axes[1, 1], cbar_kws={"label": "Qtd"})
        axes[1, 1].set_title("Intensidade: Hora × Dia da Semana")

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s4_produtos(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
    top_n: int = 15,
) -> str:
    """S4 - Top serviços por volume, faturamento e ticket médio."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s4_produtos.png")

    if "servico_nome" not in df.columns:
        _placeholder(path, "S4 — Produtos", "Coluna servico_nome ausente")
        return path

    grp = df.groupby("servico_nome")["oss_valor_venda_real"]
    vol = grp.count().nlargest(top_n).sort_values()
    fat = grp.sum().nlargest(top_n).sort_values()
    ticket = grp.mean().nlargest(top_n).sort_values()

    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    fig.suptitle("S4 — Produtos e Serviços", fontsize=14, fontweight="bold", y=1.02)

    axes[0].barh(vol.index, vol.values, color="teal")
    axes[0].set_title(f"Top {top_n} por Volume")

    axes[1].barh(fat.index, fat.values, color="purple")
    axes[1].set_title(f"Top {top_n} por Faturamento")
    axes[1].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    axes[2].barh(ticket.index, ticket.values, color=COLOR_SECONDARY)
    axes[2].set_title(f"Top {top_n} por Ticket Médio")
    axes[2].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    for ax in axes:
        ax.tick_params(axis="y", labelsize=7)

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s5_vendedores(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
    top_n: int = 10,
) -> str:
    """S5 - Top vendedores + histograma de distribuição de ticket."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s5_vendedores.png")

    if "vendedor_nome" not in df.columns:
        _placeholder(path, "S5 — Vendedores", "Coluna vendedor_nome ausente")
        return path

    grp = df.groupby("vendedor_nome")["oss_valor_venda_real"]
    fat = grp.sum().nlargest(top_n).sort_values()
    vol = grp.count().nlargest(top_n).sort_values()

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("S5 — Performance de Vendedores", fontsize=14, fontweight="bold", y=1.02)

    axes[0].barh(fat.index, fat.values, color="darkblue")
    axes[0].set_title(f"Top {top_n} por Faturamento")
    axes[0].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    axes[1].barh(vol.index, vol.values, color="green")
    axes[1].set_title(f"Top {top_n} por Volume")

    ticket_vendedor = grp.mean().dropna()
    axes[2].hist(ticket_vendedor.values, bins=min(20, len(ticket_vendedor)), color=COLOR_PRIMARY, edgecolor="white")
    if len(ticket_vendedor) > 0:
        media = ticket_vendedor.mean()
        axes[2].axvline(media, color=COLOR_DANGER, linestyle="--", lw=2, label=f"Média: {_brl(media)}")
        axes[2].legend()
    axes[2].set_title("Distribuição de Ticket por Vendedor")

    for ax in axes[:2]:
        ax.tick_params(axis="y", labelsize=8)

    plt.tight_layout()
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_s6_distribuicao_tickets(
    df: pd.DataFrame,
    out_dir: str = "output/graficos",
) -> str:
    """S6 - Histograma, boxplot e faixas de preço."""
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

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("S6 — Distribuição de Tickets", fontsize=14, fontweight="bold", y=1.02)

    # Histograma geral
    axes[0, 0].hist(vals, bins=50, color=COLOR_PRIMARY, edgecolor="white", alpha=0.8)
    axes[0, 0].axvline(media, color=COLOR_DANGER, ls="--", lw=2, label=f"Média: {_brl(media)}")
    axes[0, 0].axvline(mediana, color=COLOR_ACCENT, ls="-", lw=2, label=f"Mediana: {_brl(mediana)}")
    axes[0, 0].legend(fontsize=8)
    axes[0, 0].set_title("Distribuição Geral")

    # Histograma até P95 (sem outliers)
    vals_p95 = vals[vals <= p95]
    axes[0, 1].hist(vals_p95, bins=40, color=COLOR_SECONDARY, edgecolor="white", alpha=0.8)
    axes[0, 1].axvline(mediana, color=COLOR_ACCENT, ls="-", lw=2, label=f"Mediana: {_brl(mediana)}")
    axes[0, 1].set_title(f"Até P95 ({_brl(p95)})")
    axes[0, 1].legend(fontsize=8)

    # Boxplot
    bp = axes[1, 0].boxplot(vals, vert=False, widths=0.6, patch_artist=True,
                            boxprops=dict(facecolor=COLOR_PRIMARY, alpha=0.5))
    axes[1, 0].set_title("Boxplot")
    axes[1, 0].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _brl(x)))

    # Faixas de preço
    bins_faixa = [0, 100, 250, 500, 1000, 2000, 5000, float("inf")]
    labels_faixa = ["0-100", "100-250", "250-500", "500-1K", "1K-2K", "2K-5K", "5K+"]
    df_temp = pd.DataFrame({"val": vals})
    df_temp["faixa"] = pd.cut(df_temp["val"], bins=bins_faixa, labels=labels_faixa, right=False)
    faixa_counts = df_temp["faixa"].value_counts().reindex(labels_faixa).fillna(0)
    axes[1, 1].bar(faixa_counts.index, faixa_counts.values, color="lightcoral", edgecolor="darkred")
    axes[1, 1].set_title("Distribuição por Faixa de Preço")
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
    """S7 - Cross-selling: single vs multi-item (baseado em qtd_servicos)."""
    df = _filtrar(df)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "s7_cross_selling.png")

    if "qtd_servicos" not in df.columns:
        _placeholder(path, "S7 — Cross-Selling", "Coluna qtd_servicos ausente")
        return path

    df = df.copy()
    df["tipo_os"] = np.where(df["qtd_servicos"] >= 2, "Multi-item", "Single-item")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle("S7 — Cross-Selling (Single vs Multi-item)", fontsize=14, fontweight="bold", y=1.02)

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
    """S8 - Heatmap de alertas: top concessionárias com métricas normalizadas."""
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
    fig.suptitle("S8 — Alertas e Anomalias", fontsize=14, fontweight="bold", y=1.02)

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
