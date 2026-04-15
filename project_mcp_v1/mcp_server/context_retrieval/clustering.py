"""K-Means sobre vectores de embedding (batch / worker)."""

from __future__ import annotations

from typing import Any


def fit_kmeans(
    vectors: list[list[float]],
    n_clusters: int,
    *,
    n_init: int = 12,
    random_state: int = 42,
) -> tuple[Any, int]:
    import numpy as np
    from sklearn.cluster import KMeans

    arr = np.array(vectors, dtype=np.float64)
    n_eff = min(int(n_clusters), len(vectors))
    km = KMeans(
        n_clusters=n_eff,
        n_init=max(3, int(n_init)),
        max_iter=400,
        tol=1e-4,
        random_state=random_state,
    )
    km.fit(arr)
    return km, n_eff


def silhouette_optional(vectors: list[list[float]], labels: list[int]) -> float | None:
    if len(vectors) < 3 or len(set(labels)) < 2:
        return None
    try:
        import numpy as np
        from sklearn.metrics import silhouette_score

        arr = np.array(vectors, dtype=np.float64)
        return float(silhouette_score(arr, labels, metric="euclidean"))
    except Exception:
        return None
