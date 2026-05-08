# app/services/clustering_metricas.py
"""
Clustering determinístico a partir de métricas FASE 1 (top_n por concessionária).
K-Means ou DBSCAN sobre matriz Z-score (StandardScaler), anexado em
resultado_extracao['clustering_deterministico'].
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler
except ImportError:
    KMeans = None  # type: ignore[misc, assignment]
    DBSCAN = None  # type: ignore[misc, assignment]


# Métricas com lista {grupo, valor} só entram na matriz de clustering se agruparem por uma destas colunas.
_GROUP_BY_CLUSTERING_PERMITIDO = frozenset(
    {
        ("concessionaria_id",),
        ("concessionaria_nome",),
    }
)


def _normaliza_group_by_metrica(m: Dict[str, Any]) -> Optional[Tuple[str, ...]]:
    """Retorna tupla normalizada de colunas ou None se ausente/vazio (legado)."""
    gb = m.get("group_by")
    if gb is None:
        return None
    if isinstance(gb, str):
        gb = [gb]
    if not isinstance(gb, list) or len(gb) == 0:
        return None
    return tuple(str(x).strip().lower() for x in gb)


def _group_by_permitido_matriz_clustering(m: Dict[str, Any]) -> bool:
    g = _normaliza_group_by_metrica(m)
    if g is None:
        return True
    return g in _GROUP_BY_CLUSTERING_PERMITIDO


def _grupo_parece_multi_entidade(s: str) -> bool:
    t = str(s).strip()
    if len(t) < 2:
        return True
    if t.startswith("(") and t.endswith(")"):
        inner = t[1:-1]
        if "," in inner:
            return True
    return False


def diagnosticar_metricas_clustering(metricas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Conta quantas métricas passam em cada filtro de metricas_para_matriz_concessionaria
    (para entender por que K-Means/DBSCAN não montam matriz).
    """
    stats: Dict[str, Any] = {
        "total_metricas": len(metricas),
        "status_ok": 0,
        "ok_com_lista_resultado": 0,
        "com_grupo_valor_sem_periodo": 0,
        "aceitas_na_matriz": 0,
        "metric_ids_aceitos_amostra": [],
        "motivos_exclusao": {
            "status_nao_ok": 0,
            "sem_metric_id": 0,
            "resultado_nao_lista_ou_vazio": 0,
            "sem_chaves_grupo_valor": 0,
            "timeseries_periodo": 0,
            "group_by_nao_concessionaria": 0,
            "multi_entidade_ou_duplicado_grupo": 0,
            "menos_de_2_grupos_distintos": 0,
        },
    }
    mids_amostra: List[str] = []
    aceitas = 0

    for m in metricas:
        if m.get("status") != "ok":
            stats["motivos_exclusao"]["status_nao_ok"] += 1
            continue
        stats["status_ok"] += 1
        mid = str(m.get("metric_id") or "").strip()
        if not mid:
            stats["motivos_exclusao"]["sem_metric_id"] += 1
            continue
        res = m.get("resultado")
        if not isinstance(res, list) or not res:
            stats["motivos_exclusao"]["resultado_nao_lista_ou_vazio"] += 1
            continue
        stats["ok_com_lista_resultado"] += 1
        r0 = res[0]
        if not isinstance(r0, dict) or "grupo" not in r0 or "valor" not in r0:
            stats["motivos_exclusao"]["sem_chaves_grupo_valor"] += 1
            continue
        if "periodo" in r0:
            stats["motivos_exclusao"]["timeseries_periodo"] += 1
            continue
        if not _group_by_permitido_matriz_clustering(m):
            stats["motivos_exclusao"]["group_by_nao_concessionaria"] += 1
            continue
        stats["com_grupo_valor_sem_periodo"] += 1

        grupos_vals: Dict[str, float] = {}
        duplicado = False
        for row in res:
            if not isinstance(row, dict):
                duplicado = True
                break
            g = row.get("grupo")
            s = str(g).strip()
            if _grupo_parece_multi_entidade(s):
                duplicado = True
                break
            v = row.get("valor")
            num = pd.to_numeric(v, errors="coerce")
            if s in grupos_vals:
                duplicado = True
                break
            grupos_vals[s] = float(num) if pd.notna(num) else float("nan")

        if duplicado:
            stats["motivos_exclusao"]["multi_entidade_ou_duplicado_grupo"] += 1
            continue
        if len(grupos_vals) < 2:
            stats["motivos_exclusao"]["menos_de_2_grupos_distintos"] += 1
            continue
        aceitas += 1
        if len(mids_amostra) < 15:
            mids_amostra.append(mid)

    stats["aceitas_na_matriz"] = aceitas
    stats["metric_ids_aceitos_amostra"] = mids_amostra
    return stats


def _log_cluster(log: bool, msg: str) -> None:
    logger.info(msg)
    if log:
        print(msg, flush=True)


def metricas_para_matriz_concessionaria(
    metricas: List[Dict[str, Any]],
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Monta DataFrame [concessionaria, m1, m2, ...] a partir de métricas ok cujo resultado
    é lista de {grupo, valor} com um único rótulo por linha (nome da concessionária).
    Ignora timeseries ({periodo, valor}) e top_n com chave composta (tupla).
    """
    series_por_mid: Dict[str, pd.Series] = {}
    mids_ok: List[str] = []

    for m in metricas:
        if m.get("status") != "ok":
            continue
        mid = str(m.get("metric_id") or "").strip()
        if not mid:
            continue
        res = m.get("resultado")
        if not isinstance(res, list) or not res:
            continue
        r0 = res[0]
        if not isinstance(r0, dict) or "grupo" not in r0 or "valor" not in r0:
            continue
        if "periodo" in r0:
            continue

        if not _group_by_permitido_matriz_clustering(m):
            continue

        grupos_vals: Dict[str, float] = {}
        duplicado = False
        for row in res:
            if not isinstance(row, dict):
                duplicado = True
                break
            g = row.get("grupo")
            s = str(g).strip()
            if _grupo_parece_multi_entidade(s):
                duplicado = True
                break
            v = row.get("valor")
            num = pd.to_numeric(v, errors="coerce")
            if s in grupos_vals:
                duplicado = True
                break
            grupos_vals[s] = float(num) if pd.notna(num) else float("nan")

        if duplicado or len(grupos_vals) < 2:
            continue

        ser = pd.Series(grupos_vals, name=mid)
        series_por_mid[mid] = ser
        mids_ok.append(mid)

    if len(series_por_mid) < 2:
        return pd.DataFrame(), mids_ok

    df = pd.DataFrame(series_por_mid)
    df.index.name = "concessionaria"
    df = df.reset_index()
    return df, mids_ok


def _silhueta_segura(Xn: np.ndarray, labels: np.ndarray) -> Optional[float]:
    mask = labels >= 0
    if mask.sum() < 2:
        return None
    labs = labels[mask]
    if len(set(labs)) < 2:
        return None
    try:
        return float(silhouette_score(Xn[mask], labs))
    except Exception:
        return None


def executar_clustering_metricas(
    resultado_extracao: Dict[str, Any],
    n_clusters: int = 5,
    metodo: str = "kmeans",
    min_concessionarias: int = 4,
    min_colunas_features: int = 2,
    random_state: int = 42,
    dbscan_eps: float = 0.5,
    dbscan_min_samples: Optional[int] = None,
    log_diagnostico: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Executa K-Means ou DBSCAN sobre features numéricas alinhadas por concessionária
    (normalização z-score). Retorna bloco para resultado_extracao['clustering_deterministico'].
    """
    prefix = "[CLUSTER]"

    if KMeans is None:
        _log_cluster(
            log_diagnostico,
            f"{prefix} sklearn não disponível (KMeans/DBSCAN não importados). "
            "Instale scikit-learn no ambiente do kernel.",
        )
        return None

    metricas = resultado_extracao.get("metricas") or []
    if not isinstance(metricas, list):
        _log_cluster(log_diagnostico, f"{prefix} resultado_extracao.metricas não é lista (tipo={type(metricas)}).")
        return None

    diag = diagnosticar_metricas_clustering(metricas)
    _log_cluster(
        log_diagnostico,
        f"{prefix} diagnóstico métricas: total={diag['total_metricas']} | "
        f"status_ok={diag['status_ok']} | com lista resultado={diag['ok_com_lista_resultado']} | "
        f"grupo+valor sem timeseries={diag['com_grupo_valor_sem_periodo']} | "
        f"aceitas p/ matriz (≥2 grupos, 1 dim)={diag['aceitas_na_matriz']}",
    )
    _log_cluster(
        log_diagnostico,
        f"{prefix} exclusões: {diag['motivos_exclusao']}",
    )
    if diag.get("metric_ids_aceitos_amostra"):
        _log_cluster(
            log_diagnostico,
            f"{prefix} metric_ids aceitos (amostra): {diag['metric_ids_aceitos_amostra']}",
        )

    df, mids_usadas = metricas_para_matriz_concessionaria(metricas)
    if df.empty:
        _log_cluster(
            log_diagnostico,
            f"{prefix} matriz vazia: são necessárias ≥2 métricas com pares grupo+valor por concessionária "
            f"(após merge). mids parciais antes do merge: {mids_usadas}.",
        )
        return None

    n_lojas = len(df)
    feature_cols = [c for c in df.columns if c != "concessionaria"]
    n_feat = len(feature_cols)

    if n_lojas < min_concessionarias:
        _log_cluster(
            log_diagnostico,
            f"{prefix} lojas na matriz={n_lojas} < min_concessionarias={min_concessionarias}. "
            f"features={n_feat} cols={feature_cols[:20]}{'…' if n_feat > 20 else ''}",
        )
        return None

    if n_feat < min_colunas_features:
        _log_cluster(
            log_diagnostico,
            f"{prefix} colunas de feature={n_feat} < min_colunas_features={min_colunas_features}. "
            f"lojas={n_lojas}. Precisa de pelo menos {min_colunas_features} métricas distintas elegíveis.",
        )
        return None

    X = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
    n_samples = X.shape[0]

    amostra = df.head(3).to_dict(orient="records")
    _log_cluster(
        log_diagnostico,
        f"{prefix} matriz OK: {n_lojas} lojas × {n_feat} features | "
        f"metric_ids_features={mids_usadas} | amostra 3 linhas={amostra}",
    )

    scaler = StandardScaler()
    Xn = scaler.fit_transform(X)

    metodo_l = (metodo or "kmeans").lower().strip()
    labels: np.ndarray
    k_efetivo: int
    centers_arr: Optional[np.ndarray] = None

    if metodo_l == "dbscan":
        if DBSCAN is None:
            _log_cluster(log_diagnostico, f"{prefix} DBSCAN pedido mas não importado.")
            return None
        ms = dbscan_min_samples
        if ms is None:
            ms = max(2, min(int(n_clusters), max(2, n_samples // 4)))
        _log_cluster(
            log_diagnostico,
            f"{prefix} DBSCAN eps={dbscan_eps} min_samples={ms} amostras={n_samples}",
        )
        model = DBSCAN(eps=float(dbscan_eps), min_samples=int(ms))
        labels = np.asarray(model.fit_predict(Xn), dtype=int)
        if np.all(labels == -1):
            _log_cluster(
                log_diagnostico,
                f"{prefix} DBSCAN: todos os pontos ruído (-1). Ajuste eps/min_samples ou use kmeans.",
            )
            return None
        k_efetivo = len({x for x in labels.tolist() if x >= 0})
        if k_efetivo < 1:
            return None
    else:
        k_req = max(2, min(int(n_clusters), n_samples))
        if k_req >= n_samples:
            k_req = max(2, n_samples - 1) if n_samples > 2 else 1
        if k_req < 2:
            _log_cluster(
                log_diagnostico,
                f"{prefix} K-Means: k_req<2 (amostras={n_samples}).",
            )
            return None
        _log_cluster(
            log_diagnostico,
            f"{prefix} K-Means n_clusters efetivo={k_req} (pedido={n_clusters}) amostras={n_samples}",
        )
        model = KMeans(n_clusters=k_req, random_state=random_state, n_init=10)
        labels = np.asarray(model.fit_predict(Xn), dtype=int)
        centers_arr = model.cluster_centers_
        k_efetivo = k_req
        metodo_l = "kmeans"

    dists = np.zeros(n_samples, dtype=float)
    if metodo_l == "kmeans" and centers_arr is not None:
        for i, lab in enumerate(labels):
            if 0 <= lab < len(centers_arr):
                dists[i] = float(np.linalg.norm(Xn[i] - centers_arr[lab]))
    else:
        # DBSCAN: distância ao centróide amostral do cluster
        for lab in set(labels.tolist()):
            if lab < 0:
                continue
            mask = labels == lab
            center = Xn[mask].mean(axis=0)
            for i in np.where(mask)[0]:
                dists[i] = float(np.linalg.norm(Xn[i] - center))

    sil = _silhueta_segura(Xn, labels)

    nomes = df["concessionaria"].astype(str).tolist()
    mapeamento = [
        {
            "concessionaria": nomes[i],
            "cluster_id": int(labels[i]),
            "distancia_centroide": round(dists[i], 6) if labels[i] >= 0 else None,
        }
        for i in range(n_samples)
    ]

    unique, counts = np.unique(labels, return_counts=True)
    distribuicao = {f"cluster_{int(u)}": int(c) for u, c in zip(unique, counts)}

    por_cluster: Dict[int, List[str]] = {}
    for item in mapeamento:
        cid = int(item["cluster_id"])
        por_cluster.setdefault(cid, []).append(item["concessionaria"])

    perfis_minimos = [
        {
            "cluster_id": cid,
            "n_concessionarias": len(lojas),
            "concessionarias": sorted(lojas),
        }
        for cid, lojas in sorted(por_cluster.items())
    ]

    nota = (
        f"Partição gerada no Maestro por {metodo_l.upper()} sobre matriz de {len(feature_cols)} "
        f"features (metric_ids: {', '.join(mids_usadas[:12])}"
        f"{'…' if len(mids_usadas) > 12 else ''}), após normalização z-score (StandardScaler)."
    )

    _log_cluster(
        log_diagnostico,
        f"{prefix} sucesso: metodo={metodo_l} clusters={k_efetivo} silhouette={sil} "
        f"distribuicao={distribuicao}",
    )

    return {
        "metodo": metodo_l,
        "n_clusters": k_efetivo,
        "normalizacao": "z_score_standard_scaler",
        "metric_ids_features": mids_usadas,
        "nota_tecnica": nota,
        "resumo_clustering": {
            "status": "executado",
            "total_concessionarias": n_samples,
            "n_clusters": k_efetivo,
            "metodo": metodo_l,
            "silhouette_score": sil,
            "distribuicao": distribuicao,
            "normalizacao": "z_score_standard_scaler",
        },
        "mapeamento_concessionarias": mapeamento,
        "perfis_clusters_dados": perfis_minimos,
    }


def executar_clustering_kmeans_metricas(
    resultado_extracao: Dict[str, Any],
    n_clusters: int = 5,
    min_concessionarias: int = 4,
    min_colunas_features: int = 2,
    random_state: int = 42,
    log_diagnostico: bool = False,
) -> Optional[Dict[str, Any]]:
    """Compatibilidade: apenas K-Means."""
    return executar_clustering_metricas(
        resultado_extracao,
        n_clusters=n_clusters,
        metodo="kmeans",
        min_concessionarias=min_concessionarias,
        min_colunas_features=min_colunas_features,
        random_state=random_state,
        log_diagnostico=log_diagnostico,
    )
