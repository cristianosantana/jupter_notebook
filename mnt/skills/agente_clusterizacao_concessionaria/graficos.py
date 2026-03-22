# mnt/skills/agente_clusterizacao_concessionaria/graficos.py
"""Gráficos a partir da resposta FASE 2 + métricas FASE 1; renderização por especificação JSON."""
from __future__ import annotations

import ast
import json
import re
from numbers import Number
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def extrair_json_texto(texto: str) -> Optional[Dict[str, Any]]:
    if not texto or not str(texto).strip():
        return None
    s = str(texto).strip()
    if "```" in s:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
        if m:
            s = m.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def extrair_objeto_json_folheado(texto: str) -> Optional[Dict[str, Any]]:
    """Último recurso: primeiro `{` ao último `}` (modelo com texto antes/depois do JSON)."""
    if not texto or not str(texto).strip():
        return None
    s = str(texto).strip()
    i = s.find("{")
    j = s.rfind("}")
    if i < 0 or j <= i:
        return None
    chunk = s[i : j + 1]
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        return None


def normalizar_resposta_cluster(resp: Any) -> Optional[Dict[str, Any]]:
    if resp is None:
        return None
    if isinstance(resp, dict):
        d = resp
    elif isinstance(resp, str):
        d = extrair_json_texto(resp) or extrair_objeto_json_folheado(resp)
    else:
        return None
    if not isinstance(d, dict):
        return None
    inner = d.get("resposta")
    if isinstance(inner, str):
        inner = extrair_json_texto(inner) or extrair_objeto_json_folheado(inner)
    if isinstance(inner, dict) and (
        "resumo_clustering" in inner
        or "perfis_clusters" in inner
        or "mapeamento_concessionarias" in inner
        or ("objetivo" in inner and "perfis" in inner)
        or "relatorios_concessionarias" in inner
    ):
        return inner
    return d


def resultado_exec_para_dict(ex: Any) -> Dict[str, Any]:
    if isinstance(ex, dict) and "metricas" in ex:
        return ex
    if isinstance(ex, str):
        parsed = extrair_json_texto(ex)
        if isinstance(parsed, dict) and "metricas" in parsed:
            return parsed
    return {}


def extrair_metricas_ok(resultado_exec: Any) -> List[Dict[str, Any]]:
    if not isinstance(resultado_exec, dict):
        return []
    return [m for m in resultado_exec.get("metricas", []) if m.get("status") == "ok"]


def metrica_top_n_para_df(m: Dict[str, Any]) -> Optional[pd.DataFrame]:
    res = m.get("resultado")
    if not isinstance(res, list) or not res:
        return None
    rows = []
    for item in res:
        if not isinstance(item, dict):
            continue
        g, v = item.get("grupo"), item.get("valor")
        rows.append({"grupo": str(g) if g is not None else "", "valor": v})
    if not rows:
        return None
    return pd.DataFrame(rows)


def _rotulo_metrica(m: Dict[str, Any]) -> str:
    mid = str(m.get("metric_id") or "metrica")
    desc = m.get("descricao")
    if isinstance(desc, str) and desc.strip():
        return (desc.strip())[:100]
    return mid[:100]


def metrica_resultado_para_dataframe(m: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """
    Converte qualquer métrica com status ok em DataFrame com colunas grupo, valor para gráficos.
    Suporta: top_n e listas {grupo,valor}; timeseries {periodo,valor}; escalares (count, sum, mean, etc.).
    """
    res = m.get("resultado")
    label = _rotulo_metrica(m)

    if isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict):
        r0 = res[0]
        if "grupo" in r0 and "valor" in r0:
            return metrica_top_n_para_df(m)
        if "periodo" in r0 and "valor" in r0:
            rows = []
            for item in res:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    {
                        "grupo": str(item.get("periodo", ""))[:120],
                        "valor": item.get("valor"),
                    }
                )
            if not rows:
                return None
            return pd.DataFrame(rows)

    if isinstance(res, bool):
        return None
    if isinstance(res, Number):
        return pd.DataFrame([{"grupo": label, "valor": float(res)}])

    if res is not None and not isinstance(res, (list, dict)):
        num = pd.to_numeric(res, errors="coerce")
        if pd.notna(num):
            return pd.DataFrame([{"grupo": label, "valor": float(num)}])
        return pd.DataFrame([{"grupo": label, "valor": str(res)[:80]}])

    return None


def dfs_por_metric_id(resultado_exec: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for m in extrair_metricas_ok(resultado_exec):
        mid = m.get("metric_id") or ""
        df = metrica_resultado_para_dataframe(m)
        if df is not None and not df.empty:
            out[str(mid)] = df
    return out


def _eixo_x_sugere_servico(campo: Optional[str], rotulo: Optional[str]) -> bool:
    c = str(campo or "").lower()
    r = str(rotulo or "").lower()
    if "servico" in c or "serviço" in c or "servico" in r or "serviço" in r:
        return True
    if "tipo_serv" in c or "nome_serv" in c:
        return True
    return False


def _campo_x_e_generico(campo: Optional[str]) -> bool:
    return str(campo or "").strip().lower() in {
        "nome",
        "grupo",
        "categoria",
        "label",
        "item",
        "rotulo",
        "chave",
        "descricao",
    }


def _titulo_menciona_loja_ou_concessionaria(titulo: Optional[str]) -> bool:
    t = str(titulo or "").lower()
    return any(
        x in t
        for x in (
            "concession",
            "concessionária",
            "loja",
            "unidade",
            "rede (lojas)",
            "por loja",
        )
    )


def _titulo_sugere_eixo_servico_sem_loja(titulo: Optional[str]) -> bool:
    """Título fala em serviço/mix/top serviço mas não deixa explícito que o eixo é loja."""
    if _titulo_menciona_loja_ou_concessionaria(titulo):
        return False
    t = str(titulo or "").lower()
    frases = (
        "tipo de serviço",
        "tipo de servico",
        "por tipo de serviço",
        "por tipo de servico",
        "mix de serviços",
        "mix de servicos",
        "mix servico",
        "mix serviços",
        "top serviços",
        "top servicos",
        "ranking de serviços",
        "ranking de servicos",
        "faturamento por serviço",
        "faturamento por servico",
        "quantidade por serviço",
        "quantidade por servico",
        "cross-sell por serviço",
        "cross-sell por servico",
        "cross sell por serviço",
        "cross sell por servico",
    )
    return any(f in t for f in frases)


def _metrica_eh_agregacao_por_concessionaria(m: Dict[str, Any]) -> bool:
    """Métrica cujo eixo grupo é (também) concessionária — ex.: top_n por concessionaria_nome."""
    gb = m.get("group_by")
    if isinstance(gb, str):
        gb = [gb]
    if isinstance(gb, list) and len(gb) > 0:
        for c in gb:
            cl = str(c).lower()
            if "concessionaria" in cl or cl in ("con_id", "concessionaria_id"):
                return True
        return False

    mid = str(m.get("metric_id") or "").lower()
    desc = str(m.get("descricao") or "").lower()
    if "_conc" in mid or mid.endswith("_conc") or "concession" in mid or "por_loja" in mid:
        return True
    if "loja" in mid and "servico" not in mid and "serviço" not in mid:
        return True
    if "rede" in mid and "servico" not in mid and "serviço" not in mid:
        return True
    trechos = (
        "concessionária",
        "concessionaria",
        "por loja",
        "por concession",
        "por unidade",
    )
    if any(t in desc for t in trechos):
        return True
    return False


def _deve_renomear_eixo_servico_para_concessionaria(
    spec: Dict[str, Any],
    campo_x: str,
    rotulo_x: Optional[str],
    m: Dict[str, Any],
) -> bool:
    if not _metrica_eh_agregacao_por_concessionaria(m):
        return False
    tit = spec.get("titulo")
    if _eixo_x_sugere_servico(campo_x, rotulo_x):
        return True
    if _titulo_sugere_eixo_servico_sem_loja(tit) and (
        _campo_x_e_generico(campo_x) or _eixo_x_sugere_servico(campo_x, rotulo_x)
    ):
        return True
    return False


def _grupo_cell_para_valor_bruto(grupo_cell: Any) -> Any:
    """Se o grupo foi serializado como string de lista, reparse para casar loja no filtro."""
    if isinstance(grupo_cell, str):
        s = grupo_cell.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                v = ast.literal_eval(s)
                if isinstance(v, (list, tuple)):
                    return v
            except (ValueError, SyntaxError):
                pass
    return grupo_cell


def _match_grupo_loja(grupo_val: Any, nome_loja: Optional[str]) -> bool:
    if not nome_loja or not str(nome_loja).strip():
        return True
    n = str(nome_loja).strip().casefold()
    gv = _grupo_cell_para_valor_bruto(grupo_val)
    if isinstance(gv, (list, tuple)):
        return any(str(p).strip().casefold() == n for p in gv)
    return str(gv).strip().casefold() == n


def _metricas_spec_referenciam_por_concessionaria(
    spec: Dict[str, Any], por_mid: Dict[str, Dict[str, Any]]
) -> bool:
    ids = spec.get("fonte_metric_ids") or spec.get("fonte_metric_id") or []
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list):
        return False
    for mid in ids:
        m = por_mid.get(str(mid))
        if m and _metrica_eh_agregacao_por_concessionaria(m):
            return True
    return False


def _filtrar_dados_spec_por_loja_do_rel(
    spec: Dict[str, Any],
    rel: Dict[str, Any],
    por_mid: Dict[str, Dict[str, Any]],
) -> None:
    """Evita gráfico 'por loja X' com ranking de toda a rede (dados de métrica por concessionária)."""
    nome = (rel.get("concessionaria_nome") or "").strip()
    if not nome or not _metricas_spec_referenciam_por_concessionaria(spec, por_mid):
        return
    dados = spec.get("dados")
    if not isinstance(dados, list) or len(dados) < 2:
        return
    eixos = spec.get("eixos") or {}
    ex_x = eixos.get("x") or {}
    if not isinstance(ex_x, dict):
        return
    cx = ex_x.get("campo")
    if not cx:
        return
    kept = [r for r in dados if isinstance(r, dict) and _match_grupo_loja(r.get(cx), nome)]
    if kept:
        spec["dados"] = kept


def _ajustar_titulo_servico_para_loja(titulo: str) -> str:
    """Alinha título ao eixo real (concessionária) quando a métrica é por loja."""
    if not titulo:
        return titulo
    t = titulo
    repls = [
        (r"por\s+tipo\s+de\s+servi[çc]o", "por concessionária"),
        (r"mix\s+de\s+servi[çc]os?", "Indicadores por concessionária"),
        (r"mix\s+servi[çc]os?", "Indicadores por concessionária"),
        (r"top\s+servi[çc]os?", "Top concessionárias"),
        (r"ranking\s+de\s+servi[çc]os?", "Ranking de concessionárias"),
        (r"faturamento\s+por\s+servi[çc]o", "Faturamento por concessionária"),
        (r"quantidade\s+por\s+servi[çc]o", "Quantidade por concessionária"),
        (r"cross[- ]?sell\s+por\s+servi[çc]o", "Cross-sell por concessionária"),
        (r"cross\s+sell\s+por\s+servi[çc]o", "Cross-sell por concessionária"),
    ]
    for pat, sub in repls:
        t = re.sub(pat, sub, t, flags=re.IGNORECASE)
    return t


def enriquecer_visualizacoes_com_metricas(
    resposta: Optional[Dict[str, Any]], ex: Dict[str, Any]
) -> None:
    """
    Preenche `dados` vazios em specs quando `fonte_metric_ids` aponta para métricas ok em `ex`.
    Corrige eixo X e título quando a métrica é por concessionária mas a spec fala em
    serviço (campo servico, título 'mix/top serviços', eixo x genérico 'nome', etc.).
    """
    if not resposta or not isinstance(resposta, dict) or not ex:
        return
    por_mid = {str(m.get("metric_id")): m for m in extrair_metricas_ok(ex)}

    def fill_spec(spec: Dict[str, Any], rel: Optional[Dict[str, Any]] = None) -> None:
        if not isinstance(spec, dict):
            return
        dados = spec.get("dados")
        if isinstance(dados, list) and len(dados) > 0:
            return
        ids = spec.get("fonte_metric_ids") or spec.get("fonte_metric_id") or []
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list) or not ids:
            return
        eixos = spec.get("eixos") or {}
        if not isinstance(eixos, dict):
            return
        ex_x = eixos.get("x") or {}
        ex_y = eixos.get("y") or {}
        if not isinstance(ex_x, dict) or not isinstance(ex_y, dict):
            return
        cx, cy = ex_x.get("campo"), ex_y.get("campo")
        if not cx or not cy:
            return
        nome_loja = ""
        if rel and isinstance(rel, dict):
            nome_loja = (rel.get("concessionaria_nome") or "").strip()
        for mid in ids:
            m = por_mid.get(str(mid))
            if not m:
                continue
            dfm = metrica_resultado_para_dataframe(m)
            if dfm is None or dfm.empty:
                continue
            if nome_loja and _metrica_eh_agregacao_por_concessionaria(m):
                dfm = dfm[dfm["grupo"].apply(lambda g, nl=nome_loja: _match_grupo_loja(g, nl))].copy()
                if dfm.empty:
                    continue
            cx_uso = cx
            if _deve_renomear_eixo_servico_para_concessionaria(spec, cx, ex_x.get("rotulo"), m):
                cx_uso = "concessionaria"
                eixos.setdefault("x", {})
                eixos["x"]["campo"] = cx_uso
                rx = str(ex_x.get("rotulo") or "").replace("serviço", "concessionária").replace(
                    "servico", "concessionária"
                )
                rx_l = rx.strip().lower()
                if not rx_l or rx_l in ("serviço", "servico", "nome", "grupo", "categoria", "label"):
                    rx = "Concessionária"
                eixos["x"]["rotulo"] = rx
                spec["eixos"] = eixos
                tit = spec.get("titulo")
                if isinstance(tit, str) and tit:
                    spec["titulo"] = _ajustar_titulo_servico_para_loja(tit)
            linhas = []
            for _, r in dfm.iterrows():
                vy = r["valor"]
                q = pd.to_numeric(vy, errors="coerce")
                linhas.append(
                    {
                        cx_uso: str(r["grupo"]),
                        cy: float(q) if pd.notna(q) else vy,
                    }
                )
            spec["dados"] = linhas
            if nome_loja and _metrica_eh_agregacao_por_concessionaria(m) and linhas:
                xb = spec.setdefault("eixos", {}).setdefault("x", {})
                rlab = str(xb.get("rotulo") or "").strip().casefold()
                if rlab in (
                    "kpi",
                    "kpis",
                    "período",
                    "periodo",
                    "métrica",
                    "metrica",
                    "indicador",
                    "indicadores",
                ):
                    xb["rotulo"] = "Concessionária"
            break

    for rel in resposta.get("relatorios_concessionarias") or []:
        if not isinstance(rel, dict):
            continue
        for spec in rel.get("visualizacoes_sugeridas") or []:
            fill_spec(spec, rel)
            _filtrar_dados_spec_por_loja_do_rel(spec, rel, por_mid)
    for spec in resposta.get("especificacoes_graficos") or []:
        fill_spec(spec, None)


def validar_especificacao_grafico(spec: Dict[str, Any]) -> List[str]:
    erros: List[str] = []
    if not isinstance(spec, dict):
        return ["especificacao nao e dict"]
    if not spec.get("id"):
        erros.append("campo obrigatorio: id")
    tipo = str(spec.get("tipo_grafico") or "").lower().strip()
    if not tipo:
        erros.append("campo obrigatorio: tipo_grafico")
    dados = spec.get("dados")
    if not isinstance(dados, list) or not dados:
        erros.append("dados deve ser lista nao vazia")
    eixos = spec.get("eixos")
    if not isinstance(eixos, dict):
        erros.append("eixos deve ser objeto")
        return erros
    for k in ("x", "y"):
        ax = eixos.get(k)
        if not isinstance(ax, dict) or not ax.get("campo"):
            erros.append(f"eixos.{k}.campo obrigatorio")
    if erros:
        return erros
    cx = eixos["x"]["campo"]
    cy = eixos["y"]["campo"]
    if tipo == "heatmap":
        for i, row in enumerate(dados):
            if not isinstance(row, dict):
                erros.append(f"dados[{i}] nao e dict")
            elif cx not in row:
                erros.append(f"dados[{i}] falta rotulo de linha '{cx}'")
        return erros
    for i, row in enumerate(dados):
        if not isinstance(row, dict):
            erros.append(f"dados[{i}] nao e dict")
            continue
        if cx not in row:
            erros.append(f"dados[{i}] falta campo x '{cx}'")
        if cy not in row:
            erros.append(f"dados[{i}] falta campo y '{cy}'")
    return erros


def _slug(s: str, max_len: int = 48) -> str:
    t = "".join(c if c.isalnum() or c in "-_" else "_" for c in (s or "").lower())
    t = re.sub(r"_+", "_", t).strip("_")
    return (t or "spec")[:max_len]


def _resolve_xy_line_scatter(df: pd.DataFrame, cx: str, cy: str) -> Dict[str, Any]:
    """
    Eixo X para line/scatter: datetime e numérico reais; senão índice + rótulos categóricos.
    Evita tratar 4.64 / 4.46 como strings fora de ordem no scatter.
    """
    y = pd.to_numeric(df[cy], errors="coerce")
    raw_x = df[cx]
    n = len(df)
    thresh = max(1, int(0.85 * n)) if n else 0

    # Numérico antes de datetime: evita que 4.64 vire "data" espúria.
    num_x = pd.to_numeric(raw_x, errors="coerce")
    if bool(thresh) and int(num_x.notna().sum()) >= thresh:
        tmp = pd.DataFrame({"_x": num_x, "_y": y}).dropna(subset=["_x", "_y"])
        if not tmp.empty:
            tmp = tmp.sort_values("_x")
            return {
                "kind": "numeric",
                "x": tmp["_x"].to_numpy(dtype=float),
                "y": tmp["_y"].astype(float).to_numpy(),
            }

    dt = pd.to_datetime(raw_x, errors="coerce", utc=False)
    if bool(thresh) and int(dt.notna().sum()) >= thresh:
        tmp = pd.DataFrame({"_t": dt, "_y": y}).dropna(subset=["_t", "_y"])
        if not tmp.empty:
            tmp = tmp.sort_values("_t")
            return {"kind": "time", "x": tmp["_t"], "y": tmp["_y"].astype(float)}

    xs_str = raw_x.astype(str).tolist()
    yv = y.fillna(0.0).astype(float).tolist()
    return {
        "kind": "categorical",
        "x_pos": np.arange(len(xs_str), dtype=float),
        "y": yv,
        "labels": xs_str,
    }


def renderizar_especificacao(spec: Dict[str, Any], path: str) -> str:
    """Gera um PNG a partir da especificação. Levanta ValueError se inválida."""
    errs = validar_especificacao_grafico(spec)
    if errs:
        raise ValueError("; ".join(errs))
    tipo = str(spec.get("tipo_grafico", "")).lower().strip()
    titulo = str(spec.get("titulo") or spec.get("id") or "Gráfico")[:200]
    dados = spec["dados"]
    eixos = spec["eixos"]
    cx, cy = eixos["x"]["campo"], eixos["y"]["campo"]
    lx = str(eixos["x"].get("rotulo") or cx)
    ly = str(eixos["y"].get("rotulo") or cy)
    df = pd.DataFrame(dados)
    xs = df[cx].astype(str).tolist()
    ys = pd.to_numeric(df[cy], errors="coerce").fillna(0.0).tolist()

    if tipo in ("line", "scatter"):
        fig, ax = plt.subplots(figsize=(10, 5))
        resolved = _resolve_xy_line_scatter(df, cx, cy)
        if resolved["kind"] == "time":
            xv, yv = resolved["x"], resolved["y"]
            if tipo == "line":
                ax.plot(xv, yv, marker="o", color="#2563eb")
            else:
                ax.scatter(xv, yv, c="#2563eb", alpha=0.75)
            ax.set_xlabel(lx, fontsize=10)
            ax.set_ylabel(ly, fontsize=10)
            fig.autofmt_xdate()
        elif resolved["kind"] == "numeric":
            xv, yv = resolved["x"], resolved["y"]
            if tipo == "line":
                ax.plot(xv, yv, marker="o", color="#2563eb")
            else:
                ax.scatter(xv, yv, c="#2563eb", alpha=0.75)
            ax.set_xlabel(lx, fontsize=10)
            ax.set_ylabel(ly, fontsize=10)
        else:
            x_pos, yv, labels = resolved["x_pos"], resolved["y"], resolved["labels"]
            h = max(4.0, 0.35 * len(labels))
            plt.close(fig)
            fig, ax = plt.subplots(figsize=(10, h))
            if tipo == "line":
                ax.plot(x_pos, yv, marker="o", color="#2563eb")
            else:
                ax.scatter(x_pos, yv, c="#2563eb", alpha=0.75)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
            ax.set_xlabel(lx, fontsize=10)
            ax.set_ylabel(ly, fontsize=10)
    else:
        fig, ax = plt.subplots(figsize=(10, max(4.0, 0.35 * len(xs))))

    if tipo == "barh":
        ax.barh(xs, ys, color="#60a5fa")
        ax.set_xlabel(ly, fontsize=10)
        ax.set_ylabel(lx, fontsize=10)
        ax.invert_yaxis()
    elif tipo == "bar":
        ax.bar(xs, ys, color="#60a5fa")
        ax.set_xlabel(lx, fontsize=10)
        ax.set_ylabel(ly, fontsize=10)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha="right")
    elif tipo == "pie":
        ax.pie(ys, labels=xs, autopct="%1.0f%%", textprops={"fontsize": 8})
        ax.set_title(titulo, fontsize=11)
        fig.tight_layout()
        fig.savefig(path, dpi=120, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return path
    elif tipo in ("line", "scatter"):
        pass
    elif tipo == "heatmap":
        if len(df.columns) < 2:
            raise ValueError("heatmap: dados precisam de pelo menos 2 colunas numéricas além do rótulo")
        num = df.select_dtypes(include=[np.number])
        if num.shape[1] == 0:
            raise ValueError("heatmap: sem colunas numericas")
        im = ax.imshow(num.values, aspect="auto", cmap="Blues")
        ax.set_yticks(range(len(df)))
        ax.set_yticklabels(df[cx].astype(str).tolist(), fontsize=8)
        ax.set_xticks(range(num.shape[1]))
        ax.set_xticklabels(num.columns.tolist(), rotation=35, ha="right", fontsize=8)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    else:
        plt.close(fig)
        raise ValueError(f"tipo_grafico nao suportado: {tipo}")

    ax.set_title(titulo, fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def especificacoes_automaticas_de_metricas(ex: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Monta specs `barh` (nome × quantidade) a partir de qualquer métrica ok plotável
    (top_n, timeseries, escalares count/sum/mean, etc.), quando o modelo não enviou specs.
    """
    specs: List[Dict[str, Any]] = []
    for m in extrair_metricas_ok(ex):
        mid = str(m.get("metric_id") or "metrica")
        df = metrica_resultado_para_dataframe(m)
        if df is None or df.empty:
            continue
        dados = []
        for _, r in df.head(25).iterrows():
            q = pd.to_numeric(r["valor"], errors="coerce")
            dados.append(
                {
                    "nome": str(r["grupo"])[:120],
                    "quantidade": float(q) if pd.notna(q) else 0.0,
                }
            )
        specs.append(
            {
                "id": _slug(mid, 50) or "metrica",
                "tipo_grafico": "barh",
                "titulo": (m.get("descricao") or mid)[:200],
                "dados": dados,
                "eixos": {
                    "x": {"campo": "nome", "rotulo": "Grupo"},
                    "y": {"campo": "quantidade", "rotulo": "Valor"},
                },
                "fonte_metric_ids": [mid],
            }
        )
    return specs


def listar_especificacoes_visualizacao(resposta: Optional[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    """Retorna pares (chave_arquivo_segura, spec) na ordem: por loja, depois globais."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    if not isinstance(resposta, dict):
        return out
    for rel in resposta.get("relatorios_concessionarias") or []:
        if not isinstance(rel, dict):
            continue
        loja = str(rel.get("concessionaria_nome") or rel.get("concessionaria_id") or "loja")
        slug_loja = _slug(loja, 32)
        for spec in rel.get("visualizacoes_sugeridas") or []:
            if not isinstance(spec, dict):
                continue
            sid = str(spec.get("id") or "viz")
            key = f"{slug_loja}_{_slug(sid, 40)}"
            out.append((key, spec))
    for spec in resposta.get("especificacoes_graficos") or []:
        if not isinstance(spec, dict):
            continue
        sid = str(spec.get("id") or "global")
        out.append((f"g_{_slug(sid, 50)}", spec))
    return out


def renderizar_todas_especificacoes(
    resposta: Optional[Dict[str, Any]],
    out_dir: str,
    prefix: str = "spec",
) -> Dict[str, str]:
    paths: Dict[str, str] = {}
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    for key, spec in listar_especificacoes_visualizacao(resposta):
        fname = f"{prefix}_{key}.png"
        path = str(base / fname)
        try:
            renderizar_especificacao(spec, path)
            paths[f"spec_{key}"] = path
        except ValueError:
            continue
    return paths


class GraficosAgenteClusterizacaoConcessionaria:
    """Gera PNGs a partir de `resultado_execucao` + `resposta` FASE 2 (inclui specs JSON)."""

    def __init__(self, out_dir: str = "output/graficos_cluster"):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _salvar_barh(self, df: pd.DataFrame, titulo: str, arquivo: str, max_itens: int = 25) -> str:
        d = df.head(max_itens).copy()
        d = d.assign(_v=pd.to_numeric(d["valor"], errors="coerce").fillna(0))
        fig, ax = plt.subplots(figsize=(10, max(4.0, 0.38 * len(d))))
        ax.barh(d["grupo"].astype(str), d["_v"])
        ax.set_title(str(titulo)[:120], fontsize=11)
        ax.invert_yaxis()
        fig.tight_layout()
        path = str(self.out_dir / arquivo)
        fig.savefig(path, dpi=120, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return path

    @staticmethod
    def _pct_intervalo_para_numero(val: Any) -> float:
        if val is None:
            return float("nan")
        if isinstance(val, (int, float)):
            return float(val)
        t = str(val).replace("%", "").replace("–", "-").strip()
        nums = re.findall(r"[\d.]+", t)
        if not nums:
            return float("nan")
        vals = [float(x) for x in nums[:2]]
        return float(np.mean(vals))

    def _mix_dict_do_perfil(self, perfil: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for k, v in perfil.items():
            if "mix" in k.lower() and isinstance(v, dict):
                return v
        return None

    def _graficos_perfis_qualitativos(self, resposta: Optional[Dict[str, Any]]) -> Dict[str, str]:
        paths: Dict[str, str] = {}
        if not resposta or not isinstance(resposta.get("perfis"), list):
            return paths
        perfis = resposta["perfis"]
        nomes = [
            str(p.get("nome_perfil") or p.get("nome") or "?")
            for p in perfis
            if isinstance(p, dict)
        ]
        if nomes:
            fig, ax = plt.subplots(figsize=(10, max(3.0, 0.35 * len(nomes))))
            ax.barh(range(len(nomes)), [1] * len(nomes), color="#93c5fd")
            ax.set_yticks(range(len(nomes)))
            ax.set_yticklabels(nomes, fontsize=9)
            ax.set_title("Perfis listados (resposta qualitativa FASE 2)", fontsize=11)
            ax.invert_yaxis()
            ax.set_xticks([])
            fig.tight_layout()
            p2 = str(self.out_dir / "c2_perfis_listados.png")
            fig.savefig(p2, dpi=120, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            paths["c2_perfis"] = p2

        rows_mix = []
        for p in perfis:
            if not isinstance(p, dict):
                continue
            mix = self._mix_dict_do_perfil(p)
            if not mix:
                continue
            row: Dict[str, Any] = {"perfil": str(p.get("nome_perfil") or "?")}
            for ck, cv in mix.items():
                row[str(ck)] = self._pct_intervalo_para_numero(cv)
            rows_mix.append(row)
        if rows_mix:
            dfm = pd.DataFrame(rows_mix).set_index("perfil").fillna(0)
            fig, ax = plt.subplots(figsize=(10, max(4.0, 0.4 * len(dfm))))
            dfm.plot(kind="barh", stacked=True, ax=ax, legend=True, fontsize=8)
            ax.set_title("Mix estimado por perfil (média da faixa % quando intervalo)", fontsize=11)
            ax.invert_yaxis()
            fig.tight_layout()
            p3 = str(self.out_dir / "c3_mix_receita_por_perfil.png")
            fig.savefig(p3, dpi=120, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            paths["c3_mix"] = p3
        return paths

    def _distribuicao_clusters(self, resposta: Optional[Dict[str, Any]]) -> Optional[str]:
        if not resposta:
            return None
        dist = None
        rc = resposta.get("resumo_clustering")
        if isinstance(rc, dict):
            dist = rc.get("distribuicao")
        if not dist and isinstance(resposta.get("distribuicao"), dict):
            dist = resposta["distribuicao"]
        if not dist:
            perfis = resposta.get("perfis_clusters")
            if isinstance(perfis, list):
                labels, vals = [], []
                for p in perfis:
                    if not isinstance(p, dict):
                        continue
                    cid = p.get("cluster_id", p.get("nome_perfil", "?"))
                    t = p.get("tamanho")
                    if t is None:
                        t = len(p.get("concessionarias") or [])
                    try:
                        tv = int(t)
                    except (TypeError, ValueError):
                        tv = 0
                    labels.append(str(cid))
                    vals.append(tv)
                if labels:
                    dist = dict(zip(labels, vals))
        if not dist:
            return None
        df = pd.DataFrame([{"grupo": str(k), "valor": float(v)} for k, v in dist.items()])
        return self._salvar_barh(df, "Distribuição por cluster", "c1_distribuicao_clusters.png")

    def gerar(self, resp_agente: Dict[str, Any]) -> Dict[str, str]:
        paths: Dict[str, str] = {}
        resposta = normalizar_resposta_cluster(resp_agente.get("resposta"))
        ex = resultado_exec_para_dict(resp_agente.get("resultado_execucao"))
        enriquecer_visualizacoes_com_metricas(resposta, ex)

        for m in extrair_metricas_ok(ex):
            mid = str(m.get("metric_id") or "")
            if not mid:
                continue
            df = metrica_resultado_para_dataframe(m)
            if df is None or df.empty:
                continue
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in mid)[:60]
            titulo_m = str(m.get("descricao") or mid).strip()[:120]
            paths[f"m_{safe}"] = self._salvar_barh(df, titulo_m, f"m_{safe}.png", max_itens=25)

        p = self._distribuicao_clusters(resposta)
        if p:
            paths["c1_distribuicao"] = p

        paths.update(self._graficos_perfis_qualitativos(resposta))

        spec_paths = renderizar_todas_especificacoes(resposta, str(self.out_dir), prefix="spec")
        paths.update(spec_paths)

        if not spec_paths and ex.get("metricas") and not any(k.startswith("m_") for k in paths):
            auto_specs = especificacoes_automaticas_de_metricas(ex)
            for idx, spec in enumerate(auto_specs):
                sid = _slug(str(spec.get("id") or f"a{idx}"), 50)
                path = str(self.out_dir / f"auto_{sid}.png")
                try:
                    renderizar_especificacao(spec, path)
                    paths[f"auto_{sid}"] = path
                except ValueError:
                    continue

        if not paths:
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.text(
                0.5,
                0.5,
                "Sem dados para gráficos de cluster\n(métricas ok vazias ou JSON FASE 2 sem distribuição/specs)",
                ha="center",
                va="center",
                fontsize=11,
                color="#6b7280",
            )
            ax.axis("off")
            ph = str(self.out_dir / "placeholder.png")
            fig.savefig(ph, dpi=120, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            paths["placeholder"] = ph
        return paths


def gerar_todos_graficos_cluster(
    resultado_maestro: Dict[str, Any],
    out_dir: str = "output/graficos_cluster",
) -> Dict[str, str]:
    """
    Delegação para uso no notebook/app: percorre respostas do agente de clusterização e gera PNGs.
    """
    merged: Dict[str, str] = {}
    agentes = resultado_maestro.get("respostas_agentes") or []
    graf = GraficosAgenteClusterizacaoConcessionaria(out_dir=out_dir)
    for i, resp in enumerate(agentes):
        aid = str(resp.get("agente_id") or "")
        if "clusterizacao" in aid or aid == "agente_clusterizacao_concessionaria":
            sub = graf.gerar(resp)
            for k, v in sub.items():
                merged[f"{i}_{k}"] = v
    if not merged and agentes:
        r0 = agentes[0]
        ex0 = resultado_exec_para_dict(r0.get("resultado_execucao"))
        if ex0.get("metricas") or r0.get("resposta"):
            sub = graf.gerar(r0)
            for k, v in sub.items():
                merged[f"0_{k}"] = v
    return merged
