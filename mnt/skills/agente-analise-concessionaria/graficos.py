"""
Gráficos G1–G12 para relatório de concessionária única.
Reutiliza estilo do agente-analise-os via import do wrapper.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

import importlib.util

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_GOSPEC = importlib.util.spec_from_file_location(
    "_graficos_os_ref",
    Path(__file__).resolve().parent.parent / "agente-analise-os" / "graficos.py",
)
_GOMOD = importlib.util.module_from_spec(_GOSPEC)
assert _GOSPEC.loader
_GOSPEC.loader.exec_module(_GOMOD)

COLOR_ACCENT = _GOMOD.COLOR_ACCENT
COLOR_DANGER = _GOMOD.COLOR_DANGER
COLOR_PRIMARY = _GOMOD.COLOR_PRIMARY
COLOR_SECONDARY = _GOMOD.COLOR_SECONDARY
COLORS_TOP = _GOMOD.COLORS_TOP
FIG_DPI = _GOMOD.FIG_DPI
STYLE = _GOMOD.STYLE
_brl = _GOMOD._brl
_ensure_dir = _GOMOD._ensure_dir
_filtrar = _GOMOD._filtrar

plt.style.use(STYLE)


def _placeholder(path: str, titulo: str, msg: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=11)
    ax.set_title(titulo)
    ax.axis("off")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def grafico_g1_resumo_kpis(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    df = _filtrar(df)
    path = str(_ensure_dir(out_dir) / "g1_resumo.png")
    if df.empty:
        _placeholder(path, "G1", "Sem dados")
        return path
    fat = df["oss_valor_venda_real"].sum()
    t_m = df["oss_valor_venda_real"].mean()
    t_md = df["oss_valor_venda_real"].median()
    n_os = df["id"].nunique() if "id" in df.columns else len(df)
    pag = float(df.groupby("id")["os_paga"].first().mean()) if "id" in df.columns and "os_paga" in df.columns else 0
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    fig.suptitle("G1 — Resumo executivo", fontsize=14, fontweight="bold", y=1.02)
    kpis = [
        ("Faturamento", _brl(fat), COLOR_PRIMARY),
        ("Ticket méd / med", f"{_brl(t_m)}\n{_brl(t_md)}", COLOR_SECONDARY),
        ("OS únicas", str(int(n_os)), COLOR_ACCENT),
        ("% OS pagas", f"{pag * 100:.1f}%", COLOR_PRIMARY),
    ]
    for ax, (titulo, valor, cor) in zip(axes, kpis):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.text(0.5, 0.55, valor, ha="center", va="center", fontsize=14, fontweight="bold", color=cor)
        ax.text(0.5, 0.2, titulo, ha="center", va="center", fontsize=10, color="#374151")
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0.05, 0.05), 0.9, 0.9, fill=False, edgecolor=cor, lw=2, transform=ax.transAxes))
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_g2_series_dw_m(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    df = _filtrar(df)
    path = str(_ensure_dir(out_dir) / "g2_series.png")
    if "created_at" not in df.columns:
        _placeholder(path, "G2", "created_at ausente")
        return path
    d = df.set_index(pd.to_datetime(df["created_at"], errors="coerce")).sort_index()
    d = d[d.index.notna()]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4))
    last = d.index.max()
    if pd.isna(last):
        _placeholder(path, "G2", "Sem datas")
        return path
    d90 = d[d.index >= last - pd.Timedelta(days=90)]
    ser_d = d90["oss_valor_venda_real"].resample("D").sum()
    axes[0].plot(ser_d.index, ser_d.values, color=COLOR_PRIMARY)
    axes[0].axhline(ser_d.median(), color=COLOR_DANGER, ls="--", alpha=0.7)
    axes[0].set_title("Diária (90d)")
    ser_w = d["oss_valor_venda_real"].resample("W").sum()
    axes[1].plot(range(len(ser_w)), ser_w.values, color=COLOR_SECONDARY)
    axes[1].axhline(ser_w.median(), color=COLOR_DANGER, ls="--", alpha=0.7)
    axes[1].set_title("Semanal (histórico)")
    ser_m = d["oss_valor_venda_real"].resample("ME").sum()
    axes[2].plot(range(len(ser_m)), ser_m.values, color=COLOR_ACCENT)
    axes[2].axhline(ser_m.median(), color=COLOR_DANGER, ls="--", alpha=0.7)
    axes[2].set_title("Mensal (histórico)")
    fig.suptitle("G2 — Séries de faturamento")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_g3_sazonalidade(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    df = _filtrar(df)
    path = str(_ensure_dir(out_dir) / "g3_sazonalidade.png")
    if "created_at" not in df.columns:
        _placeholder(path, "G3", "Sem created_at")
        return path
    t = pd.to_datetime(df["created_at"], errors="coerce")
    df = df.assign(_dow=t.dt.dayofweek, _h=t.dt.hour)
    pivot = df.pivot_table(values="oss_valor_venda_real", index="_h", columns="_dow", aggfunc="sum", fill_value=0)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    im = axes[0].imshow(pivot.values, aspect="auto", cmap="YlOrRd")
    axes[0].set_title("Heatmap hora × dia da semana")
    plt.colorbar(im, ax=axes[0], fraction=0.046)
    m = df.groupby(df["created_at"].dt.month)["oss_valor_venda_real"].sum()
    axes[1].bar(m.index.astype(str), m.values, color=COLOR_PRIMARY)
    axes[1].set_title("Faturamento por mês do ano")
    fig.suptitle("G3 — Sazonalidade")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_g4_distribuicao_ticket(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    df = _filtrar(df)
    path = str(_ensure_dir(out_dir) / "g4_distribuicao.png")
    v = df["oss_valor_venda_real"].dropna()
    if v.empty:
        _placeholder(path, "G4", "Sem valores")
        return path
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(v.clip(upper=v.quantile(0.99)), bins=40, color=COLOR_PRIMARY, alpha=0.85)
    ax.axvline(v.median(), color=COLOR_DANGER, label="mediana")
    ax.axvline(v.quantile(0.95), color=COLOR_SECONDARY, label="P95")
    ax.legend()
    ax.set_title("G4 — Distribuição de tickets (clip P99)")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_g5_mix_servicos(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    df = _filtrar(df)
    path = str(_ensure_dir(out_dir) / "g5_mix.png")
    if "servico_nome" not in df.columns:
        _placeholder(path, "G5", "servico_nome ausente")
        return path
    top = df.groupby("servico_nome")["oss_valor_venda_real"].agg(["count", "sum"]).nlargest(10, "sum")
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(top))
    ax.barh(x - 0.2, top["count"] / top["count"].max(), 0.4, label="vol norm", color=COLOR_PRIMARY)
    ax.barh(x + 0.2, top["sum"] / top["sum"].max(), 0.4, label="fat norm", color=COLOR_SECONDARY)
    ax.set_yticks(x)
    ax.set_yticklabels(top.index.str[:32])
    ax.legend()
    ax.set_title("G5 — Top 10 serviços (volume vs faturamento normalizados)")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_g6_tracao_placeholder(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    path = str(_ensure_dir(out_dir) / "g6_tracao.png")
    _placeholder(path, "G6 — Tração serviços", "Use métricas double_window da FASE 1 para nuances")
    return path


def grafico_g7_vendedoras(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    df = _filtrar(df)
    path = str(_ensure_dir(out_dir) / "g7_vendedoras.png")
    if "vendedor_nome" not in df.columns:
        _placeholder(path, "G7", "vendedor_nome ausente")
        return path
    top = df.groupby("vendedor_nome")["oss_valor_venda_real"].sum().nlargest(8)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(top.index.str[:28], top.values, color=COLORS_TOP[: len(top)])
    ax.set_title("G7 — Top vendedoras (faturamento)")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_g8_troca_time(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    path = str(_ensure_dir(out_dir) / "g8_troca.png")
    _placeholder(path, "G8 — Impacto troca vendedoras", "Inferência por janelas 90d — ver FASE 2")
    return path


def grafico_g9_anomalias_serie_m(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    df = _filtrar(df)
    path = str(_ensure_dir(out_dir) / "g9_anomalias.png")
    if "created_at" not in df.columns:
        _placeholder(path, "G9", "Sem datas")
        return path
    s = df.set_index(pd.to_datetime(df["created_at"], errors="coerce"))["oss_valor_venda_real"].resample("ME").sum()
    s = s.dropna()
    med = s.median()
    mad = (s - med).abs().median()
    up = med + 2 * (1.4826 * mad if mad > 0 else mad)
    low = med - 2 * (1.4826 * mad if mad > 0 else mad)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(s.index, s.values, "o-", color=COLOR_PRIMARY)
    ax.axhline(up, color=COLOR_DANGER, ls="--", alpha=0.8)
    ax.axhline(low, color=COLOR_SECONDARY, ls="--", alpha=0.8)
    ax.fill_between(s.index, low, up, alpha=0.15, color=COLOR_ACCENT)
    ax.set_title("G9 — Série mensal com banda mediana ± 2×MAD")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def grafico_g10_projecao_placeholder(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    path = str(_ensure_dir(out_dir) / "g10_projecao_fat.png")
    _placeholder(path, "G10 — Projeção faturamento", "Cenários na FASE 2 (P10/mediana/P90)")
    return path


def grafico_g11_volume_placeholder(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    path = str(_ensure_dir(out_dir) / "g11_projecao_vol.png")
    _placeholder(path, "G11 — Projeção volume", "Volume mensal na FASE 1")
    return path


def grafico_g12_plano_acao(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> str:
    path = str(_ensure_dir(out_dir) / "g12_plano.png")
    _placeholder(path, "G12 — Plano de ação", "Matriz textual em S12_plano_acao (FASE 2)")
    return path


def gerar_todos_graficos(df: pd.DataFrame, out_dir: str = "output/graficos_conc") -> Dict[str, str]:
    """Gera os 12 PNGs; retorna mapa chave lógica → caminho."""
    funcs = [
        ("g1", grafico_g1_resumo_kpis),
        ("g2", grafico_g2_series_dw_m),
        ("g3", grafico_g3_sazonalidade),
        ("g4", grafico_g4_distribuicao_ticket),
        ("g5", grafico_g5_mix_servicos),
        ("g6", grafico_g6_tracao_placeholder),
        ("g7", grafico_g7_vendedoras),
        ("g8", grafico_g8_troca_time),
        ("g9", grafico_g9_anomalias_serie_m),
        ("g10", grafico_g10_projecao_placeholder),
        ("g11", grafico_g11_volume_placeholder),
        ("g12", grafico_g12_plano_acao),
    ]
    out: Dict[str, str] = {}
    for key, fn in funcs:
        out[key] = fn(df, out_dir=out_dir)
    return out
