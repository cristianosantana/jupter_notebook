# app/services/maestro_fluxo.py — Fluxo Maestro com perguntas_dados (FASE 1 agregada)
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from mnt.skills.agente_mysql.helpers import MySQLAgent

from app.core.skills import get_skill_by_id, load_skills


def _get_skills(skills_list=None, skills_dir=None):
    if skills_list is not None:
        return skills_list
    base = skills_dir or os.path.join(os.path.dirname(__file__), "..", "..", "mnt", "skills")
    return load_skills(base)


def extrair_json(texto: str) -> Optional[Dict]:
    """Extrai JSON do texto retornado pelo modelo."""
    if not texto or not texto.strip():
        return None
    s = texto.strip()
    if "```" in s:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
        if match:
            s = match.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _dict_resposta_para_markdown(obj, depth: int = 0, max_depth: int = 6) -> str:
    """Converte resposta em dict (JSON do agente) em markdown legível."""
    if depth > max_depth:
        return "_…_"
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        lines = []
        for i, item in enumerate(obj[:35]):
            if isinstance(item, dict):
                block = _dict_resposta_para_markdown(item, depth + 1, max_depth)
                lines.append(f"{i + 1}. " + block.replace("\n", "\n   "))
            else:
                lines.append(f"- {item}")
        if len(obj) > 35:
            lines.append(f"- _(+{len(obj) - 35} itens)_")
        return "\n".join(lines) if lines else "_(vazio)_"
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            label = str(k).replace("_", " ").strip() or k
            if isinstance(v, (dict, list)):
                sub = _dict_resposta_para_markdown(v, depth + 1, max_depth)
                parts.append(f"**{label}**\n{sub}")
            else:
                parts.append(f"**{label}**: {v}")
        return "\n\n".join(parts)
    return str(obj)


def _primeiro_texto_util_em_dict(d: Dict, max_len: int = 520) -> Optional[str]:
    """Primeiro texto útil para síntese (evita cortar JSON bruto em 120 chars)."""
    if not isinstance(d, dict):
        return None
    for key in ("resumo_executivo", "resumo_objetivo", "conclusao_pratica", "conclusao", "resumo"):
        if key not in d:
            continue
        v = d[key]
        if isinstance(v, str) and len(v.strip()) > 15:
            s = v.strip()
            return s[:max_len] + ("…" if len(s) > max_len else "")
        if isinstance(v, dict):
            inner = _primeiro_texto_util_em_dict(v, max_len)
            if inner:
                return inner
    for v in d.values():
        if isinstance(v, str) and len(v.strip()) > 40:
            s = v.strip()
            return s[:max_len] + ("…" if len(s) > max_len else "")
        if isinstance(v, dict):
            inner = _primeiro_texto_util_em_dict(v, max_len)
            if inner:
                return inner
        if isinstance(v, list) and v:
            if all(isinstance(x, str) for x in v[:8]):
                joined = "; ".join(x for x in v[:6] if x)
                if len(joined) > 35:
                    return (joined[:max_len] + "…") if len(joined) > max_len else joined
    return None


def _cortar_em_frase(s: str, max_len: int) -> str:
    """Corta em limite de frase (último . ou ? ou ! antes de max_len) para não terminar no meio."""
    if len(s) <= max_len:
        return s
    cut = s[: max_len + 1]
    for sep in (". ", ".\n", "?\n", "!\n", "? ", "! "):
        idx = cut.rfind(sep)
        if idx > max_len // 2:
            return cut[: idx + len(sep)].rstrip()
    return cut[:max_len].rstrip()


def _trecho_para_sintese(resp, limite: int = 560) -> str:
    """Resumo por agente para a seção Síntese (completo o suficiente, sem JSON truncado)."""
    if isinstance(resp, dict):
        t = _primeiro_texto_util_em_dict(resp, limite)
        if t:
            return t
        flat = _dict_resposta_para_markdown(resp, max_depth=2)
        if len(flat) <= limite:
            return flat
        cut = _cortar_em_frase(flat, limite)
        return cut + "…" if len(cut) < len(flat) else cut
    s = (resp or "").strip() if isinstance(resp, str) else str(resp)
    if len(s) <= limite:
        return s
    cut = _cortar_em_frase(s, limite)
    if len(cut) >= len(s):
        return s
    nl = cut.rfind("\n\n")
    if nl > 200:
        return cut[:nl] + "…"
    return cut + "…"


def _resposta_agente_para_texto(resp) -> str:
    """Texto completo da resposta de um agente para a entrega markdown."""
    if isinstance(resp, dict):
        re = resp.get("resumo_executivo")
        if isinstance(re, str) and re.strip():
            return re.strip()
        return _dict_resposta_para_markdown(resp)
    return resp if isinstance(resp, str) else str(resp)


def _formatar_entrega(pergunta: str, respostas_agentes: List[Dict], avaliacao: Optional[Dict], para_avaliador: List[Dict]) -> str:
    """Gera o markdown da entrega conforme PASSO 6 do Maestro."""
    n_consultados = len(respostas_agentes)
    aval = avaliacao or {}
    avaliacao_completa = aval.get("avaliacao_completa") or []
    ranking = aval.get("ranking_final") or [r.get("agente_id") for r in para_avaliador]
    id_to_resp = {r.get("agente_id"): r for r in para_avaliador}
    ordenados = [id_to_resp[aid] for aid in ranking if aid in id_to_resp]
    for r in para_avaliador:
        if r.get("agente_id") not in ranking:
            ordenados.append(r)
    n_qualificadas = len(ordenados)
    linhas = [
        "## Resposta do Maestro", "",
        "**Pergunta:** " + pergunta,
        f"**Agentes consultados:** {n_consultados} | **Respostas qualificadas:** {n_qualificadas}",
        "---",
    ]
    for r in ordenados:
        aid = r.get("agente_id", "")
        nome = r.get("agente_nome", aid)
        score_total = next(
            (item.get("score_total") for item in avaliacao_completa if item.get("agente_id") == aid),
            (r.get("scores") or {}).get("score_final", 0),
        )
        pct = round((score_total or 0) * 100)
        _resp_raw = r.get("resposta", "")
        _str_res = _resposta_agente_para_texto(_resp_raw)
        linhas += [f"### {nome} — {aid}", f"*Score de Confiança: {pct}%*", "", _str_res, "", "---"]
    linhas += ["", "### Síntese"]
    resumos = []
    for r in ordenados:
        nome_s = r.get("agente_nome", r.get("agente_id", ""))
        resumos.append(f"**{nome_s}:** {_trecho_para_sintese(r.get('resposta', ''))}")
    linhas.append("\n\n".join(resumos))
    return "\n".join(linhas)


def invocar_agente_maestro(client, skill_id, payload_maestro, model, skills_list=None, skills_dir=None):
    """Invoca um agente em modo Maestro; retorno JSON válido."""
    skills = _get_skills(skills_list, skills_dir)
    skill = get_skill_by_id(skills, skill_id)
    if not skill:
        return ""
    modelo = skill.get("model") or model
    user = (
        json.dumps(payload_maestro, ensure_ascii=False)
        + "\n\nVocê está sendo invocado pelo Maestro. Responda APENAS com um único JSON válido no Formato de Retorno da skill "
        "(agente_id, agente_nome, pode_responder, justificativa_viabilidade, resposta, scores, limitacoes_da_resposta, aspectos_para_outros_agentes), "
        "incluindo campos extras de fase quando solicitado (ex.: perguntas_dados na FASE 1). Sem texto antes ou depois."
    )
    resp = client.chat.completions.create(
        model=modelo,
        messages=[{"role": "system", "content": skill["content"]}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    return (resp.choices[0].message.content or "").strip()

def executar_fluxo_maestro(
    client: OpenAI,
    pergunta: str,
    model: str = None,
    skills_list: Optional[List[Dict]] = None,
    agentes: Optional[List[str]] = None,
    agentes_dataframe: Optional[List[str]] = None,
    verbose: bool = True,
    mysql_host: Optional[str] = None,
    mysql_porta: Optional[int] = None,
    mysql_usuario: Optional[str] = None,
    mysql_senha: Optional[str] = None,
    mysql_banco: Optional[str] = None,
    mysql_tabela: Optional[str] = None,
    mysql_tabelas: Optional[List[Dict]] = None,
    mysql_limite: int = 50_000,
    mysql_filtro_where: str = "",
    mysql_injetar_namespace: Optional[Dict] = None,
    skills_dir: Optional[str] = None,
) -> Dict:
    """
    Executa o fluxo completo: análise (1+2), invocação dos N agentes (3),
    payload avaliador (4), avaliador (5), entrega (6).

    Versão com privacidade reforçada para agentes DataFrame:
      - FASE 1: agente retorna perguntas agregadas em JSON (perguntas_dados)
      - Executor interno calcula somente métricas agregadas (sem linha crua)
      - FASE 2: agente interpreta resultado_extracao estruturado
    """
    import pandas as pd

    model = model or os.environ.get("MODELO_DEFAULT")
    skills = _get_skills(skills_list, skills_dir)
    agentes = agentes or []
    _agentes_dataframe = agentes_dataframe if agentes_dataframe is not None \
        else ["agente-dados", "agente-financeiro", "agente-negocios"]
    resultado_mysql = None
    df_contexto = None
    df_variavel = None
    _t = os.environ.get("TIME_INTERVAL_AGENTS")
    time_interval_agents = float(_t) if _t else 2.0

    contrato_perguntas = {
        "schema": "perguntas_dados.v1",
        "campos": [
            "metric_id", "descricao", "tipo", "coluna_valor", "group_by", "filtros", "janela_tempo", "top_n",
            "coluna_data", "frequencia", "quantil", "agregacao"
        ],
        "tipos_permitidos": ["count", "sum", "mean", "median", "percentile", "top_n", "timeseries", "null_rate", "nunique"],
        "operadores_filtro_permitidos": ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in"],
    }

    def _to_scalar(v):
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        if hasattr(v, "item"):
            try:
                return v.item()
            except Exception:
                return str(v)
        return v

    def _resolver_col_data(df, preferida=None):
        candidatos = []
        if preferida:
            candidatos.append(preferida)
        candidatos += ["created_at", "data", "data_venda", "updated_at", "timestamp"]
        for c in candidatos:
            if c in df.columns:
                return c
        return None

    def _mascarar_valor(valor):
        if valor is None:
            return None
        if isinstance(valor, str):
            return (valor[:64] + "...") if len(valor) > 64 else valor
        return valor

    def _sanitizar_df_amostra(df: pd.DataFrame, n: int = 8) -> List[Dict]:
        if df is None or df.empty:
            return []

        import re as _re
        import numpy as _np
        import pandas as _pd

        sensivel_regex = _re.compile(
            r"(email|mail|telefone|celular|cpf|cnpj|document|rg|endereco|address|senha|password|token|secret|pix|cartao|card|nascimento)",
            _re.IGNORECASE,
        )
        id_regex = _re.compile(r"(^id$|_id$|id_|uuid)", _re.IGNORECASE)
        amostra = df.head(n).copy()
        total = len(df)

        for i in range(len(amostra.columns)):
            col = amostra.columns[i]
            serie = amostra.iloc[:, i]
            col_s = str(col)
            col_low = col_s.lower()
            if sensivel_regex.search(col_low):
                amostra.iloc[:, i] = amostra.iloc[:, i].astype(object)
                amostra.iloc[:, i] = "***MASKED***"
                continue

            try:
                nunique = int(df.iloc[:, i].nunique(dropna=True))
            except Exception:
                nunique = None

            if id_regex.search(col_low) and nunique is not None and total > 0 and (nunique / total) > 0.8:
                amostra.iloc[:, i] = amostra.iloc[:, i].astype(object)
                amostra.iloc[:, i] = "<ID_MASKED>"
                continue

            if serie.dtype == "object" or str(serie.dtype) == "object":
                amostra.iloc[:, i] = serie.map(_mascarar_valor)

        if amostra.columns.duplicated().any():
            seen = {}
            new_cols = []
            for c in amostra.columns:
                cstr = str(c)
                n = seen.get(cstr, 0)
                new_cols.append(cstr if n == 0 else f"{cstr}_{n}")
                seen[cstr] = n + 1
            amostra.columns = new_cols
        records = amostra.to_dict(orient="records")

        def _to_json_serializable(val):
            # None or NaN/NaT -> None
            try:
                if pd.isna(val):
                    return None
            except Exception:
                pass
            # pandas Timestamp
            try:
                if isinstance(val, _pd.Timestamp):
                    return val.isoformat()
            except Exception:
                pass
            # numpy scalar types
            try:
                if isinstance(val, _np.generic):
                    return val.item()
            except Exception:
                pass
            # datetimes
            try:
                import datetime as _dt
                if isinstance(val, _dt.datetime) or isinstance(val, _dt.date):
                    return val.isoformat()
            except Exception:
                pass
            # timedelta
            try:
                if isinstance(val, _pd.Timedelta):
                    return str(val)
            except Exception:
                pass
            # fallback for common primitives
            if isinstance(val, (str, int, float, bool)):
                return val
            # default to string representation
            try:
                return str(val)
            except Exception:
                return None

        clean_records = []
        for r in records:
            nr = {}
            for k, v in r.items():
                nr[k] = _to_json_serializable(v)
            clean_records.append(nr)

        return clean_records

    def _montar_df_perfil(df: pd.DataFrame) -> Dict:
        if df is None:
            return {}

        total = len(df)
        cols = []
        n_cols = min(80, len(df.columns))
        for i in range(n_cols):
            serie = df.iloc[:, i]
            col = df.columns[i]
            nulls = int(serie.isna().sum())
            pct_null = round((nulls / total) * 100, 2) if total > 0 else 0.0
            try:
                nunique = int(serie.nunique(dropna=True))
            except Exception:
                nunique = None
            cols.append({
                "coluna": str(col),
                "dtype": str(serie.dtype),
                "nulls": nulls,
                "pct_null": pct_null,
                "nunique": nunique,
            })

        num_indices = [i for i in range(len(df.columns)) if pd.api.types.is_numeric_dtype(df.iloc[:, i].dtype)][:15]
        estat_num = {}
        seen_num = {}
        for i in num_indices:
            s = pd.to_numeric(df.iloc[:, i], errors="coerce")
            c = str(df.columns[i])
            key = c if c not in seen_num else f"{c}_{seen_num[c]}"
            seen_num[c] = seen_num.get(c, 0) + 1
            estat_num[key] = {
                "mean": _to_scalar(round(s.mean(), 6)) if s.notna().any() else None,
                "median": _to_scalar(round(s.median(), 6)) if s.notna().any() else None,
                "p95": _to_scalar(round(s.quantile(0.95), 6)) if s.notna().any() else None,
                "min": _to_scalar(round(s.min(), 6)) if s.notna().any() else None,
                "max": _to_scalar(round(s.max(), 6)) if s.notna().any() else None,
            }

        return {
            "linhas": int(df.shape[0]),
            "colunas": int(df.shape[1]),
            "perfil_colunas": cols,
            "estatisticas_numericas": estat_num,
        }

    def _preparar_contexto_mysql() -> Tuple[Dict, Dict]:
        host    = mysql_host    or os.environ.get("MYSQL_HOST", "localhost")
        porta   = mysql_porta
        if porta is None:
            porta_env = os.environ.get("MYSQL_PORT")
            porta = int(porta_env) if porta_env else 3306
        usuario = mysql_usuario or os.environ.get("MYSQL_USER", "root")
        senha   = mysql_senha   or os.environ.get("MYSQL_PASSWORD", "")
        banco   = mysql_banco   or os.environ.get("MYSQL_DATABASE", "")

        agent     = MySQLAgent(host=host, porta=porta, usuario=usuario, senha=senha, banco=banco)
        namespace = mysql_injetar_namespace if mysql_injetar_namespace is not None else globals()

        if mysql_tabelas:
            resultado = agent.carregar_multiplas_tabelas(
                definicoes=mysql_tabelas,
                limite=mysql_limite,
                filtro_where=mysql_filtro_where,
                verbose=verbose,
            )
        else:
            resultado = agent.carregar_tabela(
                mysql_tabela,
                limite=mysql_limite,
                filtro_where=mysql_filtro_where,
                verbose=verbose,
            )

        if not resultado["sucesso"]:
            raise RuntimeError(f"[agente-mysql] {resultado['erro']}")

        if namespace is not None:
            agent.injetar_no_namespace(resultado, namespace)

        df = resultado["dataframe"]
        amostra_sanitizada = _sanitizar_df_amostra(df)
        try:
            amostra_json = json.dumps(amostra_sanitizada, ensure_ascii=False)
        except TypeError:
            raise

        contexto = {
            "df_variavel": resultado["variavel"],
            "df_info": resultado["metadados"]["df_info"],
            "df_colunas": resultado["metadados"]["colunas"],
            "df_perfil": _montar_df_perfil(df),
            "df_amostra": amostra_json,
            "df_amostra_sanitizada": amostra_json,
            "contrato_perguntas_dados": contrato_perguntas,
        }
        return resultado, contexto

    def _aplicar_filtros(df: pd.DataFrame, filtros: List[Dict]) -> pd.DataFrame:
        out = df
        for f in filtros or []:
            col = f.get("coluna")
            op = (f.get("operador") or "eq").lower()
            val = f.get("valor")
            if not col or col not in out.columns:
                raise ValueError(f"Filtro inválido: coluna '{col}' não existe")
            if op == "eq":
                out = out[out[col] == val]
            elif op == "ne":
                out = out[out[col] != val]
            elif op == "gt":
                out = out[out[col] > val]
            elif op == "gte":
                out = out[out[col] >= val]
            elif op == "lt":
                out = out[out[col] < val]
            elif op == "lte":
                out = out[out[col] <= val]
            elif op == "in":
                vals = val if isinstance(val, list) else [val]
                out = out[out[col].isin(vals)]
            elif op == "not_in":
                vals = val if isinstance(val, list) else [val]
                out = out[~out[col].isin(vals)]
            else:
                raise ValueError(f"Operador de filtro não permitido: {op}")
        return out

    def _aplicar_janela(df: pd.DataFrame, item: Dict) -> pd.DataFrame:
        janela = item.get("janela_tempo")
        if not janela:
            return df

        dias = None
        col_data = item.get("coluna_data")
        if isinstance(janela, dict):
            dias = janela.get("dias")
            col_data = janela.get("coluna") or col_data
        elif isinstance(janela, (int, float)):
            dias = int(janela)

        if not dias:
            return df

        col_data = _resolver_col_data(df, preferida=col_data)
        if not col_data:
            raise ValueError("Janela temporal solicitada, mas coluna de data não encontrada")

        dt = pd.to_datetime(df[col_data], errors="coerce")
        limite = pd.Timestamp.now() - pd.Timedelta(days=int(dias))
        return df[dt >= limite]

    def _executar_perguntas_agregadas(parsed: Dict) -> Dict:
        perguntas = parsed.get("perguntas_dados") or []
        if not isinstance(perguntas, list) or len(perguntas) == 0:
            return {
                "sucesso": False,
                "resultado_texto": "perguntas_dados ausente ou vazio",
                "resultado_obj": {"schema_version": "1.0", "metricas": [], "erros": ["perguntas_dados ausente ou vazio"]},
            }

        df_nome = parsed.get("df_variavel_usada") or (df_contexto or {}).get("df_variavel")
        namespace = mysql_injetar_namespace if mysql_injetar_namespace is not None else globals()
        if not df_nome or df_nome not in namespace:
            msg = f"DataFrame '{df_nome}' não encontrado no namespace"
            return {
                "sucesso": False,
                "resultado_texto": msg,
                "resultado_obj": {"schema_version": "1.0", "metricas": [], "erros": [msg]},
            }

        base_df = namespace[df_nome]
        metricas = []
        erros = []

        for idx, item in enumerate(perguntas):
            metric_id = item.get("metric_id") or f"m_{idx+1}"
            desc = item.get("descricao") or ""
            tipo = (item.get("tipo") or "").lower().strip()
            try:
                if tipo not in contrato_perguntas["tipos_permitidos"]:
                    raise ValueError(f"Tipo não permitido: {tipo}")

                trabalho = base_df.copy()
                trabalho = _aplicar_filtros(trabalho, item.get("filtros") or [])
                trabalho = _aplicar_janela(trabalho, item)

                group_by = item.get("group_by") or []
                if isinstance(group_by, str):
                    group_by = [group_by]
                for g in group_by:
                    if g not in trabalho.columns:
                        raise ValueError(f"group_by inválido: coluna '{g}' não existe")

                coluna_valor = item.get("coluna_valor")

                if tipo == "count":
                    if coluna_valor:
                        if coluna_valor not in trabalho.columns:
                            raise ValueError(f"coluna_valor inválida: {coluna_valor}")
                        valor = int(trabalho[coluna_valor].notna().sum())
                    else:
                        valor = int(len(trabalho))

                elif tipo in {"sum", "mean", "median"}:
                    if not coluna_valor or coluna_valor not in trabalho.columns:
                        raise ValueError("sum/mean/median exigem coluna_valor válida")
                    s = pd.to_numeric(trabalho[coluna_valor], errors="coerce")
                    if tipo == "sum":
                        valor = _to_scalar(round(s.sum(), 6))
                    elif tipo == "mean":
                        valor = _to_scalar(round(s.mean(), 6)) if s.notna().any() else None
                    else:
                        valor = _to_scalar(round(s.median(), 6)) if s.notna().any() else None

                elif tipo == "percentile":
                    if not coluna_valor or coluna_valor not in trabalho.columns:
                        raise ValueError("percentile exige coluna_valor válida")
                    q = item.get("quantil")
                    if q is None:
                        q = item.get("percentil")
                    q = float(q if q is not None else 0.95)
                    if q > 1:
                        q = q / 100.0
                    q = min(max(q, 0.0), 1.0)
                    s = pd.to_numeric(trabalho[coluna_valor], errors="coerce")
                    valor = _to_scalar(round(s.quantile(q), 6)) if s.notna().any() else None

                elif tipo == "null_rate":
                    col = coluna_valor or item.get("coluna")
                    if not col or col not in trabalho.columns:
                        raise ValueError("null_rate exige coluna válida")
                    valor = round(float(trabalho[col].isna().mean() * 100), 4)

                elif tipo == "nunique":
                    col = coluna_valor or item.get("coluna")
                    if not col or col not in trabalho.columns:
                        raise ValueError("nunique exige coluna válida")
                    valor = int(trabalho[col].nunique(dropna=True))

                elif tipo == "top_n":
                    n = int(item.get("top_n") or 10)
                    agg = (item.get("agregacao") or "count").lower()
                    grp = group_by[0] if group_by else item.get("coluna_grupo")
                    if not grp or grp not in trabalho.columns:
                        raise ValueError("top_n exige group_by ou coluna_grupo válida")

                    if agg == "count":
                        serie = trabalho[grp].value_counts(dropna=False).head(n)
                        valor = [{"grupo": _to_scalar(k), "valor": int(v)} for k, v in serie.items()]
                    else:
                        if not coluna_valor or coluna_valor not in trabalho.columns:
                            raise ValueError("top_n com agregacao != count exige coluna_valor")
                        s = pd.to_numeric(trabalho[coluna_valor], errors="coerce")
                        df_aux = trabalho.copy()
                        df_aux["__valor__"] = s
                        if agg == "sum":
                            serie = df_aux.groupby(grp, dropna=False)["__valor__"].sum().sort_values(ascending=False).head(n)
                        elif agg == "mean":
                            serie = df_aux.groupby(grp, dropna=False)["__valor__"].mean().sort_values(ascending=False).head(n)
                        else:
                            raise ValueError(f"Agregação não permitida em top_n: {agg}")
                        valor = [{"grupo": _to_scalar(k), "valor": _to_scalar(round(v, 6))} for k, v in serie.items()]

                elif tipo == "timeseries":
                    col_data = _resolver_col_data(trabalho, preferida=item.get("coluna_data"))
                    if not col_data:
                        raise ValueError("timeseries exige coluna de data")
                    freq = (item.get("frequencia") or "ME").upper()
                    agg = (item.get("agregacao") or "count").lower()
                    dt = pd.to_datetime(trabalho[col_data], errors="coerce")
                    df_aux = trabalho.copy()
                    df_aux["__dt__"] = dt
                    df_aux = df_aux[df_aux["__dt__"].notna()]
                    df_aux = df_aux.set_index("__dt__")

                    if agg == "count":
                        serie = df_aux.resample(freq).size()
                    else:
                        if not coluna_valor or coluna_valor not in df_aux.columns:
                            raise ValueError("timeseries com agregação numérica exige coluna_valor")
                        s = pd.to_numeric(df_aux[coluna_valor], errors="coerce")
                        if agg == "sum":
                            serie = s.resample(freq).sum()
                        elif agg == "mean":
                            serie = s.resample(freq).mean()
                        else:
                            raise ValueError(f"Agregação não permitida em timeseries: {agg}")

                    valor = [
                        {"periodo": str(k.date()) if hasattr(k, "date") else str(k), "valor": _to_scalar(round(v, 6) if isinstance(v, (int, float)) else v)}
                        for k, v in serie.items()
                    ]

                else:
                    raise ValueError(f"Tipo não suportado: {tipo}")

                metricas.append({
                    "metric_id": metric_id,
                    "descricao": desc,
                    "tipo": tipo,
                    "status": "ok",
                    "resultado": valor,
                })

            except Exception as exc:
                erro = f"{metric_id}: {exc}"
                erros.append(erro)
                metricas.append({
                    "metric_id": metric_id,
                    "descricao": desc,
                    "tipo": tipo,
                    "status": "erro",
                    "erro": str(exc),
                })

        resultado_obj = {
            "schema_version": "1.0",
            "metricas": metricas,
            "erros": erros,
            "resumo_execucao": {
                "metricas_sucesso": len([m for m in metricas if m.get("status") == "ok"]),
                "metricas_erro": len([m for m in metricas if m.get("status") == "erro"]),
            },
        }
        return {
            "sucesso": len(metricas) > 0 and len([m for m in metricas if m.get("status") == "ok"]) > 0,
            "resultado_texto": json.dumps(resultado_obj, ensure_ascii=False),
            "resultado_obj": resultado_obj,
        }

    if verbose:
        print("[MAESTRO] Iniciando fluxo. Pergunta:", (pergunta[:80] + "...") if len(pergunta) > 80 else pergunta)

    if verbose:
        print("[MAESTRO] Passo 1+2: Analisando pergunta (chamando LLM Maestro)...")
    skill_maestro = get_skill_by_id(skills, "maestro")
    if not skill_maestro:
        raise ValueError("Skill 'maestro' não encontrada.")
    model_maestro = skill_maestro.get("model") or model
    msg_analise = (
        pergunta
        + "\n\nRetorne um JSON com uma única chave 'analise' (objeto) contendo: "
        "pergunta (string), dominios_identificados (lista de strings), tipo_resposta_esperada (uma de: factual, analítica, técnica, criativa, comparativa), "
        "complexidade (uma de: baixa, média, alta), informacao_central (string)."
    )
    resp_analise = client.chat.completions.create(
        model=model_maestro,
        messages=[
            {"role": "system", "content": skill_maestro["content"]},
            {"role": "user", "content": msg_analise},
        ],
        response_format={"type": "json_object"},
    )
    raw_analise = (resp_analise.choices[0].message.content or "").strip()
    analise_data = extrair_json(raw_analise)
    analise = (analise_data.get("analise") or analise_data) if isinstance(analise_data, dict) else {}
    if not analise:
        analise = {
            "pergunta": pergunta,
            "dominios_identificados": [],
            "tipo_resposta_esperada": "analítica",
            "complexidade": "média",
            "informacao_central": pergunta,
        }
    contexto_maestro = (
        f"Domínios: {analise.get('dominios_identificados', [])}; "
        f"Tipo: {analise.get('tipo_resposta_esperada', '')}; "
        f"Complexidade: {analise.get('complexidade', '')}; "
        f"Central: {analise.get('informacao_central', '')}"
    )

    if mysql_tabelas or mysql_tabela:
        if verbose:
            print("[MAESTRO] Pré-carregando dados MySQL...")
        resultado_mysql, df_contexto = _preparar_contexto_mysql()
        df_variavel = df_contexto.get("df_variavel")
        if verbose:
            print(f"[MAESTRO] DataFrame disponível em '{df_variavel}'.")
        tabela_ref = (mysql_tabelas[0]["tabela"] if mysql_tabelas else mysql_tabela)
        contexto_maestro = f"{contexto_maestro}; Tabela: {tabela_ref}; DF: {df_variavel}"

    def _invocar_um_agente(skill_id: str) -> Dict:
        """Invocação de um único agente (modo conhecimento ou 2 fases). Retorna o dict de resposta."""
        usa_dataframe = bool(df_contexto and skill_id in _agentes_dataframe)
        if verbose:
            modo = "2 fases" if usa_dataframe else "conhecimento"
            print(f"[MAESTRO] Passo 3: Invocando agente: {skill_id} ({modo})")
        payload_base = {
            "skill_invocada": skill_id,
            "pergunta": pergunta,
            "contexto_maestro": contexto_maestro,
            "tipo_resposta_esperada": analise.get("tipo_resposta_esperada", "analítica"),
        }
        if not usa_dataframe:
            payload_base["instrucao"] = "Responda estritamente dentro do seu domínio. Calcule seus scores."
            raw = invocar_agente_maestro(client, skill_id, payload_base, model=model, skills_list=skills, skills_dir=skills_dir)
            parsed = extrair_json(raw)
            if parsed and isinstance(parsed, dict):
                parsed.setdefault("agente_id", skill_id)
                return parsed
            return {
                "agente_id": skill_id,
                "agente_nome": skill_id,
                "pode_responder": False,
                "justificativa_viabilidade": "Resposta não veio em JSON válido.",
                "resposta": "",
                "scores": {},
            }
        payload_fase1 = {**payload_base}
        payload_fase1.update(df_contexto)
        payload_fase1["fase"] = "extracao"
        payload_fase1["instrucao"] = (
            "FASE 1 — EXTRAÇÃO ESTRUTURADA: opere em MODO DATAFRAME. "
            "NÃO gere código Python. Em vez disso, retorne 'perguntas_dados' (lista JSON) seguindo o contrato informado em 'contrato_perguntas_dados'. "
            "Cada pergunta deve ser agregada (sem linhas cruas) e alinhada ao seu domínio."
        )
        if verbose:
            print(f"[MAESTRO]   [{skill_id}] FASE 1: solicitando perguntas_dados...")
        raw1 = invocar_agente_maestro(client, skill_id, payload_fase1, model=model, skills_list=skills, skills_dir=skills_dir)
        parsed1 = extrair_json(raw1)
        if not parsed1 or not isinstance(parsed1, dict):
            return {
                "agente_id": skill_id,
                "agente_nome": skill_id,
                "pode_responder": False,
                "justificativa_viabilidade": "FASE 1 não retornou JSON válido.",
                "resposta": "",
                "scores": {},
            }
        parsed1.setdefault("agente_id", skill_id)
        if not parsed1.get("perguntas_dados"):
            parsed1["pode_responder"] = False
            parsed1["justificativa_viabilidade"] = (
                parsed1.get("justificativa_viabilidade")
                or "FASE 1 não retornou perguntas_dados."
            )
            return parsed1
        exec_info = _executar_perguntas_agregadas(parsed1)
        resultado_extracao = exec_info.get("resultado_obj", {})
        if verbose:
            status_exec = "✅" if exec_info.get("sucesso") else "❌"
            print(f"[MAESTRO]   [{skill_id}] FASE 1 execução {status_exec}: métricas="
                  f"{resultado_extracao.get('resumo_execucao', {}).get('metricas_sucesso', 0)}")
        if not exec_info.get("sucesso"):
            parsed1["resposta"] = (
                (parsed1.get("resposta") or "")
                + "\n\nFalha ao executar perguntas agregadas de FASE 1."
            ).strip()
            parsed1["resultado_execucao"] = resultado_extracao
            return parsed1
        if verbose:
            print(f"[MAESTRO]   [{skill_id}] FASE 2: enviando agregados para interpretação...")
        payload_fase2 = {
            "skill_invocada": skill_id,
            "pergunta": pergunta,
            "contexto_maestro": contexto_maestro,
            "tipo_resposta_esperada": analise.get("tipo_resposta_esperada", "analítica"),
            "fase": "interpretacao",
            "resultado_extracao": resultado_extracao,
            "instrucao": (
                "FASE 2 — INTERPRETAÇÃO: você recebeu em 'resultado_extracao' apenas métricas agregadas reais. "
                "Interprete conforme seu domínio e responda a pergunta do usuário. "
                "Não solicitar nem inferir dados linha a linha. "
                "Retorne o JSON completo de resposta (sem codigo_pandas)."
            ),
        }
        raw2 = invocar_agente_maestro(client, skill_id, payload_fase2, model=model, skills_list=skills, skills_dir=skills_dir)
        parsed2 = extrair_json(raw2)
        if parsed2 and isinstance(parsed2, dict):
            parsed2.setdefault("agente_id", skill_id)
            parsed2["resultado_execucao"] = resultado_extracao
            return parsed2
        parsed1["resultado_execucao"] = resultado_extracao
        parsed1["resposta"] = (
            (parsed1.get("resposta") or "")
            + "\n\nFASE 2 indisponível; retornando somente resultados agregados executados."
        ).strip()
        return parsed1

    with ThreadPoolExecutor(max_workers=len(agentes) or 1) as executor:
        futures = []
        for i, sid in enumerate(agentes):
            if i > 0:
                time.sleep(time_interval_agents)
            futures.append(executor.submit(_invocar_um_agente, sid))
        respostas_agentes = [f.result() for f in futures]

    para_avaliador = [r for r in respostas_agentes if r.get("pode_responder") is True]
    if verbose:
        print("[MAESTRO] Passo 4: Respostas a enviar ao avaliador:", len(para_avaliador), "de", len(respostas_agentes))

    avaliacao = None
    if not para_avaliador:
        entrega_final = (
            "## Resposta do Maestro\n\n**Pergunta:** " + pergunta
            + "\n\nNenhum agente qualificado para responder. "
            "Sugestão: reformule a pergunta ou consulte um domínio mais específico."
        )
    else:
        if verbose:
            print("[MAESTRO] Passo 5: Invocando avaliador de coerência...")
        payload_aval = {
            "pergunta_original": pergunta,
            "tipo_resposta_esperada": analise.get("tipo_resposta_esperada", "analítica"),
            "respostas_coletadas": [
                {
                    "agente_id": r.get("agente_id"),
                    "agente_nome": r.get("agente_nome", r.get("agente_id")),
                    "resposta": r.get("resposta", ""),
                    "scores_agente": r.get("scores") or {},
                    "limitacoes_da_resposta": r.get("limitacoes_da_resposta", ""),
                }
                for r in para_avaliador
            ],
        }
        skill_aval = get_skill_by_id(skills, "avaliador-coerencia")
        if not skill_aval:
            raise ValueError("Skill 'avaliador-coerencia' não encontrada.")
        model_aval = skill_aval.get("model") or model
        user_aval = (
            json.dumps(payload_aval, ensure_ascii=False)
            + "\n\nRetorne APENAS um JSON com: avaliacao_completa (lista de objetos com "
            "agente_id, agente_nome, scores_avaliador, score_total, status, observacoes), "
            "ranking_final (lista de agente_id), conflitos_detectados, respostas_excluidas, threshold_utilizado."
        )
        resp_aval = client.chat.completions.create(
            model=model_aval,
            messages=[
                {"role": "system", "content": skill_aval["content"]},
                {"role": "user", "content": user_aval},
            ],
            response_format={"type": "json_object"},
        )
        raw_aval = (resp_aval.choices[0].message.content or "").strip()
        avaliacao = extrair_json(raw_aval)

        if verbose:
            ranking = (avaliacao or {}).get("ranking_final", [])
            print("[MAESTRO] Avaliador retornou ranking:", ranking)

        if verbose:
            print("[MAESTRO] Passo 6: Formatando entrega ao usuário.")
        entrega_final = _formatar_entrega(pergunta, respostas_agentes, avaliacao, para_avaliador)

    if verbose:
        print("[MAESTRO] Fluxo concluído.")
    return {
        "analise": analise,
        "respostas_agentes": respostas_agentes,
        "avaliacao": avaliacao,
        "entrega_final": entrega_final,
        "resultado_mysql": resultado_mysql,
        "df_variavel": df_variavel,
    }
